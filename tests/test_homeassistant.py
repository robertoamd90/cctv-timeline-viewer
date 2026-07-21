import asyncio
import os
import tempfile
import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import BackgroundTasks, HTTPException
from starlette.requests import Request

from ctv_server import auth
from ctv_server import db
from ctv_server.api.cameras import list_cameras, update_camera
from ctv_server.api.events import _sanitize
from ctv_server.api.recordings import _public_recording
from ctv_server.api.system import list_source_directories
from ctv_server.api.timeline import prepare_timeline
from ctv_server.auth import CurrentUser, require_admin, user_from_request
from ctv_server.config import path_within_source_roots, source_roots
from ctv_server.models import CameraUpdate


def make_request(headers=None, user=None):
    raw_headers = [
        (key.lower().encode("latin-1"), value.encode("latin-1"))
        for key, value in (headers or {}).items()
    ]
    request = Request({
        "type": "http",
        "method": "GET",
        "path": "/",
        "headers": raw_headers,
        "client": ("172.30.32.2", 1234),
        "server": ("ctv", 8000),
        "scheme": "http",
    })
    if user is not None:
        request.state.ctv_user = user
    return request


class AuthorizationTests(unittest.TestCase):
    def tearDown(self):
        auth.reset_role_cache()

    def test_admin_dependency_rejects_viewer(self):
        viewer = CurrentUser("viewer", "viewer", "Viewer", False, True)
        with self.assertRaises(HTTPException) as raised:
            require_admin(make_request(user=viewer))
        self.assertEqual(raised.exception.status_code, 403)

    def test_admin_dependency_fails_closed_when_roles_are_unavailable(self):
        unresolved = CurrentUser("admin", "admin", "Admin", False, False)
        with self.assertRaises(HTTPException) as raised:
            require_admin(make_request(user=unresolved))
        self.assertEqual(raised.exception.status_code, 503)

    def test_ingress_identity_uses_home_assistant_role(self):
        request = make_request({
            "X-Remote-User-Id": "abc",
            "X-Remote-User-Name": "roberto",
            "X-Remote-User-Display-Name": "Roberto",
        })
        with patch.dict(os.environ, {"CTV_DEPLOYMENT": "homeassistant"}, clear=False), \
             patch("ctv_server.auth.resolve_admin", new=AsyncMock(return_value=(True, True))):
            user = asyncio.run(user_from_request(request))
        self.assertTrue(user.is_admin)
        self.assertEqual(user.id, "abc")

    def test_admin_only_ingress_trusts_supervisor_authorization(self):
        request = make_request({
            "X-Remote-User-Id": "abc",
            "X-Remote-User-Name": "roberto",
        })
        with patch.dict(os.environ, {
            "CTV_DEPLOYMENT": "homeassistant",
            "CTV_HA_ADMIN_ONLY": "1",
        }, clear=False), patch(
            "ctv_server.auth.resolve_admin", new=AsyncMock()
        ) as resolve:
            user = asyncio.run(user_from_request(request))
        self.assertTrue(user.is_admin)
        self.assertTrue(user.role_resolved)
        resolve.assert_not_awaited()

    def test_missing_ingress_identity_is_rejected(self):
        with patch.dict(os.environ, {"CTV_DEPLOYMENT": "homeassistant"}, clear=False):
            with self.assertRaises(HTTPException) as raised:
                asyncio.run(user_from_request(make_request()))
        self.assertEqual(raised.exception.status_code, 401)


