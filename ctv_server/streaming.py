import asyncio
import logging
import os
import re
import shutil
import tempfile
import time
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator, Optional

from ctv_server.db import get_db


PROFILE_NAMES = ("balanced", "fast")
_MAX_TRANSCODERS = max(0, int(os.environ.get("CTV_MAX_TRANSCODERS", "0")))
_transcode_slots = asyncio.Semaphore(_MAX_TRANSCODERS) if _MAX_TRANSCODERS else None
_HLS_ROOT = Path(os.environ.get(
    "CTV_HLS_ROOT", os.path.join(tempfile.gettempdir(), "ctv-hls"),
))
_HLS_TTL_SECONDS = max(30, int(os.environ.get("CTV_HLS_TTL_SECONDS", "300")))
_HLS_START_TIMEOUT = max(10, int(os.environ.get("CTV_HLS_START_TIMEOUT", "30")))
_HLS_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")
_HLS_SEGMENT_PATTERN = re.compile(r"^segment_\d{5}\.ts$")


@dataclass
class HlsJob:
    signature: tuple
    directory: Path
    error_path: Path
    process: asyncio.subprocess.Process
    last_access: float
    started_at: float
    started_logged: bool = False


_hls_jobs: dict[str, HlsJob] = {}
_hls_lock = asyncio.Lock()
_hls_tasks: set[asyncio.Task] = set()
log = logging.getLogger("ctv.streaming")


def _hls_failure_detail(job: HlsJob) -> str:
    try:
        detail = job.error_path.read_text(
            encoding="utf-8", errors="replace",
        ).strip()
    except OSError:
        detail = ""
    return detail[-1000:] or f"ffmpeg exited {job.process.returncode}"


def get_stream_profiles() -> dict:
    conn = get_db()
    rows = conn.execute(
        """
        SELECT name, scale_percent, fps, bitrate_kbps
        FROM stream_profiles
        WHERE name IN ('balanced', 'fast')
        """
    ).fetchall()
    conn.close()
    configured = {
        row["name"]: {
            "name": row["name"],
            "configurable": True,
            "scale_percent": row["scale_percent"],
            "fps": row["fps"],
            "bitrate_kbps": row["bitrate_kbps"],
        }
        for row in rows
    }
    return {
        "native": {
            "name": "native",
            "configurable": False,
            "scale_percent": 100,
            "fps": None,
            "bitrate_kbps": None,
        },
        **{name: configured[name] for name in PROFILE_NAMES},
    }


def _encoding_command(
    filepath: str,
    profile: dict,
    start_seconds: float,
    speed: float,
) -> list[str]:
    scale = profile["scale_percent"] / 100
    fps = profile["fps"]
    bitrate = profile["bitrate_kbps"]
    preset = "ultrafast" if profile["name"] == "fast" else "veryfast"
    video_filter = (
        f"setpts=(PTS-STARTPTS)/{speed:g},"
        f"fps={fps},"
        f"scale=trunc(iw*{scale:g}/2)*2:trunc(ih*{scale:g}/2)*2:flags=fast_bilinear"
    )
    return [
        "ffmpeg",
        "-nostdin",
        "-hide_banner",
        "-loglevel",
        "error",
        "-ss",
        f"{start_seconds:.3f}",
        "-i",
        filepath,
        "-map",
        "0:v:0",
        "-an",
        "-sn",
        "-dn",
        "-vf",
        video_filter,
        "-c:v",
        "libx264",
        "-preset",
        preset,
        "-tune",
        "zerolatency",
        "-pix_fmt",
        "yuv420p",
        "-b:v",
        f"{bitrate}k",
        "-maxrate",
        f"{bitrate}k",
        "-bufsize",
        f"{bitrate * 2}k",
        "-g",
        str(fps),
        "-keyint_min",
        str(fps),
        "-sc_threshold",
        "0",
        "-fps_mode",
        "cfr",
    ]


def build_transcode_command(
    filepath: str,
    profile: dict,
    start_seconds: float,
    speed: float,
) -> list[str]:
    return [
        *_encoding_command(filepath, profile, start_seconds, speed),
        "-movflags",
        "frag_keyframe+empty_moov+default_base_moof",
        "-flush_packets",
        "1",
        "-f",
        "mp4",
        "pipe:1",
    ]


def build_hls_command(
    filepath: str,
    profile: dict,
    start_seconds: float,
    speed: float,
    output_dir: str,
) -> list[str]:
    directory = Path(output_dir)
    return [
        *_encoding_command(filepath, profile, start_seconds, speed),
        "-hls_time",
        "1",
        "-hls_list_size",
        "0",
        "-hls_playlist_type",
        "event",
        "-hls_flags",
        "independent_segments+temp_file",
        "-hls_segment_filename",
        str(directory / "segment_%05d.ts"),
        "-muxdelay",
        "0",
        "-f",
        "hls",
        str(directory / "index.m3u8"),
    ]


async def _stop_process(process: asyncio.subprocess.Process):
    if process.returncode is not None:
        return
    process.terminate()
    try:
        await asyncio.wait_for(process.wait(), timeout=2)
    except asyncio.TimeoutError:
        process.kill()
        await process.wait()


@asynccontextmanager
async def _transcode_slot():
    if _transcode_slots is None:
        yield
        return
    async with _transcode_slots:
        yield


