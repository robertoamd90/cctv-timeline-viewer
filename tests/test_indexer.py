import os
import sqlite3
import tempfile
import threading
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import patch

from ctv_server import db
from ctv_server.api.recordings import list_recordings
from ctv_server.indexer import index_camera
from ctv_server.scan_service import run_camera_scan


class IndexerTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.original_db = db.DB_PATH
        db.DB_PATH = str(self.root / "ctv.db")
        db.init_db()
        conn = db.get_db()
        self.camera_id = conn.execute(
            "INSERT INTO cameras (name, source_path, timezone) VALUES (?, ?, 'UTC')",
            ("Test", str(self.root)),
        ).lastrowid
        conn.commit()
        conn.close()

    def tearDown(self):
        db.DB_PATH = self.original_db
        self.tempdir.cleanup()

    def test_reindex_preserves_id_and_marks_removed_file_missing(self):
        media = self.root / "CAM_20260706002901.mp4"
        media.write_bytes(b"not-a-real-video")
        self.assertEqual(index_camera(self.camera_id, str(self.root))["new"], 1)

        conn = db.get_db()
        first = conn.execute("SELECT id FROM recordings").fetchone()["id"]
        conn.close()

        media.write_bytes(b"changed-media")
        result = index_camera(self.camera_id, str(self.root))
        conn = db.get_db()
        changed = conn.execute("SELECT id, availability FROM recordings").fetchone()
        conn.close()
        self.assertEqual(result["updated"], 1)
        self.assertEqual(changed["id"], first)
        self.assertEqual(changed["availability"], "available")

        media.unlink()
        self.assertEqual(index_camera(self.camera_id, str(self.root))["missing"], 1)
        conn = db.get_db()
        availability = conn.execute("SELECT availability FROM recordings").fetchone()[0]
        conn.close()
        self.assertEqual(availability, "missing")

    def test_unavailable_source_does_not_mark_recordings_missing(self):
        media = self.root / "CAM_20260706002901.mp4"
        media.write_bytes(b"media")
        index_camera(self.camera_id, str(self.root))
        with self.assertRaises(FileNotFoundError):
            index_camera(self.camera_id, str(self.root / "not-mounted"))
        conn = db.get_db()
        availability = conn.execute("SELECT availability FROM recordings").fetchone()[0]
        conn.close()
        self.assertEqual(availability, "available")

    def test_scan_service_marks_unavailable_mount_offline(self):
        missing_source = str(self.root / "not-mounted")
        conn = db.get_db()
        conn.execute(
            "UPDATE cameras SET source_path = ? WHERE id = ?", (missing_source, self.camera_id)
        )
        conn.commit()
        conn.close()
        result = run_camera_scan(self.camera_id, missing_source)
        conn = db.get_db()
        camera = conn.execute(
            "SELECT source_status, source_error FROM cameras WHERE id = ?", (self.camera_id,)
        ).fetchone()
        conn.close()
        self.assertEqual(result["status"], "error")
        self.assertEqual(camera["source_status"], "offline")
        self.assertIn("Sorgente non disponibile", camera["source_error"])

    def test_image_is_ignored_by_indexer(self):
        image = self.root / "snapshot_20260706002901.jpg"
        image.write_bytes(b"jpeg-placeholder")
        result = index_camera(self.camera_id, str(self.root))
        conn = db.get_db()
        recording = conn.execute("SELECT COUNT(*) FROM recordings WHERE path = ?", (str(image),)).fetchone()[0]
        conn.close()
        self.assertEqual(result["total"], 0)
        self.assertEqual(recording, 0)
        self.assertTrue(image.exists())

    def test_camera_time_offset_is_applied_at_read_time(self):
        media = self.root / "CAM_20260706002901.mp4"
        media.write_bytes(b"video-placeholder")
        conn = db.get_db()
        conn.execute(
            "UPDATE cameras SET time_offset_seconds = -4.5 WHERE id = ?", (self.camera_id,)
        )
        conn.commit()
        conn.close()

        with patch("ctv_server.indexer.get_ffprobe_data", return_value={}):
            index_camera(self.camera_id, str(self.root))

        conn = db.get_db()
        start_ts = conn.execute(
            "SELECT start_ts FROM recordings WHERE camera_id = ?", (self.camera_id,)
        ).fetchone()[0]
        conn.close()
        raw = datetime(2026, 7, 6, 0, 29, 1, tzinfo=timezone.utc).timestamp()
        self.assertEqual(start_ts, raw)
        public = list_recordings(
            camera_id=self.camera_id, from_ts=None, to_ts=None, limit=100, offset=0
        )
        self.assertEqual(public[0]["start_ts"], raw - 4.5)

    def test_queued_scan_ignores_camera_deleted_before_start(self):
        conn = db.get_db()
        conn.execute("DELETE FROM cameras WHERE id = ?", (self.camera_id,))
        conn.commit()
        conn.close()
        result = run_camera_scan(self.camera_id, str(self.root))
        self.assertEqual(result["status"], "removed")
        conn = db.get_db()
        count = conn.execute("SELECT COUNT(*) FROM recordings").fetchone()[0]
        conn.close()
        self.assertEqual(count, 0)

    def test_slow_probe_does_not_hold_database_write_lock(self):
        media = self.root / "CAM_20260706002901.mp4"
        media.write_bytes(b"video-placeholder")
        probe_started = threading.Event()
        release_probe = threading.Event()
        errors = []

        def slow_probe(_path):
            probe_started.set()
            release_probe.wait(timeout=2)
            return {}

        def scan():
            try:
                index_camera(self.camera_id, str(self.root))
            except Exception as exc:
                errors.append(exc)

        with patch("ctv_server.indexer.get_ffprobe_data", side_effect=slow_probe):
            thread = threading.Thread(target=scan)
            thread.start()
            self.assertTrue(probe_started.wait(timeout=1))
            conn = db.get_db()
            conn.execute("UPDATE cameras SET config = '{}' WHERE id = ?", (self.camera_id,))
            conn.commit()
            conn.close()
            release_probe.set()
            thread.join(timeout=3)

        self.assertFalse(thread.is_alive())
        self.assertEqual(errors, [])


