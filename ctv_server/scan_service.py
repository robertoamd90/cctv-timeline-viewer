import logging
import threading
import time

from ctv_server.api.events import emit
from ctv_server.db import get_db
from ctv_server.indexer import index_camera
from ctv_server.thumbnailer import generate_thumbnail

log = logging.getLogger("ctv.scan")
_locks_guard = threading.Lock()
_camera_locks: dict[int, threading.Lock] = {}


def _lock_for(camera_id: int) -> threading.Lock:
    with _locks_guard:
        return _camera_locks.setdefault(camera_id, threading.Lock())


def is_scanning(camera_id: int) -> bool:
    return _lock_for(camera_id).locked()


def run_camera_scan(camera_id: int, source_path: str) -> dict:
    """Esegue un solo job per camera e persiste lo stato operativo."""
    lock = _lock_for(camera_id)
    if not lock.acquire(blocking=False):
        return {"status": "busy", "camera_id": camera_id}

    started = time.time()
    conn = get_db()
    camera = conn.execute("SELECT source_path FROM cameras WHERE id = ?", (camera_id,)).fetchone()
    if not camera:
        conn.close()
        lock.release()
        return {"status": "removed", "camera_id": camera_id}
    # Usa sempre il percorso corrente: il watcher potrebbe avere letto una configurazione precedente.
    source_path = camera["source_path"]
    conn.execute(
        "UPDATE cameras SET source_status = 'scanning', source_error = NULL, last_scan_started = ? WHERE id = ?",
        (started, camera_id),
    )
    conn.commit()
    conn.close()
    emit("scan", {"camera_id": camera_id, "status": "started"})

    try:
        result = index_camera(camera_id, source_path)
        emit("scan", {"camera_id": camera_id, "status": "indexing_done", **result})

        conn = get_db()
        rows = conn.execute(
            "SELECT id, path FROM recordings WHERE camera_id = ? "
            "AND availability = 'available' AND thumbnail_path IS NULL",
            (camera_id,),
        ).fetchall()
        conn.close()
        thumbnail_updates = []
        for index, row in enumerate(rows):
            try:
                thumb = generate_thumbnail(row["id"], row["path"])
                if thumb:
                    thumbnail_updates.append((thumb, row["id"]))
            except Exception:
                log.exception("Thumbnail failed for recording %d", row["id"])
            emit("scan", {
                "camera_id": camera_id,
                "status": "thumbnails",
                "done": index + 1,
                "total": len(rows),
            })
        completed = time.time()
        conn = get_db()
        conn.executemany(
            "UPDATE recordings SET thumbnail_path = ? WHERE id = ?",
            thumbnail_updates,
        )
        conn.execute(
            "UPDATE cameras SET source_status = 'online', source_error = NULL, "
            "last_scan_completed = ? WHERE id = ?",
            (completed, camera_id),
        )
        conn.commit()
        conn.close()
        payload = {"camera_id": camera_id, "status": "done", **result}
        emit("scan", payload)
        return payload
    except Exception as exc:
        message = str(exc)
        log.warning("Scan failed for camera %d: %s", camera_id, message)
        conn = get_db()
        conn.execute(
            "UPDATE cameras SET source_status = 'offline', source_error = ? WHERE id = ?",
            (message, camera_id),
        )
        conn.commit()
        conn.close()
        payload = {"camera_id": camera_id, "status": "error", "error": message}
        emit("scan", payload)
        return payload
    finally:
        lock.release()
