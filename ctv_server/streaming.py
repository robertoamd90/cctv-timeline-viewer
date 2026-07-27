import asyncio
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator

from ctv_server.db import get_db


PROFILE_NAMES = ("balanced", "fast")
_MAX_TRANSCODERS = max(0, int(os.environ.get("CTV_MAX_TRANSCODERS", "0")))
_transcode_slots = asyncio.Semaphore(_MAX_TRANSCODERS) if _MAX_TRANSCODERS else None


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


def build_transcode_command(
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
        "-movflags",
        "frag_keyframe+empty_moov+default_base_moof",
        "-flush_packets",
        "1",
        "-f",
        "mp4",
        "pipe:1",
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
