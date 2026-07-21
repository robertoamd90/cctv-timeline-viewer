import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable, Optional

from ctv_server.db import get_db, write_db
from ctv_server.scanner import (
    extract_timestamp,
    get_ffprobe_data,
    hash_file,
    parse_ffprobe,
    scan_directory,
)


def index_camera(
    camera_id: int,
    source_path: str,
    timezone: str = "UTC",
    partition_key: Optional[str] = None,
    purge_missing: bool = False,
    progress: Optional[Callable[[int, int], None]] = None,
):
    """Riconcilia una sorgente senza perdere gli ID delle registrazioni."""
    conn = get_db()
    try:
        cam = conn.execute("SELECT timezone FROM cameras WHERE id = ?", (camera_id,)).fetchone()
        if timezone == "UTC":
            if cam and cam["timezone"]:
                timezone = cam["timezone"]
        existing_query = "SELECT path, size, mtime FROM recordings WHERE camera_id = ?"
        existing_params: tuple = (camera_id,)
        if partition_key is not None:
            existing_query += " AND partition_key = ?"
            existing_params += (partition_key,)
        existing = {
            row["path"]: (row["size"], row["mtime"])
            for row in conn.execute(existing_query, existing_params).fetchall()
        }
    finally:
        conn.close()

    # Fallire qui significa sorgente offline: non cambiare l'indice esistente.
    files = scan_directory(source_path)
    scan_time = time.time()
    seen_paths = {item["path"] for item in files}
    counts = {"new": 0, "updated": 0, "missing": 0, "skipped": 0, "total": len(files)}
    skipped_paths = []
    prepared = []

    # Tutto il lavoro lento avviene senza una transazione SQLite aperta.
    changed_media = []
    for media in files:
        previous = existing.get(media["path"])
        same_mtime = previous and previous[1] is not None and abs(previous[1] - media["mtime"]) < 0.001
        if previous and previous[0] == media["size"] and same_mtime:
            skipped_paths.append(media["path"])
            counts["skipped"] += 1
            continue
        changed_media.append(media)

    if progress:
        progress(counts["skipped"], len(files))

    def prepare_media(media: dict) -> tuple:
        start_ts = extract_timestamp(media["filename"], media["path"], timezone)
        media_kind = "video"
        meta = parse_ffprobe(get_ffprobe_data(media["path"]))
        start_ts = start_ts or meta.get("creation_time") or media["mtime"]
        duration = meta.get("duration", 0) or 0
        end_ts = start_ts + duration if duration > 0 else None
        file_hash = hash_file(media["path"]) if os.environ.get("CTV_HASH_FILES") == "1" else None
        return (
            camera_id, media["path"], media["filename"], start_ts, end_ts, duration,
            meta.get("codec", ""), meta.get("resolution", ""), meta.get("fps", 0),
            media["size"], media["mtime"], file_hash, partition_key, media_kind, scan_time,
        )

    workers = max(1, int(os.environ.get("CTV_INDEX_WORKERS", "4")))
    done = counts["skipped"]
    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {executor.submit(prepare_media, media): media for media in changed_media}
        for future in as_completed(futures):
            media = futures[future]
            prepared.append(future.result())
            counts["updated" if media["path"] in existing else "new"] += 1
            done += 1
            if progress:
                progress(done, len(files))

    with write_db() as conn:
        conn.executemany(
            "UPDATE recordings SET availability = 'available', last_seen = ? "
            "WHERE camera_id = ? AND path = ?",
            ((scan_time, camera_id, path) for path in skipped_paths),
        )
        for values in prepared:
            conn.execute("""
                INSERT INTO recordings (
                    camera_id, path, filename, start_ts, end_ts, duration,
                    codec, resolution, fps, size, mtime, hash, partition_key, media_kind,
                    availability, last_seen
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'available', ?)
                ON CONFLICT(camera_id, path) DO UPDATE SET
                    filename=excluded.filename, start_ts=excluded.start_ts,
                    end_ts=excluded.end_ts, duration=excluded.duration,
                    codec=excluded.codec, resolution=excluded.resolution,
                    fps=excluded.fps, size=excluded.size, mtime=excluded.mtime, hash=excluded.hash,
                    partition_key=excluded.partition_key,
                    media_kind=excluded.media_kind,
                    availability='available', last_seen=excluded.last_seen
            """, values)

        available_query = (
            "SELECT id, path, thumbnail_path FROM recordings "
            "WHERE camera_id = ? AND availability = 'available'"
        )
        available_params: tuple = (camera_id,)
        if partition_key is not None:
            available_query += " AND partition_key = ?"
            available_params += (partition_key,)
        available_rows = conn.execute(available_query, available_params).fetchall()
        missing_paths = [row["path"] for row in available_rows if row["path"] not in seen_paths]
        missing_thumbnails = [
            row["thumbnail_path"] for row in available_rows
            if row["path"] in missing_paths and row["thumbnail_path"]
        ]
        if purge_missing:
            conn.executemany(
                "DELETE FROM recordings WHERE camera_id = ? AND path = ?",
                ((camera_id, path) for path in missing_paths),
            )
        else:
            conn.executemany(
                "UPDATE recordings SET availability = 'missing' WHERE camera_id = ? AND path = ?",
                ((camera_id, path) for path in missing_paths),
            )
        counts["missing"] = len(missing_paths)
        for thumbnail in missing_thumbnails:
            try:
                os.unlink(thumbnail)
            except OSError:
                pass
        return counts