class MigrationTests(unittest.TestCase):
    def test_beta_0115_adjusted_timestamps_are_not_offset_twice(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "beta.db")
            conn = sqlite3.connect(path)
            conn.executescript("""
                CREATE TABLE cameras (
                    id INTEGER PRIMARY KEY, name TEXT NOT NULL, source_path TEXT NOT NULL,
                    timezone TEXT DEFAULT 'UTC', time_offset_seconds REAL NOT NULL DEFAULT 0,
                    config TEXT DEFAULT '{}', indexing_mode TEXT NOT NULL DEFAULT 'full',
                    directory_pattern TEXT NOT NULL DEFAULT '{YYYY}/{MM}/{DD}',
                    source_status TEXT NOT NULL DEFAULT 'unknown', source_error TEXT,
                    last_scan_started REAL, last_scan_completed REAL
                );
                CREATE TABLE recordings (
                    id INTEGER PRIMARY KEY, camera_id INTEGER NOT NULL, path TEXT NOT NULL,
                    filename TEXT NOT NULL, start_ts REAL NOT NULL, end_ts REAL, duration REAL,
                    codec TEXT, resolution TEXT, fps REAL, size INTEGER, mtime REAL, hash TEXT,
                    thumbnail_path TEXT, metadata TEXT DEFAULT '{}', partition_key TEXT,
                    media_kind TEXT NOT NULL DEFAULT 'video', availability TEXT NOT NULL DEFAULT 'available',
                    last_seen REAL, UNIQUE(camera_id, path)
                );
                INSERT INTO cameras (id, name, source_path, time_offset_seconds)
                VALUES (1, 'Beta', '.', -5);
                INSERT INTO recordings (camera_id, path, filename, start_ts, end_ts)
                VALUES (1, 'clip.mp4', 'clip.mp4', 95, 105);
            """)
            conn.close()
            original = db.DB_PATH
            try:
                db.DB_PATH = path
                db.init_db()
                result = list_recordings(
                    camera_id=1, from_ts=None, to_ts=None, limit=100, offset=0
                )
                conn = db.get_db()
                applied = conn.execute(
                    "SELECT time_offset_applied_seconds FROM recordings"
                ).fetchone()[0]
                conn.close()
            finally:
                db.DB_PATH = original
            self.assertEqual(applied, -5)
            self.assertEqual((result[0]["start_ts"], result[0]["end_ts"]), (95, 105))

    def test_poc_database_is_migrated(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "legacy.db")
            conn = sqlite3.connect(path)
            conn.executescript("""
                CREATE TABLE cameras (
                    id INTEGER PRIMARY KEY, name TEXT NOT NULL, source_path TEXT NOT NULL,
                    timezone TEXT DEFAULT 'UTC', config TEXT DEFAULT '{}'
                );
                CREATE TABLE recordings (
                    id INTEGER PRIMARY KEY, camera_id INTEGER NOT NULL, path TEXT NOT NULL,
                    filename TEXT NOT NULL, start_ts REAL NOT NULL, end_ts REAL, duration REAL,
                    codec TEXT, resolution TEXT, fps REAL, size INTEGER, hash TEXT,
                    thumbnail_path TEXT, metadata TEXT DEFAULT '{}', UNIQUE(camera_id, path)
                );
            """)
            conn.close()
            original = db.DB_PATH
            try:
                db.DB_PATH = path
                db.init_db()
                conn = db.get_db()
                camera_columns = {row[1] for row in conn.execute("PRAGMA table_info(cameras)")}
                recording_columns = {row[1] for row in conn.execute("PRAGMA table_info(recordings)")}
                conn.close()
            finally:
                db.DB_PATH = original
            self.assertIn("source_status", camera_columns)
            self.assertIn("time_offset_seconds", camera_columns)
            self.assertIn("directory_pattern", camera_columns)
            self.assertIn("availability", recording_columns)
            self.assertIn("media_kind", recording_columns)
            self.assertIn("partition_key", recording_columns)

    def test_existing_image_recordings_are_purged_but_source_files_remain(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "legacy.db")
            source = os.path.join(tmp, "snapshot_20260706002901.jpg")
            thumbnail = os.path.join(tmp, "thumbnail.jpg")
            open(source, "wb").close()
            open(thumbnail, "wb").close()
            conn = sqlite3.connect(path)
            conn.executescript("""
                CREATE TABLE cameras (
                    id INTEGER PRIMARY KEY, name TEXT NOT NULL, source_path TEXT NOT NULL,
                    timezone TEXT DEFAULT 'UTC', config TEXT DEFAULT '{}'
                );
                CREATE TABLE recordings (
                    id INTEGER PRIMARY KEY, camera_id INTEGER NOT NULL, path TEXT NOT NULL,
                    filename TEXT NOT NULL, start_ts REAL NOT NULL, end_ts REAL, duration REAL,
                    codec TEXT, resolution TEXT, fps REAL, size INTEGER, hash TEXT,
                    thumbnail_path TEXT, metadata TEXT DEFAULT '{}', UNIQUE(camera_id, path)
                );
                INSERT INTO cameras (id, name, source_path) VALUES (1, 'Legacy', '.');
            """)
            conn.execute(
                "INSERT INTO recordings "
                "(camera_id, path, filename, start_ts, thumbnail_path) VALUES (?, ?, ?, ?, ?)",
                (1, source, os.path.basename(source), 0, thumbnail),
            )
            conn.commit()
            conn.close()

            original = db.DB_PATH
            try:
                db.DB_PATH = path
                db.init_db()
                conn = db.get_db()
                count = conn.execute("SELECT COUNT(*) FROM recordings").fetchone()[0]
                conn.close()
            finally:
                db.DB_PATH = original

            self.assertEqual(count, 0)
            self.assertTrue(os.path.exists(source))
            self.assertFalse(os.path.exists(thumbnail))


if __name__ == "__main__":
    unittest.main()
