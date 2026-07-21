import logging
import os
import threading
import time
from datetime import datetime
from typing import Optional
from zoneinfo import ZoneInfo

from ctv_server.api.events import emit
from ctv_server.db import get_db, write_db
from ctv_server.indexer import index_camera
from ctv_server.operations import begin_index_job, end_index_job, index_generation
from ctv_server.partitioner import dates_for_range, partition_key, resolve_partition
from ctv_server.thumbnailer import generate_thumbnail

log = logging.getLogger("ctv.partitions")
_locks_guard = threading.Lock()
_locks: dict[tuple[int, str], threading.Lock] = {}
_thumbnail_worker = threading.Semaphore(1)


def _lock_for(camera_id: int, key: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault((camera_id, key), threading.Lock())


def _delete_partition_recordings(camera_id: int, key: str) -> int:
    with write_db() as conn:
        rows = conn.execute(
            "SELECT thumbnail_path FROM recordings WHERE camera_id = ? AND partition_key = ?",
            (camera_id, key),
        ).fetchall()
        count = conn.execute(
            "SELECT COUNT(*) FROM recordings WHERE camera_id = ? AND partition_key = ?",
            (camera_id, key),
        ).fetchone()[0]
        conn.execute(
            "DELETE FROM recordings WHERE camera_id = ? AND partition_key = ?", (camera_id, key)
        )
    for row in rows:
        if row["thumbnail_path"]:
            try:
                os.unlink(row["thumbnail_path"])
            except OSError:
                pass
    return count


def invalidate_partition(camera_id: int, key: str, path: str) -> dict:
    removed = _delete_partition_recordings(camera_id, key)
    with write_db() as conn:
        conn.execute("""
            INSERT INTO partitions (camera_id, partition_key, path, status, error, last_requested, file_count)
            VALUES (?, ?, ?, 'missing', NULL, ?, 0)
            ON CONFLICT(camera_id, partition_key) DO UPDATE SET
                path=excluded.path, status='missing', error=NULL,
                last_requested=excluded.last_requested, file_count=0,
                progress_done=0, progress_total=0
        """, (camera_id, key, path, time.time()))
        conn.execute(
            "UPDATE cameras SET source_status = 'online', source_error = NULL WHERE id = ?",
            (camera_id,),
        )
    payload = {"camera_id": camera_id, "partition": key, "status": "missing", "removed": removed}
    emit("partition", payload)
    return payload


def _generate_thumbnails(camera_id: int, key: str):
    if not begin_index_job():
        return
    with _thumbnail_worker:
        try:
            conn = get_db()
            rows = conn.execute(
                "SELECT id, path FROM recordings WHERE camera_id = ? AND partition_key = ? "
                "AND availability = 'available' AND media_kind = 'video' AND thumbnail_path IS NULL",
                (camera_id, key),
            ).fetchall()
            conn.close()
            updates = []
            for row in rows:
                thumb = generate_thumbnail(row["id"], row["path"])
                if thumb:
                    updates.append((thumb, row["id"]))
            if updates:
                with write_db() as conn:
                    conn.executemany("UPDATE recordings SET thumbnail_path = ? WHERE id = ?", updates)
            emit("partition", {"camera_id": camera_id, "partition": key, "status": "thumbnails_done"})
        finally:
            end_index_job()


def run_partition_scan(
    camera_id: int, key: str, path: str, expected_generation: Optional[int] = None
) -> dict:
    lock = _lock_for(camera_id, key)
    if not lock.acquire(blocking=False):
        return {"camera_id": camera_id, "partition": key, "status": "busy"}
    if not begin_index_job(expected_generation):
        lock.release()
        return {"camera_id": camera_id, "partition": key, "status": "busy"}
    try:
        with write_db() as conn:
            camera = conn.execute(
                "SELECT timezone, source_path FROM cameras WHERE id = ?", (camera_id,)
            ).fetchone()
            if not camera:
                return {"camera_id": camera_id, "partition": key, "status": "removed"}
            conn.execute(
                "UPDATE partitions SET status = 'scanning', error = NULL, progress_done = 0, progress_total = 0 "
                "WHERE camera_id = ? AND partition_key = ?",
                (camera_id, key),
            )
            conn.execute(
                "UPDATE cameras SET source_status = 'scanning', source_error = NULL WHERE id = ?",
                (camera_id,),
            )
        emit("partition", {"camera_id": camera_id, "partition": key, "status": "started"})

        if not os.path.isdir(camera["source_path"]):
            raise FileNotFoundError(f"Sorgente non disponibile: {camera['source_path']}")
        try:
            with os.scandir(camera["source_path"]) as entries:
                next(entries, None)
        except PermissionError as exc:
            raise PermissionError(f"Sorgente non leggibile: {camera['source_path']}") from exc
        if not os.path.isdir(path):
            return invalidate_partition(camera_id, key, path)

        last_progress = {"time": 0.0, "done": -1}

        def report_progress(done: int, total: int):
            now = time.monotonic()
            if done != total and now - last_progress["time"] < 0.5:
                return
            last_progress.update(time=now, done=done)
            with write_db() as progress_conn:
                progress_conn.execute(
                    "UPDATE partitions SET progress_done = ?, progress_total = ? "
                    "WHERE camera_id = ? AND partition_key = ?",
                    (done, total, camera_id, key),
                )
            emit("partition_progress", {
                "camera_id": camera_id, "partition": key, "done": done, "total": total,
            })

        result = index_camera(
            camera_id,
            path,
            timezone=camera["timezone"],
            partition_key=key,
            purge_missing=True,
            progress=report_progress,
        )
        completed = time.time()
        with write_db() as conn:
            conn.execute("""
                UPDATE partitions SET status = 'ready', error = NULL, last_scanned = ?, file_count = ?,
                    progress_done = ?, progress_total = ?
                WHERE camera_id = ? AND partition_key = ?
            """, (
                completed, result["total"], result["total"], result["total"], camera_id, key,
            ))
            conn.execute(
                "UPDATE cameras SET source_status = 'online', source_error = NULL, last_scan_completed = ? WHERE id = ?",
                (completed, camera_id),
            )
        payload = {"camera_id": camera_id, "partition": key, "status": "done", **result}
        emit("partition", payload)
        # Le miniature non ritardano ne la timeline ne le altre partizioni.
        threading.Thread(
            target=_generate_thumbnails, args=(camera_id, key), daemon=True
        ).start()
        return payload
    except Exception as exc:
        message = str(exc)
        log.warning("Partition scan failed for camera %d, %s: %s", camera_id, key, message)
        with write_db() as conn:
            conn.execute(
                "UPDATE partitions SET status = 'error', error = ? WHERE camera_id = ? AND partition_key = ?",
                (message, camera_id, key),
            )
            conn.execute(
                "UPDATE cameras SET source_status = 'offline', source_error = ? WHERE id = ?",
                (message, camera_id),
            )
        payload = {"camera_id": camera_id, "partition": key, "status": "error", "error": message}
        emit("partition", payload)
        return payload
    finally:
        end_index_job()
        lock.release()


def prepare_partitions(camera_ids: list[int], from_ts: float, to_ts: float) -> list[dict]:
    generation = index_generation()
    if not begin_index_job(generation):
        return []
    try:
        return _prepare_partitions(camera_ids, from_ts, to_ts, generation)
    finally:
        end_index_job()


def _prepare_partitions(
    camera_ids: list[int], from_ts: float, to_ts: float, generation: int
) -> list[dict]:
    conn = get_db()
    placeholders = ",".join("?" for _ in camera_ids)
    cameras = conn.execute(
        f"SELECT * FROM cameras WHERE indexing_mode = 'partitioned' AND id IN ({placeholders})",
        camera_ids,
    ).fetchall() if camera_ids else []
    conn.close()
    now = time.time()
    candidates = []
    for camera in cameras:
        offset = camera["time_offset_seconds"] or 0
        for day in dates_for_range(from_ts - offset, to_ts - offset, camera["timezone"]):
            key = partition_key(day)
            path = resolve_partition(camera["source_path"], camera["directory_pattern"], day)
            candidates.append({
                "camera_id": camera["id"], "key": key, "path": path,
                "is_today": day == datetime.now(ZoneInfo(camera["timezone"])).date(),
                "exists": os.path.isdir(path),
            })

    jobs = []
    with write_db() as conn:
        for candidate in candidates:
            camera_id, key, path = candidate["camera_id"], candidate["key"], candidate["path"]
            conn.execute("""
                INSERT INTO partitions (camera_id, partition_key, path, status, last_requested)
                VALUES (?, ?, ?, 'unknown', ?)
                ON CONFLICT(camera_id, partition_key) DO UPDATE SET
                    path=excluded.path, last_requested=excluded.last_requested
            """, (camera_id, key, path, now))
            row = conn.execute(
                "SELECT status, last_scanned FROM partitions WHERE camera_id = ? AND partition_key = ?",
                (camera_id, key),
            ).fetchone()
            default_ttl = "60" if candidate["is_today"] else "300"
            ttl = int(os.environ.get("CTV_ACTIVE_PARTITION_SECONDS", default_ttl))
            stale = not row["last_scanned"] or now - row["last_scanned"] >= ttl
            if not candidate["exists"]:
                jobs.append({
                    "camera_id": camera_id, "key": key, "path": path,
                    "missing": True, "generation": generation,
                })
            elif stale and not _lock_for(camera_id, key).locked():
                jobs.append({
                    "camera_id": camera_id, "key": key, "path": path,
                    "missing": False, "generation": generation,
                })
    return jobs
