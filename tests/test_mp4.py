import asyncio
import struct
import tempfile
import unittest
from pathlib import Path

from ctv_server.main import VideoFileResponse
from ctv_server.mp4 import file_duration_patches, mp4_duration_patches, patch_chunk


def box(kind: bytes, payload: bytes) -> bytes:
    return struct.pack(">I4s", len(payload) + 8, kind) + payload


def full_box(kind: bytes, fields: bytes) -> bytes:
    return box(kind, b"\0\0\0\0" + fields)


def fragmented_mp4() -> bytes:
    mvhd = full_box(b"mvhd", struct.pack(">IIII", 0, 0, 1000, 1000))
    tkhd = full_box(b"tkhd", struct.pack(">IIIII", 0, 0, 1, 0, 1000))
    mdhd = full_box(b"mdhd", struct.pack(">IIII", 0, 0, 16000, 1000))
    trak = box(b"trak", tkhd + box(b"mdia", mdhd))
    moov = box(b"moov", mvhd + trak + box(b"mvex", b""))
    return box(b"ftyp", b"isom") + moov + box(b"moof", b"") + box(b"mdat", b"video")


class Mp4DurationTests(unittest.TestCase):
    def test_patches_fragmented_mp4_durations_without_changing_size(self):
        original = fragmented_mp4()
        patches = mp4_duration_patches(original, 53.76)
        patched = patch_chunk(original, 0, patches)

        self.assertEqual(len(patched), len(original))
        self.assertEqual(len(patches), 3)
        values = [int.from_bytes(value, "big") for _, value in patches]
        self.assertEqual(values, [53760, 53760, 860160])

    def test_patch_chunk_handles_a_range_crossing_a_duration_field(self):
        original = fragmented_mp4()
        patches = mp4_duration_patches(original, 20.0)
        offset, replacement = patches[0]
        ranged = original[offset + 1:offset + 3]

        self.assertEqual(
            patch_chunk(ranged, offset + 1, patches),
            replacement[1:3],
        )

    def test_does_not_patch_non_fragmented_mp4(self):
        data = box(b"ftyp", b"isom") + box(
            b"moov", full_box(b"mvhd", struct.pack(">IIII", 0, 0, 1000, 1000))
        )
        self.assertEqual(mp4_duration_patches(data, 20.0), ())

    def test_file_patch_cache_is_invalidated_by_file_metadata(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "clip.mp4"
            path.write_bytes(fragmented_mp4())
            stat = path.stat()
            first = file_duration_patches(str(path), 10.0, stat.st_mtime_ns, stat.st_size)
            second = file_duration_patches(str(path), 20.0, stat.st_mtime_ns, stat.st_size)
            self.assertNotEqual(first, second)

    def test_video_response_patches_single_range_without_changing_range_contract(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "clip.mp4"
            original = fragmented_mp4()
            path.write_bytes(original)
            patches = mp4_duration_patches(original, 20.0)

            response = VideoFileResponse(path, media_type="video/mp4", expected_duration=20.0)
            messages = []

            async def send(message):
                messages.append(message)

            async def receive():
                return {"type": "http.disconnect"}

            asyncio.run(response({
                "type": "http",
                "method": "GET",
                "headers": [(b"range", b"bytes=10-79")],
                "extensions": {},
            }, receive, send))

            start = messages[0]
            headers = {key.decode(): value.decode() for key, value in start["headers"]}
            content = b"".join(message.get("body", b"") for message in messages[1:])
            self.assertEqual(start["status"], 206)
            self.assertEqual(headers["content-range"], f"bytes 10-79/{len(original)}")
            self.assertEqual(content, patch_chunk(original[10:80], 10, patches))


if __name__ == "__main__":
    unittest.main()
