import asyncio
import json
from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from ctv_server.auth import current_user

router = APIRouter(prefix="/api/events", tags=["events"])

# Coda globale per eventi SSE
_listeners: list[asyncio.Queue] = []


def _sanitize(value):
    if isinstance(value, dict):
        result = {}
        for key, item in value.items():
            if key in {"path", "source_path", "thumbnail_path", "hash", "metadata"}:
                continue
            if key == "error" and item:
                result[key] = "Source unavailable"
            else:
                result[key] = _sanitize(item)
        return result
    if isinstance(value, list):
        return [_sanitize(item) for item in value]
    return value


def emit(event_type: str, data: dict):
    """Invia un evento a tutti i listener SSE connessi."""
    for q in _listeners:
        try:
            q.put_nowait((event_type, data))
        except asyncio.QueueFull:
            pass


async def _event_stream(request: Request):
    q: asyncio.Queue = asyncio.Queue(maxsize=256)
    user = current_user(request)
    _listeners.append(q)
    try:
        # Evento iniziale di connessione
        yield "event: connected\ndata: {}\n\n"
        while True:
            disconnected = await request.is_disconnected()
            if disconnected:
                break
            try:
                event_type, data = await asyncio.wait_for(q.get(), timeout=15.0)
                payload = data if user.is_admin else _sanitize(data)
                yield f"event: {event_type}\ndata: {json.dumps(payload)}\n\n"
            except asyncio.TimeoutError:
                yield ": keepalive\n\n"
    finally:
        _listeners.remove(q)


@router.get("")
async def events_stream(request: Request):
    """SSE endpoint per eventi realtime."""
    return StreamingResponse(
        _event_stream(request),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
