import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from ctv_server import db
from ctv_server.partition_service import prepare_partitions, run_partition_scan
from ctv_server.partitioner import dates_for_range, resolve_partition, validate_pattern
from ctv_server.api.timeline import get_timeline


class PartitionerTests(unittest.TestCase):
    def test_range_crossing_midnight_resolves_both_days(self):
        tz = ZoneInfo("Europe/Rome")
        start = datetime(2026, 7, 11, 23, 30, tzinfo=tz).timestamp()
        end = datetime(2026, 7, 12, 0, 30, tzinfo=tz).timestamp()
        days = dates_for_range(start, end, "Europe/Rome")
        self.assertEqual([day.isoformat() for day in days], ["2026-07-11", "2026-07-12"])

    def test_pattern_resolves_exact_daily_directory(self):
        pattern = validate_pattern("{YYYY}/{MM}/{DD}")
        day = datetime(2026, 7, 11).date()
        self.assertTrue(resolve_partition("/archive", pattern, day).endswith("/2026/07/11"))


class PartitionIndexTests(unittest.TestCase):
    def setUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.root = Path(self.tempdir.name)
        self.day = self.root / "2026" / "07" / "11"
        self.day.mkdir(parents=True)
        self.original_db = db.DB_PATH
        db.DB_PATH = str(self.root / "ctv.db")
        db.init_db()
        conn = db.get_db()
        self.camera_id = conn.execute("""
            INSERT INTO cameras (name, source_path, timezone, indexing_mode, directory_pattern)
            VALUES ('Test', ?, 'Europe/Rome', 'partitioned', '{YYYY}/{MM}/{DD}')
        """, (str(self.root),)).lastrowid
        conn.commit()
        conn.close()

    def tearDown(self):
        db.DB_PATH = self.original_db
        self.tempdir.cleanup()

    def test_requested_partition_is_indexed_and_removed_file_is_purged(self):
        media = self.day / "CAM_20260711010000.mp4"
        media.write_bytes(b"video")
        tz = ZoneInfo("Europe/Rome")
        start = datetime(2026, 7, 11, 0, 0, tzinfo=tz).timestamp()
        end = datetime(2026, 7, 12, 0, 0, tzinfo=tz).timestamp()
        jobs = prepare_partitions([self.camera_id], start, end)
        self.assertEqual(len(jobs), 1)
        pending = get_timeline(start, end, str(self.camera_id))
        self.assertEqual(len(pending["cameras"]), 1)
        self.assertEqual(pending["cameras"][0]["partition_status"], "unknown")
        self.assertEqual(pending["cameras"][0]["segments"], [])
        run_partition_scan(self.camera_id, jobs[0]["key"], jobs[0]["path"])

        conn = db.get_db()
        recording = conn.execute(
            "SELECT partition_key FROM recordings WHERE camera_id = ?", (self.camera_id,)
        ).fetchone()
        conn.close()
        self.assertEqual(recording["partition_key"], "2026-07-11")
        ready = get_timeline(start, end, str(self.camera_id))
        self.assertEqual(ready["cameras"][0]["partition_status"], "ready")
        self.assertEqual(len(ready["cameras"][0]["segments"]), 1)

        media.unlink()
        result = run_partition_scan(self.camera_id, "2026-07-11", str(self.day))
        self.assertEqual(result["missing"], 1)
        conn = db.get_db()
        count = conn.execute(
            "SELECT COUNT(*) FROM recordings WHERE camera_id = ?", (self.camera_id,)
        ).fetchone()[0]
        conn.close()
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
