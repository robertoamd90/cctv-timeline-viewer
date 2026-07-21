import math
from typing import Optional
from fastapi import APIRouter, BackgroundTasks, HTTPException, Query
from ctv_server.db import RECORDING_TIME_DELTA_SQL, get_db, recording_time_delta
from ctv_server.partition_service import prepare_partitions, run_partition_scan
from ctv_server.partitioner import dates_for_range, partition_key

router = APIRouter(prefix="/api/timeline", tags=["timeline"])


def _camera_ids(value: Optional[str]) -> list[int]:
    return [int(item) for item in (value or "").split(",") if item.strip().isdigit()]


@router.post("/prepare", status_code=202)
def prepare_timeline(
    background: BackgroundTasks,
    from_ts: float = Query(..., alias="from"),
    to_ts: float = Query(..., alias="to"),
    camera_ids: Optional[str] = Query(None, alias="cameras"),
):
    if not math.isfinite(from_ts) or not math.isfinite(to_ts) or to_ts <= from_ts:
        raise HTTPException(status_code=422, detail="Invalid timeline range")
    if to_ts - from_ts > 172800:
        raise HTTPException(status_code=422, detail="Timeline preparation is limited to 48 hours")
    ids = _camera_ids(camera_ids)
    if not ids:
        conn = get_db()
        ids = [row["id"] for row in conn.execute("SELECT id FROM cameras").fetchall()]
        conn.close()
    jobs = prepare_partitions(ids, from_ts, to_ts)
    for job in jobs:
        background.add_task(run_partition_scan, job["camera_id"], job["key"], job["path"])
    return {"status": "queued", "partitions": len(jobs)}


@router.get("/bounds")
def get_timeline_bounds():
    conn = get_db()
    row = conn.execute(
        f"SELECT MIN(r.start_ts + {RECORDING_TIME_DELTA_SQL}) AS first, "
        f"MAX(COALESCE(r.end_ts, r.start_ts) + {RECORDING_TIME_DELTA_SQL}) AS last "
        "FROM recordings r JOIN cameras c ON c.id = r.camera_id "
        "WHERE r.availability = 'available' "
        "AND (c.indexing_mode = 'full' OR r.partition_key IS NOT NULL)"
    ).fetchone()
    conn.close()
    return {"first": row["first"], "last": row["last"]}


@router.get("")
def get_timeline(
    from_ts: Optional[float] = Query(None, alias="from"),
    to_ts: Optional[float] = Query(None, alias="to"),
    camera_ids: Optional[str] = Query(None, alias="cameras"),
):
    """Restituisce i segmenti della timeline raggruppati per telecamera."""
    conn = get_db()

    # Se nessun range specificato, usa i limiti dei dati
    if from_ts is None or to_ts is None:
        row = conn.execute(f"""
            SELECT MIN(r.start_ts + {RECORDING_TIME_DELTA_SQL}) as mn,
                   MAX(COALESCE(r.end_ts, r.start_ts) + {RECORDING_TIME_DELTA_SQL}) as mx
            FROM recordings r JOIN cameras c ON c.id = r.camera_id
            WHERE r.availability = 'available'
              AND (c.indexing_mode = 'full' OR r.partition_key IS NOT NULL)
        """).fetchone()
        if from_ts is None:
            from_ts = row["mn"] or 0
        if to_ts is None:
            to_ts = row["mx"] or (from_ts + 86400)

    selected_ids = _camera_ids(camera_ids)
    camera_query = "SELECT * FROM cameras"
    camera_params: list = []
    if selected_ids:
        camera_query += " WHERE id IN (" + ",".join("?" for _ in selected_ids) + ")"
        camera_params.extend(selected_ids)
    camera_query += " ORDER BY name"
    selected_cameras = conn.execute(camera_query, camera_params).fetchall()

    cameras_map: dict = {}
    for camera in selected_cameras:
        state = "ready" if camera["indexing_mode"] == "full" else "unknown"
        progress_done = progress_total = 0
        if camera["indexing_mode"] == "partitioned":
            offset = camera["time_offset_seconds"] or 0
            keys = [
                partition_key(day)
                for day in dates_for_range(from_ts - offset, to_ts - offset, camera["timezone"])
            ]
            placeholders = ",".join("?" for _ in keys)
            partitions = conn.execute(
                f"SELECT status, progress_done, progress_total FROM partitions "
                f"WHERE camera_id = ? AND partition_key IN ({placeholders})",
                (camera["id"], *keys),
            ).fetchall() if keys else []
            statuses = [row["status"] for row in partitions]
            progress_done = sum(row["progress_done"] for row in partitions)
            progress_total = sum(row["progress_total"] for row in partitions)
            if any(status == "scanning" for status in statuses):
                state = "scanning"
            elif any(status == "error" for status in statuses):
                state = "error"
            elif statuses and all(status == "missing" for status in statuses):
                state = "missing"
            elif statuses and all(status in {"ready", "missing"} for status in statuses):
                state = "ready"
        cameras_map[camera["id"]] = {
            "camera_id": camera["id"],
            "camera_name": camera["name"],
            "partition_status": state,
            "progress_done": progress_done,
            "progress_total": progress_total,
            "segments": [],
        }

    query = f"""SELECT r.*, c.name as camera_name, c.time_offset_seconds
               FROM recordings r JOIN cameras c ON r.camera_id = c.id
               WHERE r.availability = 'available'
                 AND (c.indexing_mode = 'full' OR r.partition_key IS NOT NULL)
                 AND COALESCE(r.end_ts, r.start_ts) + {RECORDING_TIME_DELTA_SQL} >= ?
                 AND r.start_ts + {RECORDING_TIME_DELTA_SQL} <= ?"""
    params: list = [from_ts, to_ts]

    if selected_ids:
        placeholders = ",".join("?" * len(selected_ids))
        query += f" AND r.camera_id IN ({placeholders})"
        params.extend(selected_ids)

    query += " ORDER BY c.name, r.start_ts"
    rows = conn.execute(query, params).fetchall()

    # Aggiunge i segmenti alle righe camera gia create.
    for r in rows:
        d = dict(r)
        cid = d["camera_id"]
        if cid not in cameras_map:
            continue
        offset = recording_time_delta(r)
        cameras_map[cid]["segments"].append({
            "id": d["id"],
            "filename": d["filename"],
            "start_ts": d["start_ts"] + offset,
            "end_ts": d["end_ts"] + offset if d["end_ts"] is not None else None,
            "duration": d["duration"],
            "media_kind": d["media_kind"],
            "has_thumbnail": d["thumbnail_path"] is not None,
        })

    conn.close()
    return {
        "from": from_ts,
        "to": to_ts,
        "cameras": list(cameras_map.values()),
    }
