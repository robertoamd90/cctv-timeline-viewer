from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from ctv_server.db import get_db

router = APIRouter(prefix="/api/recordings", tags=["recordings"])


def _public_recording(row) -> dict:
    allowed = (
        "id", "camera_id", "filename", "start_ts", "end_ts", "duration",
        "codec", "resolution", "fps", "size", "media_kind", "availability",
    )
    return {key: row[key] for key in allowed if key in row.keys()}


@router.get("")
def list_recordings(
    camera_id: Optional[int] = None,
    from_ts: Optional[float] = Query(None, alias="from"),
    to_ts: Optional[float] = Query(None, alias="to"),
    limit: int = 100,
    offset: int = 0,
):
    conn = get_db()
    query = "SELECT * FROM recordings WHERE availability = 'available'"
    params: list = []

    if camera_id is not None:
        query += " AND camera_id = ?"
        params.append(camera_id)
    if from_ts is not None:
        query += " AND COALESCE(end_ts, start_ts) >= ?"
        params.append(from_ts)
    if to_ts is not None:
        query += " AND start_ts <= ?"
        params.append(to_ts)

    query += " ORDER BY start_ts LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [_public_recording(row) for row in rows]


@router.get("/{recording_id}")
def get_recording(recording_id: int):
    conn = get_db()
    row = conn.execute("SELECT * FROM recordings WHERE id = ? AND availability = 'available'", (recording_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404)
    return _public_recording(row)


@router.get("/{recording_id}/thumbnail")
def get_thumbnail(recording_id: int):
    from ctv_server.thumbnailer import THUMBNAIL_DIR
    import os
    path = os.path.join(THUMBNAIL_DIR, f"{recording_id}.jpg")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Thumbnail not yet generated")
    return FileResponse(path, media_type="image/jpeg")
