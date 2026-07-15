import os
import subprocess
from typing import Optional
from pathlib import Path

THUMBNAIL_DIR = os.environ.get("CTV_THUMBNAILS", os.path.expanduser("~/.ctv/thumbnails"))


def generate_thumbnail(recording_id: int, filepath: str, width: int = 320) -> Optional[str]:
    """Genera una thumbnail dal video al secondo 0 e la salva su disco."""
    os.makedirs(THUMBNAIL_DIR, exist_ok=True)
    out_path = os.path.join(THUMBNAIL_DIR, f"{recording_id}.jpg")

    try:
        subprocess.run(
            [
                "ffmpeg", "-y", "-ss", "1", "-i", filepath,
                "-vframes", "1", "-vf", f"scale={width}:-1",
                "-q:v", "3", out_path,
            ],
            capture_output=True, check=True, timeout=30,
        )
        return out_path
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired, FileNotFoundError):
        return None
