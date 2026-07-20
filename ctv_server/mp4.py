import os
import struct
from functools import lru_cache


def _boxes(data: bytes, start: int, end: int):
    position = start
    while position + 8 <= end:
        size = struct.unpack_from(">I", data, position)[0]
        box_type = data[position + 4:position + 8]
        header_size = 8
        if size == 1:
            if position + 16 > end:
                return
            size = struct.unpack_from(">Q", data, position + 8)[0]
            header_size = 16
        elif size == 0:
            size = end - position
        if size < header_size or position + size > end:
            return
        yield position, size, header_size, box_type
        position += size


def _children(data: bytes, box):
    position, size, header_size, _ = box
    return _boxes(data, position + header_size, position + size)


def _duration_field(data: bytes, box, kind: bytes):
    position, _, header_size, _ = box
    payload = position + header_size
    if payload + 4 > len(data):
        return None
    version = data[payload]
    if version not in {0, 1}:
        return None
    if kind in {b"mvhd", b"mdhd"}:
        scale_offset, duration_offset = ((12, 16) if version == 0 else (20, 24))
    elif kind == b"tkhd":
        scale_offset, duration_offset = (None, 20) if version == 0 else (None, 28)
    else:
        return None
    width = 4 if version == 0 else 8
    absolute_duration = payload + duration_offset
    if absolute_duration + width > position + box[1]:
        return None
    timescale = None
    if scale_offset is not None:
        absolute_scale = payload + scale_offset
        if absolute_scale + 4 > position + box[1]:
            return None
        timescale = struct.unpack_from(">I", data, absolute_scale)[0]
    current = int.from_bytes(data[absolute_duration:absolute_duration + width], "big")
    return absolute_duration, width, timescale, current


def mp4_duration_patches(header: bytes, expected_duration: float) -> tuple[tuple[int, bytes], ...]:
    """Return same-size header patches for fragmented MP4 files with truncated durations."""
    if not expected_duration or expected_duration <= 0:
        return ()
    top_level = list(_boxes(header, 0, len(header)))
    moov = next((box for box in top_level if box[3] == b"moov"), None)
    if not moov:
        return ()
    moov_children = list(_children(header, moov))
    if not any(box[3] == b"mvex" for box in moov_children):
        return ()

    mvhd = next((box for box in moov_children if box[3] == b"mvhd"), None)
    movie_field = _duration_field(header, mvhd, b"mvhd") if mvhd else None
    if not movie_field or not movie_field[2]:
        return ()
    movie_timescale = movie_field[2]
    fields = [(movie_field, movie_timescale)]

    for trak in (box for box in moov_children if box[3] == b"trak"):
        trak_children = list(_children(header, trak))
        tkhd = next((box for box in trak_children if box[3] == b"tkhd"), None)
        if tkhd:
            field = _duration_field(header, tkhd, b"tkhd")
            if field:
                fields.append((field, movie_timescale))
        mdia = next((box for box in trak_children if box[3] == b"mdia"), None)
        if mdia:
            mdhd = next((box for box in _children(header, mdia) if box[3] == b"mdhd"), None)
            if mdhd:
                field = _duration_field(header, mdhd, b"mdhd")
                if field and field[2]:
                    fields.append((field, field[2]))

    patches = []
    for (offset, width, _, current), timescale in fields:
        desired = round(expected_duration * timescale)
        maximum = (1 << (width * 8)) - 1
        if desired <= maximum and current / timescale < expected_duration - 0.5:
            patches.append((offset, desired.to_bytes(width, "big")))
    return tuple(patches)


def patch_chunk(chunk: bytes, absolute_offset: int, patches: tuple[tuple[int, bytes], ...]) -> bytes:
    if not chunk or not patches:
        return chunk
    chunk_end = absolute_offset + len(chunk)
    output = None
    for patch_offset, replacement in patches:
        patch_end = patch_offset + len(replacement)
        overlap_start = max(absolute_offset, patch_offset)
        overlap_end = min(chunk_end, patch_end)
        if overlap_start >= overlap_end:
            continue
        if output is None:
            output = bytearray(chunk)
        source_start = overlap_start - patch_offset
        target_start = overlap_start - absolute_offset
        output[target_start:target_start + overlap_end - overlap_start] = replacement[
            source_start:source_start + overlap_end - overlap_start
        ]
    return bytes(output) if output is not None else chunk


@lru_cache(maxsize=2048)
def file_duration_patches(
    path: str, expected_duration: float, mtime_ns: int, file_size: int
) -> tuple[tuple[int, bytes], ...]:
    del mtime_ns, file_size
    try:
        with open(path, "rb") as source:
            header = source.read(64 * 1024)
    except OSError:
        return ()
    return mp4_duration_patches(header, expected_duration)
