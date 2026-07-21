from typing import Optional
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from ctv_server.db import RECORDING_TIME_DELTA_SQL, get_db, recording_time_delta

router = APIRouter(prefix="/api/recordings", tags=["recordings"])


def _public_recording(row) -> dict:
    allowed = (
        "id", "camera_id", "filename", "start_ts", "end_ts", "duration",
        "codec", "resolution", "fps", "size", "media_kind", "availability",
    )
    result = {key: row[key] for key in allowed if key in row.keys()}
    offset = recording_time_delta(row)
    if "start_ts" in result:
        result["start_ts"] += offset
    if result.get("end_ts") is not None:
        result["end_ts"] += offset
    return result


@router.get("")
def list_recordings(
    camera_id: Optional[int] = None,
    from_ts: Optional[float] = Query(None, alias="from"),
    to_ts: Optional[float] = Query(None, alias="to"),
    limit: int = 100,
    offset: int = 0,
):
    conn = get_db()
    query = "SELECT r.*, c.time_offset_seconds FROM recordings r JOIN cameras c ON c.id = r.camera_id WHERE r.availability = 'available'"
    params: list = []

    if camera_id is not None:
        query += " AND r.camera_id = ?"
        params.append(camera_id)
    if from_ts is not None:
        query += f" AND COALESCE(r.end_ts, r.start_ts) + {RECORDING_TIME_DELTA_SQL} >= ?"
        params.append(from_ts)
    if to_ts is not None:
        query += f" AND r.start_ts + {RECORDING_TIME_DELTA_SQL} <= ?"
        params.append(to_ts)

    query += f" ORDER BY r.start_ts + {RECORDING_TIME_DELTA_SQL} LIMIT ? OFFSET ?"
    params.extend([limit, offset])

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [_public_recording(row) for row in rows]


@router.get("/{recording_id}")
def get_recording(recording_id: int):
    conn = get_db()
    row = conn.execute(
        "SELECT r.*, c.time_offset_seconds FROM recordings r JOIN cameras c ON c.id = r.camera_id "
        "WHERE r.id = ? AND r.availability = 'available'", (recording_id,)
    ).fetchone()
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
