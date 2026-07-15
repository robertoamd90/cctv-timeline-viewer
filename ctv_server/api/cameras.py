import os
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, Request
from ctv_server.auth import CurrentUser, current_user, require_admin
from ctv_server.config import path_within_source_roots
from ctv_server.db import get_db
from ctv_server.models import CameraCreate, CameraResponse, CameraUpdate
from ctv_server.partitioner import validate_pattern

router = APIRouter(prefix="/api/cameras", tags=["cameras"])


def _local_tz() -> str:
    """Restituisce il timezone IANA del sistema (es. 'Europe/Rome').
    Su macOS/Linux legge /etc/localtime. Fallback a 'UTC'."""
    import os
    for p in ("/etc/localtime", "/var/db/timezone/zoneinfo"):
        try:
            link = os.readlink(p)
            # /etc/localtime -> /usr/share/zoneinfo/Europe/Rome
            # oppure /var/db/timezone/zoneinfo/Europe/Rome
            for sep in ("zoneinfo/", "zoneinfo"):
                parts = link.rsplit(sep, 1)
                if len(parts) == 2 and parts[1]:
                    return parts[1].lstrip("/")
        except Exception:
            continue
    try:
        with open("/etc/timezone") as f:
            tz = f.read().strip()
            if tz: return tz
    except Exception:
        pass
    return "UTC"


def _validate_source(source_path: str, timezone: str) -> tuple[str, str]:
    path = os.path.abspath(source_path)
    try:
        ZoneInfo(timezone)
    except ZoneInfoNotFoundError:
        raise HTTPException(status_code=422, detail=f"Timezone non valida: {timezone}")
    if not path_within_source_roots(path):
        raise HTTPException(status_code=403, detail="La sorgente e fuori dalle directory consentite")
    if not os.path.isdir(path):
        raise HTTPException(status_code=422, detail="La sorgente non esiste o non e montata")
    try:
        # os.access non e affidabile sui mount smbfs di macOS: prova una vera enumerazione.
        with os.scandir(path) as entries:
            next(entries, None)
    except PermissionError:
        raise HTTPException(
            status_code=422,
            detail="La sorgente esiste ma il processo CTV non ha il permesso di leggerla",
        )
    except OSError as exc:
        raise HTTPException(status_code=422, detail=f"Impossibile leggere la sorgente: {exc}")
    return path, timezone


@router.get("")
def list_cameras(request: Request) -> list[dict]:
    user = current_user(request)
    conn = get_db()
    rows = conn.execute("""
        SELECT c.*,
            SUM(CASE WHEN r.availability = 'available' THEN 1 ELSE 0 END) AS recordings_available,
            SUM(CASE WHEN r.availability = 'missing' THEN 1 ELSE 0 END) AS recordings_missing
        FROM cameras c LEFT JOIN recordings r ON r.camera_id = c.id
        GROUP BY c.id ORDER BY c.name
    """).fetchall()
    conn.close()
    if user.is_admin:
        return [CameraResponse(**dict(row)).model_dump() for row in rows]
    return [
        {
            "id": row["id"],
            "name": row["name"],
            "timezone": row["timezone"],
            "source_status": row["source_status"],
            "recordings_available": row["recordings_available"] or 0,
            "recordings_missing": row["recordings_missing"] or 0,
        }
        for row in rows
    ]


@router.post("", status_code=201)
def create_camera(body: CameraCreate, _: CurrentUser = Depends(require_admin)) -> CameraResponse:
    source_path = os.path.abspath(body.source_path)
    tz = body.timezone.strip() if body.timezone else _local_tz()
    source_path, tz = _validate_source(source_path, tz)
    try:
        pattern = validate_pattern(body.directory_pattern)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    conn = get_db()
    cur = conn.execute(
        "INSERT INTO cameras (name, source_path, timezone, indexing_mode, directory_pattern, source_status) "
        "VALUES (?, ?, ?, ?, ?, 'online')",
        (body.name.strip(), source_path, tz, body.indexing_mode, pattern),
    )
    conn.commit()
    camera = conn.execute("SELECT * FROM cameras WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return CameraResponse(**dict(camera))


@router.put("/{camera_id}")
def update_camera(
    camera_id: int, body: CameraUpdate, _: CurrentUser = Depends(require_admin)
) -> CameraResponse:
    source_path, tz = _validate_source(body.source_path, body.timezone.strip())
    try:
        pattern = validate_pattern(body.directory_pattern)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))
    conn = get_db()
    previous = conn.execute("SELECT * FROM cameras WHERE id = ?", (camera_id,)).fetchone()
    if not previous:
        conn.close()
        raise HTTPException(status_code=404, detail="Camera not found")
    cache_changed = any((
        previous["source_path"] != source_path,
        previous["timezone"] != tz,
        previous["indexing_mode"] != body.indexing_mode,
        previous["directory_pattern"] != pattern,
    ))
    thumbnails = []
    if cache_changed:
        thumbnails = [
            row["thumbnail_path"] for row in conn.execute(
                "SELECT thumbnail_path FROM recordings WHERE camera_id = ? AND thumbnail_path IS NOT NULL",
                (camera_id,),
            ).fetchall()
        ]
        conn.execute("DELETE FROM recordings WHERE camera_id = ?", (camera_id,))
        conn.execute("DELETE FROM partitions WHERE camera_id = ?", (camera_id,))
    cur = conn.execute(
        "UPDATE cameras SET name = ?, source_path = ?, timezone = ?, indexing_mode = ?, directory_pattern = ?, "
        "source_status = 'unknown', source_error = NULL WHERE id = ?",
        (body.name.strip(), source_path, tz, body.indexing_mode, pattern, camera_id),
    )
    if cur.rowcount == 0:
        conn.close()
        raise HTTPException(status_code=404, detail="Camera not found")
    conn.commit()
    camera = conn.execute("SELECT * FROM cameras WHERE id = ?", (camera_id,)).fetchone()
    conn.close()
    for thumbnail in thumbnails:
        try:
            os.unlink(thumbnail)
        except OSError:
            pass
    return CameraResponse(**dict(camera))


@router.get("/{camera_id}")
def get_camera(camera_id: int, _: CurrentUser = Depends(require_admin)) -> CameraResponse:
    conn = get_db()
    row = conn.execute("SELECT * FROM cameras WHERE id = ?", (camera_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Camera not found")
    return CameraResponse(**dict(row))


@router.delete("/{camera_id}")
def delete_camera(camera_id: int, _: CurrentUser = Depends(require_admin)):
    from ctv_server.scan_service import is_scanning

    if is_scanning(camera_id):
        raise HTTPException(status_code=409, detail="Attendi la fine della scansione prima di eliminare la telecamera")
    conn = get_db()
    cur = conn.execute("DELETE FROM cameras WHERE id = ?", (camera_id,))
    conn.commit()
    conn.close()
    if cur.rowcount == 0:
        raise HTTPException(status_code=404, detail="Camera not found")
    return {"deleted": camera_id}