class SourceBrowserTests(unittest.TestCase):
    def test_browser_is_confined_to_configured_root(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            os.mkdir(os.path.join(root, "Garage"))
            admin = CurrentUser("admin", "admin", "Admin", True, True)
            with patch.dict(os.environ, {"CTV_SOURCE_ROOTS": root}, clear=False):
                self.assertEqual(source_roots(), (os.path.realpath(root),))
                self.assertTrue(path_within_source_roots(os.path.join(root, "Garage")))
                self.assertFalse(path_within_source_roots(outside))
                result = list_source_directories(None, root, admin)
                self.assertEqual([entry["name"] for entry in result["entries"]], ["Garage"])
                with self.assertRaises(HTTPException) as raised:
                    list_source_directories(None, outside, admin)
            self.assertEqual(raised.exception.status_code, 403)

    def test_symlink_cannot_escape_source_root(self):
        with tempfile.TemporaryDirectory() as root, tempfile.TemporaryDirectory() as outside:
            os.symlink(outside, os.path.join(root, "escape"))
            with patch.dict(os.environ, {"CTV_SOURCE_ROOTS": root}, clear=False):
                self.assertFalse(path_within_source_roots(os.path.join(root, "escape")))


class PublicApiTests(unittest.TestCase):
    def test_viewer_camera_response_hides_source_path(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = db.DB_PATH
            db.DB_PATH = os.path.join(tmp, "ctv.db")
            try:
                db.init_db()
                conn = db.get_db()
                conn.execute(
                    "INSERT INTO cameras (name, source_path, timezone) VALUES (?, ?, ?)",
                    ("Garage", "/media/private/Garage", "UTC"),
                )
                conn.commit()
                conn.close()
                viewer = CurrentUser("viewer", "viewer", "Viewer", False, True)
                cameras = list_cameras(make_request(user=viewer))
            finally:
                db.DB_PATH = original
            self.assertEqual(cameras[0]["name"], "Garage")
            self.assertNotIn("source_path", cameras[0])

    def test_recording_response_does_not_expose_filesystem_data(self):
        result = _public_recording({
            "id": 1,
            "camera_id": 2,
            "filename": "clip.mp4",
            "start_ts": 1.0,
            "end_ts": 2.0,
            "duration": 1.0,
            "path": "/media/private/clip.mp4",
            "hash": "secret",
            "metadata": "{}",
        })
        self.assertEqual(result["filename"], "clip.mp4")
        self.assertNotIn("path", result)
        self.assertNotIn("hash", result)
        self.assertNotIn("metadata", result)

    def test_viewer_event_hides_paths_and_detailed_errors(self):
        result = _sanitize({
            "camera_id": 1,
            "path": "/media/private/Garage",
            "error": "Permission denied: /media/private/Garage",
        })
        self.assertNotIn("path", result)
        self.assertEqual(result["error"], "Source unavailable")

    def test_timeline_prepare_is_limited_to_48_hours(self):
        with self.assertRaises(HTTPException) as raised:
            prepare_timeline(BackgroundTasks(), 0, 172801, None)
        self.assertEqual(raised.exception.status_code, 422)

    def test_updating_camera_offset_shifts_existing_recordings(self):
        with tempfile.TemporaryDirectory() as tmp:
            original = db.DB_PATH
            db.DB_PATH = os.path.join(tmp, "ctv.db")
            try:
                db.init_db()
                conn = db.get_db()
                camera_id = conn.execute(
                    "INSERT INTO cameras (name, source_path, timezone) VALUES (?, ?, ?)",
                    ("Garage", tmp, "UTC"),
                ).lastrowid
                conn.execute(
                    "INSERT INTO recordings (camera_id, path, filename, start_ts, end_ts) "
                    "VALUES (?, ?, ?, ?, ?)",
                    (camera_id, os.path.join(tmp, "clip.mp4"), "clip.mp4", 100, 110),
                )
                conn.commit()
                conn.close()
                admin = CurrentUser("admin", "admin", "Admin", True, True)
                result = update_camera(camera_id, CameraUpdate(
                    name="Garage", source_path=tmp, timezone="UTC", time_offset_seconds=-5,
                    indexing_mode="partitioned", directory_pattern="{YYYY}/{MM}/{DD}",
                ), admin)
                conn = db.get_db()
                recording = conn.execute(
                    "SELECT start_ts, end_ts FROM recordings WHERE camera_id = ?", (camera_id,)
                ).fetchone()
                conn.close()
            finally:
                db.DB_PATH = original
            self.assertEqual(result.time_offset_seconds, -5)
            self.assertEqual((recording["start_ts"], recording["end_ts"]), (95, 105))


if __name__ == "__main__":
    unittest.main()
