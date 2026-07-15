import os
import re
import hashlib
import subprocess
import json
from typing import Optional
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

VIDEO_EXTENSIONS = {".mp4", ".avi", ".mkv", ".mov", ".ts", ".h264", ".h265", ".dav"}

# Regex per estrarre timestamp da nomi file come:
#   CAM-Esterno_00_20260706002901.mp4
#   camera01_2026-07-06_14-30-00.mp4
#   20260706_002901.mp4
TIMESTAMP_PATTERNS = [
    re.compile(r"(\d{4})(\d{2})(\d{2})_?(\d{2})(\d{2})(\d{2})"),  # 20260706_002901
    re.compile(r"(\d{4})-(\d{2})-(\d{2})_?(\d{2})-?(\d{2})-?(\d{2})"),  # 2026-07-06_14-30-00
    re.compile(r"(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})"),  # 20260706002901
]


def scan_directory(source_path: str) -> list[dict]:
    """Trova solo i file video supportati in una directory (ricorsivo)."""
    if not os.path.isdir(source_path):
        raise FileNotFoundError(f"Sorgente non disponibile: {source_path}")
    files = []
    def onerror(error):
        raise error

    for root, _, filenames in os.walk(source_path, onerror=onerror):
        for f in filenames:
            ext = Path(f).suffix.lower()
            if ext in VIDEO_EXTENSIONS:
                path = os.path.join(root, f)
                try:
                    stat = os.stat(path)
                except FileNotFoundError:
                    continue
                files.append({
                    "path": path,
                    "filename": f,
                    "ext": ext,
                    "size": stat.st_size,
                    "mtime": stat.st_mtime,
                })
    files.sort(key=lambda item: item["path"])
    return files


def extract_timestamp(filename: str, filepath: str, tz_name: str = "UTC") -> Optional[float]:
    """Prova a estrarre il timestamp dal nome file via regex.
    Interpreta la data/ora nel timezone indicato e restituisce timestamp UTC."""
    for pattern in TIMESTAMP_PATTERNS:
        m = pattern.search(filename)
        if m:
            try:
                y, mo, d, h, mi, s = map(int, m.groups())
                tz = ZoneInfo(tz_name) if tz_name != "UTC" else timezone.utc
                dt = datetime(y, mo, d, h, mi, s, tzinfo=tz)
                return dt.timestamp()
            except (ValueError, KeyError):
                continue
    return None


def get_ffprobe_data(filepath: str) -> dict:
    """Estrae metadati video via ffprobe."""
    try:
        result = subprocess.run(
            [
                "ffprobe", "-v", "quiet", "-print_format", "json",
                "-show_format", "-show_streams", filepath,
            ],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            return {}
        return json.loads(result.stdout)
    except (FileNotFoundError, subprocess.TimeoutExpired, json.JSONDecodeError):
        return {}


def parse_ffprobe(probe: dict) -> dict:
    """Estrae i campi rilevanti dall'output ffprobe."""
    fmt = probe.get("format", {})
    video_stream = None
    for stream in probe.get("streams", []):
        if stream.get("codec_type") == "video":
            video_stream = stream
            break

    info = {
        "duration": float(fmt.get("duration", 0)),
        "codec": video_stream.get("codec_name", "") if video_stream else "",
        "resolution": f"{video_stream.get('width', 0)}x{video_stream.get('height', 0)}" if video_stream else "",
        "fps": 0.0,
        "creation_time": None,
    }

    # FPS
    if video_stream:
        fps_str = video_stream.get("r_frame_rate", "0/1")
        if "/" in fps_str:
            num, den = fps_str.split("/")
            info["fps"] = float(num) / float(den) if float(den) != 0 else 0.0

    # Timestamp dai metadati
    tags = fmt.get("tags", {})
    for key in ("creation_time", "date"):
        if key in tags:
            try:
                dt = datetime.fromisoformat(tags[key].replace("Z", "+00:00"))
                info["creation_time"] = dt.timestamp()
                break
            except (ValueError, TypeError):
                pass

    return info


def hash_file(filepath: str, chunk_size: int = 8192) -> str:
    """Hash SHA256 del file (primi 64KB + ultimi 64KB + dimensione)."""
    size = os.path.getsize(filepath)
    h = hashlib.sha256()
    h.update(str(size).encode())
    with open(filepath, "rb") as f:
        # Primi 64KB
        h.update(f.read(65536))
        # Ultimi 64KB
        if size > 131072:
            f.seek(-65536, os.SEEK_END)
            h.update(f.read(65536))
    return h.hexdigest()[:16]