async def _expire_hls_job(job_id: str):
    job = _hls_jobs.get(job_id)
    if not job:
        return
    await job.process.wait()
    if job.process.returncode:
        log.warning(
            "HLS session %s failed: %s",
            job_id[:8], _hls_failure_detail(job),
        )
        async with _hls_lock:
            if _hls_jobs.get(job_id) is job:
                _hls_jobs.pop(job_id, None)
        shutil.rmtree(job.directory, ignore_errors=True)
        return
    log.info(
        "HLS session %s completed in %.2fs with %d segments",
        job_id[:8],
        time.monotonic() - job.started_at,
        len(list(job.directory.glob("segment_*.ts"))),
    )
    while True:
        delay = _HLS_TTL_SECONDS - (time.monotonic() - job.last_access)
        if delay > 0:
            await asyncio.sleep(delay)
        async with _hls_lock:
            current = _hls_jobs.get(job_id)
            if current is not job:
                return
            if time.monotonic() - job.last_access < _HLS_TTL_SECONDS:
                continue
            _hls_jobs.pop(job_id, None)
        shutil.rmtree(job.directory, ignore_errors=True)
        return


async def ensure_hls_playlist(
    job_id: str,
    filepath: str,
    profile: dict,
    start_seconds: float,
    speed: float,
) -> Path:
    if not _HLS_ID_PATTERN.fullmatch(job_id):
        raise ValueError("Invalid HLS session")
    signature = (
        filepath,
        profile["name"],
        profile["scale_percent"],
        profile["fps"],
        profile["bitrate_kbps"],
        round(start_seconds, 3),
        speed,
    )
    async with _hls_lock:
        job = _hls_jobs.get(job_id)
        if job and job.signature != signature:
            raise ValueError("HLS session parameters changed")
        if not job:
            directory = _HLS_ROOT / job_id
            directory.mkdir(parents=True, exist_ok=False)
            started_at = time.monotonic()
            error_path = directory / "ffmpeg.log"
            try:
                with error_path.open("wb") as error_output:
                    process = await asyncio.create_subprocess_exec(
                        *build_hls_command(
                            filepath, profile, start_seconds, speed, str(directory),
                        ),
                        stdout=asyncio.subprocess.DEVNULL,
                        stderr=error_output,
                    )
            except Exception:
                shutil.rmtree(directory, ignore_errors=True)
                raise
            job = HlsJob(
                signature, directory, error_path, process, started_at, started_at,
            )
            _hls_jobs[job_id] = job
            log.info(
                "Starting HLS session %s profile=%s speed=%gx offset=%.3fs",
                job_id[:8], profile["name"], speed, start_seconds,
            )
            task = asyncio.create_task(_expire_hls_job(job_id))
            _hls_tasks.add(task)
            task.add_done_callback(_hls_tasks.discard)
        else:
            job.last_access = time.monotonic()

    playlist = job.directory / "index.m3u8"
    deadline = time.monotonic() + _HLS_START_TIMEOUT
    while time.monotonic() < deadline:
        if playlist.is_file():
            try:
                contents = playlist.read_text(encoding="utf-8")
            except (OSError, UnicodeDecodeError):
                contents = ""
            segment_names = [
                line.strip()
                for line in contents.splitlines()
                if _HLS_SEGMENT_PATTERN.fullmatch(line.strip())
            ]
            if segment_names and (job.directory / segment_names[0]).is_file():
                job.last_access = time.monotonic()
                if not job.started_logged:
                    job.started_logged = True
                    log.info(
                        "HLS session %s playable in %.2fs",
                        job_id[:8],
                        time.monotonic() - job.started_at,
                    )
                return playlist
        if job.process.returncode is not None:
            log.warning(
                "HLS session %s failed: %s",
                job_id[:8], _hls_failure_detail(job),
            )
            raise RuntimeError("Unable to create HLS stream")
        await asyncio.sleep(0.05)
    await _stop_process(job.process)
    log.warning(
        "HLS session %s did not produce a playable segment within %ss",
        job_id[:8], _HLS_START_TIMEOUT,
    )
    raise TimeoutError("Timed out while starting HLS stream")


def hls_playlist_contents(playlist: Path) -> bytes:
    contents = playlist.read_text(encoding="utf-8")
    start_tag = "#EXT-X-START:TIME-OFFSET=0,PRECISE=YES"
    if start_tag not in contents:
        contents = contents.replace(
            "#EXTM3U\n",
            f"#EXTM3U\n{start_tag}\n",
            1,
        )
    return contents.encode("utf-8")


def hls_segment(job_id: str, filename: str) -> Optional[Path]:
    if not _HLS_ID_PATTERN.fullmatch(job_id):
        return None
    if not _HLS_SEGMENT_PATTERN.fullmatch(filename):
        return None
    job = _hls_jobs.get(job_id)
    if not job:
        return None
    job.last_access = time.monotonic()
    path = job.directory / filename
    return path if path.is_file() else None


async def shutdown_hls_jobs():
    async with _hls_lock:
        jobs = list(_hls_jobs.values())
        _hls_jobs.clear()
    tasks = list(_hls_tasks)
    _hls_tasks.clear()
    for task in tasks:
        task.cancel()
    await asyncio.gather(*tasks, return_exceptions=True)
    await asyncio.gather(
        *(_stop_process(job.process) for job in jobs),
        return_exceptions=True,
    )
    shutil.rmtree(_HLS_ROOT, ignore_errors=True)


async def transcode_stream(
    filepath: str,
    profile: dict,
    start_seconds: float,
    speed: float,
) -> AsyncIterator[bytes]:
    async with _transcode_slot():
        process = await asyncio.create_subprocess_exec(
            *build_transcode_command(filepath, profile, start_seconds, speed),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        try:
            while True:
                chunk = await process.stdout.read(256 * 1024)
                if not chunk:
                    break
                yield chunk
            await process.wait()
        finally:
            await _stop_process(process)
