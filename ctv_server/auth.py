import asyncio
import json
import logging
import os
import time
from dataclasses import dataclass

from fastapi import HTTPException, Request

from ctv_server.config import is_home_assistant

log = logging.getLogger("ctv.auth")

ROLE_CACHE_SECONDS = 60
ROLE_STALE_SECONDS = 900
ADMIN_GROUP_ID = "system-admin"


@dataclass(frozen=True)
class CurrentUser:
    id: str
    name: str
    display_name: str
    is_admin: bool
    role_resolved: bool


_role_cache: dict[str, bool] = {}
_role_cache_time = 0.0
_role_lock = asyncio.Lock()


async def _receive_json(socket) -> dict:
    return json.loads(await asyncio.wait_for(socket.recv(), timeout=5))


async def _fetch_roles() -> dict[str, bool]:
    token = os.environ.get("SUPERVISOR_TOKEN", "")
    if not token:
        raise RuntimeError("SUPERVISOR_TOKEN is not available")

    import websockets

    url = os.environ.get("CTV_HA_WEBSOCKET_URL", "ws://supervisor/core/websocket")
    async with websockets.connect(url, open_timeout=5, close_timeout=2) as socket:
        required = await _receive_json(socket)
        if required.get("type") != "auth_required":
            raise RuntimeError("Unexpected Home Assistant authentication response")
        await socket.send(json.dumps({"type": "auth", "access_token": token}))
        authenticated = await _receive_json(socket)
        if authenticated.get("type") != "auth_ok":
            raise RuntimeError("Home Assistant rejected the app token")
        await socket.send(json.dumps({"id": 1, "type": "config/auth/list"}))
        response = await _receive_json(socket)
        if not response.get("success"):
            raise RuntimeError(response.get("error", {}).get("message", "Unable to list users"))
        return {
            user["id"]: ADMIN_GROUP_ID in user.get("group_ids", [])
            for user in response.get("result", [])
            if user.get("id") and user.get("is_active", True)
        }


async def resolve_admin(user_id: str) -> tuple[bool, bool]:
    global _role_cache, _role_cache_time
    now = time.monotonic()
    if _role_cache and now - _role_cache_time < ROLE_CACHE_SECONDS:
        return _role_cache.get(user_id, False), True

    async with _role_lock:
        now = time.monotonic()
        if _role_cache and now - _role_cache_time < ROLE_CACHE_SECONDS:
            return _role_cache.get(user_id, False), True
        try:
            roles = await _fetch_roles()
        except Exception as exc:
            log.warning("Unable to refresh Home Assistant user roles: %s", exc)
            if _role_cache and now - _role_cache_time < ROLE_STALE_SECONDS:
                return _role_cache.get(user_id, False), True
            return False, False
        _role_cache = roles
        _role_cache_time = now
        return roles.get(user_id, False), True


async def user_from_request(request: Request) -> CurrentUser:
    if not is_home_assistant():
        return CurrentUser("standalone", "Standalone", "Standalone", True, True)

    user_id = request.headers.get("X-Remote-User-Id", "").strip()
    if not user_id:
        raise HTTPException(status_code=401, detail="Missing Home Assistant ingress identity")
    is_admin, resolved = await resolve_admin(user_id)
    return CurrentUser(
        id=user_id,
        name=request.headers.get("X-Remote-User-Name", "").strip(),
        display_name=request.headers.get("X-Remote-User-Display-Name", "").strip(),
        is_admin=is_admin,
        role_resolved=resolved,
    )


def current_user(request: Request) -> CurrentUser:
    user = getattr(request.state, "ctv_user", None)
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")
    return user


def require_admin(request: Request) -> CurrentUser:
    user = current_user(request)
    if not user.role_resolved:
        raise HTTPException(status_code=503, detail="Home Assistant user roles are unavailable")
    if not user.is_admin:
        raise HTTPException(status_code=403, detail="Administrator access required")
    return user


def reset_role_cache() -> None:
    global _role_cache, _role_cache_time
    _role_cache = {}
    _role_cache_time = 0.0
