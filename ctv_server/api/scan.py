import logging

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException

from ctv_server.auth import CurrentUser, require_admin
from ctv_server.db import get_db
from ctv_server.operations import index_generation
from ctv_server.scan_service import is_scanning, run_camera_scan

log = logging.getLogger("ctv.scan")
router = APIRouter(prefix="/api/scan", tags=["scan"])


@router.post("/{camera_id}", status_code=202)
def scan_camera(
    camera_id: int,
    background: BackgroundTasks,
    _: CurrentUser = Depends(require_admin),
):
    conn = get_db()
    cam = conn.execute("SELECT id, source_path, indexing_mode FROM cameras WHERE id = ?", (camera_id,)).fetchone()
    conn.close()
    if not cam:
        raise HTTPException(status_code=404, detail="Camera not found")
    if cam["indexing_mode"] == "partitioned":
        raise HTTPException(status_code=400, detail="La sorgente partizionata viene caricata dalla timeline")
    if is_scanning(camera_id):
        raise HTTPException(status_code=409, detail="Scan already running")
    background.add_task(run_camera_scan, camera_id, cam["source_path"], index_generation())
    return {"status": "started", "camera_id": camera_id}


@router.post("", status_code=202)
def scan_all(
    background: BackgroundTasks,
    _: CurrentUser = Depends(require_admin),
):
    conn = get_db()
    cameras = conn.execute("SELECT id, source_path FROM cameras WHERE indexing_mode = 'full'").fetchall()
    conn.close()
    if not cameras:
        return {"status": "started", "cameras": 0, "busy": 0}
    queued = 0
    for cam in cameras:
        if not is_scanning(cam["id"]):
            background.add_task(
                run_camera_scan, cam["id"], cam["source_path"], index_generation()
            )
            queued += 1
    log.info("Scan all queued: %d of %d cameras", queued, len(cameras))
    return {"status": "started", "cameras": queued, "busy": len(cameras) - queued}
