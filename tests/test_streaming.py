import json
import asyncio
import os
import subprocess
import tempfile
import unittest

from ctv_server import db
from ctv_server.api.system import stream_profiles, update_stream_profiles
from ctv_server.auth import CurrentUser
from ctv_server.models import StreamProfileConfig, StreamProfilesUpdate
from ctv_server.streaming import (
    build_hls_command,
    build_transcode_command,
    ensure_hls_playlist,
    hls_segment,
    shutdown_hls_jobs,
)


class StreamProfileTests(unittest.TestCase):
    def setUp(self):
        self.original_db_path = db.DB_PATH
        self.tmp = tempfile.TemporaryDirectory()
        db.DB_PATH = os.path.join(self.tmp.name, "ctv.db")
        db.init_db()

    def tearDown(self):
        db.DB_PATH = self.original_db_path
        self.tmp.cleanup()

    def test_defaults_include_immutable_native_profile(self):
        profiles = stream_profiles()
        self.assertEqual(profiles["native"]["scale_percent"], 100)
        self.assertFalse(profiles["native"]["configurable"])
        self.assertEqual(profiles["balanced"]["scale_percent"], 50)
        self.assertEqual(profiles["fast"]["bitrate_kbps"], 450)

    def test_admin_can_update_compressed_profiles(self):
        admin = CurrentUser("admin", "admin", "Admin", True, True)
        updated = update_stream_profiles(
            StreamProfilesUpdate(
                balanced=StreamProfileConfig(
                    scale_percent=60, fps=18, bitrate_kbps=1600,
                ),
                fast=StreamProfileConfig(
                    scale_percent=25, fps=6, bitrate_kbps=300,
                ),
            ),
            admin,
        )
        self.assertEqual(updated["balanced"]["scale_percent"], 60)
        self.assertEqual(updated["balanced"]["fps"], 18)
        self.assertEqual(updated["fast"]["bitrate_kbps"], 300)
        self.assertEqual(updated["native"]["scale_percent"], 100)


class TranscodeCommandTests(unittest.TestCase):
    profile = {
        "name": "balanced",
        "scale_percent": 50,
        "fps": 10,
        "bitrate_kbps": 500,
    }

    def test_command_preserves_aspect_ratio_and_bakes_speed(self):
        command = build_transcode_command("/video/input.mp4", self.profile, 3.25, 16)
        video_filter = command[command.index("-vf") + 1]
        self.assertIn("setpts=(PTS-STARTPTS)/16", video_filter)
        self.assertIn("fps=10", video_filter)
        self.assertIn("scale=trunc(iw*0.5/2)*2:trunc(ih*0.5/2)*2", video_filter)
        self.assertEqual(command[command.index("-b:v") + 1], "500k")
        self.assertEqual(command[command.index("-ss") + 1], "3.250")

    def test_ffmpeg_output_has_scaled_dimensions_and_shorter_duration(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source.mp4")
            output = os.path.join(tmp, "output.mp4")
            subprocess.run(
                [
                    "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", "testsrc=size=320x240:rate=20",
                    "-t", "2", "-c:v", "mpeg4", source,
                ],
                check=True,
            )
            command = build_transcode_command(source, self.profile, 0, 2)
            result = subprocess.run(command, check=True, capture_output=True)
            with open(output, "wb") as handle:
                handle.write(result.stdout)
            probe = subprocess.run(
                [
                    "ffprobe", "-v", "error", "-show_entries",
                    "stream=width,height:format=duration", "-of", "json", output,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            metadata = json.loads(probe.stdout)
            self.assertEqual(metadata["streams"][0]["width"], 160)
            self.assertEqual(metadata["streams"][0]["height"], 120)
            self.assertLess(float(metadata["format"]["duration"]), 1.2)
            self.assertIn(b"moof", result.stdout)

    def test_hls_output_is_segmented_for_native_mobile_playback(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source.mp4")
            output_dir = os.path.join(tmp, "hls")
            os.mkdir(output_dir)
            subprocess.run(
                [
                    "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", "testsrc=size=320x240:rate=20",
                    "-t", "2", "-c:v", "mpeg4", source,
                ],
                check=True,
            )
            command = build_hls_command(source, self.profile, 0, 2, output_dir)
            subprocess.run(command, check=True, capture_output=True)
            playlist_path = os.path.join(output_dir, "index.m3u8")
            with open(playlist_path, encoding="utf-8") as handle:
                playlist = handle.read()
            self.assertIn("#EXTM3U", playlist)
            self.assertIn("#EXT-X-PLAYLIST-TYPE:EVENT", playlist)
            self.assertIn("#EXT-X-ENDLIST", playlist)
            self.assertIn("segment_00000.ts", playlist)
            self.assertNotIn(output_dir, playlist)
            segment = os.path.join(output_dir, "segment_00000.ts")
            probe = subprocess.run(
                [
                    "ffprobe", "-v", "error", "-show_entries",
                    "stream=width,height", "-of", "json", segment,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            metadata = json.loads(probe.stdout)
            self.assertEqual(metadata["streams"][0]["width"], 160)
            self.assertEqual(metadata["streams"][0]["height"], 120)

    def test_hls_session_returns_first_segment_before_full_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = os.path.join(tmp, "source.mp4")
            subprocess.run(
                [
                    "ffmpeg", "-nostdin", "-hide_banner", "-loglevel", "error",
                    "-f", "lavfi", "-i", "testsrc=size=320x240:rate=20",
                    "-t", "3", "-c:v", "mpeg4", source,
                ],
                check=True,
            )

            async def scenario():
                playlist_path = await ensure_hls_playlist(
                    "0123456789abcdef0123456789abcdef",
                    source,
                    self.profile,
                    0,
                    1,
                )
                playlist = playlist_path.read_text(encoding="utf-8")
                segment_name = next(
                    line for line in playlist.splitlines() if line.endswith(".ts")
                )
                self.assertTrue(hls_segment(
                    "0123456789abcdef0123456789abcdef", segment_name,
                ).is_file())
                await shutdown_hls_jobs()

            asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
