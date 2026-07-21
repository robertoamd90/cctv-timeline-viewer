from typing import Optional
from fastapi import APIRouter, Query
from ctv_server.db import RECORDING_TIME_DELTA_SQL, get_db, recording_time_delta

router = APIRouter(prefix="/api/search", tags=["search"])


def _public_result(row) -> dict:
    offset = recording_time_delta(row)
    return {
        "id": row["id"],
        "camera_id": row["camera_id"],
        "camera_name": row["camera_name"],
        "filename": row["filename"],
        "start_ts": row["start_ts"] + offset,
        "end_ts": row["end_ts"] + offset if row["end_ts"] is not None else None,
        "duration": row["duration"],
    }


@router.get("")
def search(
    q: str = "",
    camera_id: Optional[int] = None,
    from_ts: Optional[float] = Query(None, alias="from"),
    to_ts: Optional[float] = Query(None, alias="to"),
    min_duration: Optional[float] = None,
    limit: int = 100,
):
    """Cerca registrazioni per nome file, camera, intervallo, durata."""
    conn = get_db()
    query = "SELECT r.*, c.name as camera_name, c.time_offset_seconds FROM recordings r JOIN cameras c ON r.camera_id = c.id WHERE r.availability = 'available'"
    params: list = []

    if q:
        query += " AND (r.filename LIKE ? OR c.name LIKE ?)"
        params.extend([f"%{q}%", f"%{q}%"])
    if camera_id is not None:
        query += " AND r.camera_id = ?"
        params.append(camera_id)
    if from_ts is not None:
        query += f" AND r.end_ts + {RECORDING_TIME_DELTA_SQL} >= ?"
        params.append(from_ts)
    if to_ts is not None:
        query += f" AND r.start_ts + {RECORDING_TIME_DELTA_SQL} <= ?"
        params.append(to_ts)
    if min_duration is not None:
        query += " AND r.duration >= ?"
        params.append(min_duration)

    query += f" ORDER BY r.start_ts + {RECORDING_TIME_DELTA_SQL} DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(query, params).fetchall()
    conn.close()
    return [_public_result(row) for row in rows]
