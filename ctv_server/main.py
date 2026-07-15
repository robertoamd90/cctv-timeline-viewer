import os
import asyncio
import logging
import mimetypes
import time
from contextlib import asynccontextmanager
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from ctv_server.db import init_db, get_db
from ctv_server.api import cameras, recordings, scan, timeline, search, events, system
from ctv_server.auth import user_from_request
from ctv_server.config import is_home_assistant, trusted_ingress_proxies

# ── Logging ──
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("ctv")


class VideoFileResponse(FileResponse):
    # Larger sequential reads reduce SMB and proxy overhead during multi-camera fast playback.
    chunk_size = 1024 * 1024


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown events."""
    log.info("Initializing database…")
    init_db()
    _autodiscover_test_dir()
    # Avvia scansione periodica in background
    _watcher_task = asyncio.create_task(_background_watcher())
    log.info("CTV server ready")
    yield
    _watcher_task.cancel()
    log.info("CTV server shutting down")


app = FastAPI(
    title="CTV — CCTV Timeline Viewer",
    docs_url=None if is_home_assistant() else "/docs",
    redoc_url=None if is_home_assistant() else "/redoc",
    lifespan=lifespan,
)


@app.middleware("http")
async def deployment_security(request, call_next):
    if is_home_assistant():
        client_host = request.client.host if request.client else ""
        if client_host not in trusted_ingress_proxies():
            return JSONResponse(status_code=403, content={"detail": "Ingress proxy required"})
        if request.url.path != "/api/health":
            try:
                request.state.ctv_user = await user_from_request(request)
            except HTTPException as exc:
                return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})
    else:
        request.state.ctv_user = await user_from_request(request)
    return await call_next(request)

cors_origins = [value.strip() for value in os.environ.get("CTV_CORS_ORIGINS", "").split(",") if value.strip()]
if cors_origins:
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_methods=["GET", "POST", "PUT", "DELETE"],
        allow_headers=["Content-Type", "Authorization"],
    )

# ── Routers ──
app.include_router(cameras.router)
app.include_router(recordings.router)
app.include_router(scan.router)
app.include_router(timeline.router)
app.include_router(search.router)
app.include_router(events.router)
app.include_router(system.router)


@app.get("/api/health", tags=["system"])
def health():
    conn = get_db()
    cameras = conn.execute(
        "SELECT source_status, COUNT(*) AS count FROM cameras GROUP BY source_status"
    ).fetchall()
    conn.execute("SELECT 1").fetchone()
    conn.close()
    by_status = {row["source_status"]: row["count"] for row in cameras}
    return {
        "status": "ok" if not by_status.get("offline") else "degraded",
        "database": "ok",
        "sources": by_status,
    }


# ── Video serving ──
@app.get("/video/{recording_id}")
def serve_video(recording_id: int):
    conn = get_db()
    row = conn.execute("SELECT path, availability FROM recordings WHERE id = ?", (recording_id,)).fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Recording not found")
    if row["availability"] != "available":
        raise HTTPException(status_code=410, detail="Recording no longer available")
    filepath = row["path"]
    if not os.path.isfile(filepath):
        raise HTTPException(status_code=404, detail="File not found on disk")
    # FileResponse gestisce nativamente i range request (Content-Range)
    media_type = mimetypes.guess_type(filepath)[0] or "application/octet-stream"
    return VideoFileResponse(filepath, media_type=media_type)


# ── Frontend statico ──
web_dir = os.path.join(os.path.dirname(__file__), "..", "ctv_web")
if os.path.isdir(web_dir):
    app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")
else:
    log.warning("ctv_web directory not found — frontend not served")


# ═══════════════════════════════════════════════════════════════
# Auto-discovery cartella test (solo prima esecuzione)
# ═══════════════════════════════════════════════════════════════

def _autodiscover_test_dir():
    """Se non ci sono camere configurate, scansiona ./test
    e crea automaticamente una camera per ogni sottocartella."""
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) as n FROM cameras").fetchone()["n"]
    conn.close()
    if count > 0:
        log.info("Cameras already configured, skipping auto-discovery")
        return

    test_dir = os.path.join(os.path.dirname(__file__), "..", "test")
    if not os.path.isdir(test_dir):
        log.info("No test/ directory found, skipping auto-discovery")
        return

    log.info("Auto-discovering cameras from test/ directory…")

    conn = get_db()
    for entry in sorted(os.listdir(test_dir)):
        subdir = os.path.abspath(os.path.join(test_dir, entry))
        if os.path.isdir(subdir):
            conn.execute(
                "INSERT INTO cameras (name, source_path, timezone) VALUES (?, ?, ?)",
                (entry, subdir, "Europe/Rome"),
            )
            log.info("  Created camera: %s → %s", entry, subdir)
    conn.commit()

    cams = conn.execute("SELECT id, source_path FROM cameras").fetchall()
    conn.close()

    log.info("Auto-discovery complete; watcher will index the new cameras")


# ═══════════════════════════════════════════════════════════════
# Background watcher: riscansione periodica per nuovi file
# ═══════════════════════════════════════════════════════════════

_WATCHER_INTERVAL = int(os.environ.get("CTV_WATCHER_SECONDS", "60"))

async def _background_watcher():
    """Aggiorna solo le partizioni usate di recente, mai l'intero archivio."""
    await asyncio.sleep(10)  # aspetta 10s dopo lo startup prima della prima scansione
    from ctv_server.partition_service import run_partition_scan

    while True:
        try:
            conn = get_db()
            active_since = time.time() - max(_WATCHER_INTERVAL * 3, 300)
            partitions = conn.execute("""
                SELECT camera_id, partition_key, path FROM partitions
                WHERE last_requested >= ?
            """, (active_since,)).fetchall()
            conn.close()
            for partition in partitions:
                await asyncio.to_thread(
                    run_partition_scan,
                    partition["camera_id"],
                    partition["partition_key"],
                    partition["path"],
                )
        except Exception as exc:
            log.error("Watcher error: %s", exc)
        await asyncio.sleep(_WATCHER_INTERVAL)
