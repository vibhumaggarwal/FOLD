"""
Frame codecs: turn a container (bytes) into video frames and back.

* dense   — lossless mode. Every byte becomes one colour channel of one pixel
            (24 bits per pixel). Needs a lossless video codec.
* robust  — survives lossy compression (MP4/WebM, re-uploads). Each bit is a
            black or white block on a 128x128 grid, and every frame carries its
            own index so duplicated or repeated frames are harmless. This is the
            same layout the browser web-app produces, so videos from either side
            decode on the other.
* legacy  — decode-only support for videos made by FOLD 1.0
            (one bit per colour channel, no filename).

All frames are numpy uint8 arrays in OpenCV's BGR order.
"""

from typing import Dict, Iterable, Iterator, Optional, Tuple

import cv2
import numpy as np

from . import container
from ..exceptions import FileCorruptionError

# ---------------- robust layout (must match web-app/script.js) ----------------
GRID = 128
BITS_PER_FRAME = GRID * GRID              # 16,384
FRAME_INDEX_BITS = 32
PAYLOAD_LEN_BITS = 16
HEADER_BITS = FRAME_INDEX_BITS + PAYLOAD_LEN_BITS
MAX_PAYLOAD_BITS = BITS_PER_FRAME - HEADER_BITS
MAX_FRAMES = 10_000_000                   # rejects garbage indices from damaged frames


def _uint_bits(value: int, width: int) -> np.ndarray:
    return np.array([(value >> (width - 1 - i)) & 1 for i in range(width)], dtype=np.uint8)


def _bits_uint(bits: np.ndarray) -> int:
    out = 0
    for b in bits:
        out = (out << 1) | int(b)
    return out


# ================================ dense ================================

def dense_encode(buf: bytes, width: int, height: int) -> Iterator[np.ndarray]:
    frame_bytes = width * height * 3
    for start in range(0, len(buf), frame_bytes):
        chunk = buf[start:start + frame_bytes].ljust(frame_bytes, b"\0")
        yield np.frombuffer(chunk, dtype=np.uint8).reshape(height, width, 3)


def dense_decode(frames: Iterable[np.ndarray]) -> bytes:
    buf = bytearray()
    total = None
    for frame in frames:
        buf += frame.tobytes()
        if total is None:
            total = container.total_size(buf, container.DENSE_MAGIC)
        if total is not None and len(buf) >= total:
            break
    return bytes(buf)


# ================================ robust ================================

def robust_frame_count(buf_len: int) -> int:
    return max(1, -(-buf_len * 8 // MAX_PAYLOAD_BITS))


def robust_encode(buf: bytes, block: int = 4, repeat: int = 3) -> Iterator[np.ndarray]:
    bits = np.unpackbits(np.frombuffer(buf, dtype=np.uint8))
    for idx in range(robust_frame_count(len(buf))):
        chunk = bits[idx * MAX_PAYLOAD_BITS:(idx + 1) * MAX_PAYLOAD_BITS]
        fb = np.zeros(BITS_PER_FRAME, dtype=np.uint8)
        fb[:FRAME_INDEX_BITS] = _uint_bits(idx, FRAME_INDEX_BITS)
        fb[FRAME_INDEX_BITS:HEADER_BITS] = _uint_bits(len(chunk), PAYLOAD_LEN_BITS)
        fb[HEADER_BITS:HEADER_BITS + len(chunk)] = chunk

        grid = fb.reshape(GRID, GRID) * 255
        img = np.repeat(np.repeat(grid, block, axis=0), block, axis=1)
        frame = np.ascontiguousarray(np.stack([img] * 3, axis=-1))
        # Repeats let players that drop frames (e.g. the browser decoder) still see every index
        for _ in range(repeat):
            yield frame


def _robust_levels(frame: np.ndarray) -> np.ndarray:
    """Average brightness of each grid cell, whatever the frame's resolution."""
    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
    return cv2.resize(gray, (GRID, GRID), interpolation=cv2.INTER_AREA).astype(np.float32).reshape(-1)


def _robust_header(levels: np.ndarray) -> Tuple[int, int]:
    bits = levels[:HEADER_BITS] > 127
    return _bits_uint(bits[:FRAME_INDEX_BITS]), _bits_uint(bits[FRAME_INDEX_BITS:])


def robust_decode(frames: Iterable[np.ndarray]) -> bytes:
    # Every copy of a frame votes on each bit, which cancels out compression noise
    votes: Dict[int, np.ndarray] = {}
    counts: Dict[int, int] = {}

    for frame in frames:
        levels = _robust_levels(frame)
        idx, plen = _robust_header(levels)
        if idx >= MAX_FRAMES or plen > MAX_PAYLOAD_BITS:
            continue  # damaged header
        if idx in votes:
            votes[idx] += levels
            counts[idx] += 1
        else:
            votes[idx] = levels.copy()
            counts[idx] = 1

    if not votes:
        raise FileCorruptionError("No FOLD frames found")

    last = max(votes)
    missing = [i for i in range(last + 1) if i not in votes]
    if missing:
        preview = ", ".join(map(str, missing[:10])) + ("…" if len(missing) > 10 else "")
        raise FileCorruptionError(f"{len(missing)} frame(s) missing from the video (index {preview})")

    payload = []
    for i in range(last + 1):
        levels = votes[i] / counts[i]
        _, plen = _robust_header(levels)
        payload.append((levels[HEADER_BITS:HEADER_BITS + plen] > 127).astype(np.uint8))

    bits = np.concatenate(payload)
    return np.packbits(bits[: len(bits) // 8 * 8]).tobytes()


# ================================ legacy ================================

LEGACY_HEADER = 12  # "FOLD" + length u32 + crc32 u32, no filename


def legacy_decode(frames: Iterable[np.ndarray]) -> bytes:
    buf = bytearray()
    total = None
    for frame in frames:
        # 1.0 wrote RGB with a 128 threshold per channel
        bits = (frame[..., ::-1] >= 128).reshape(-1)
        buf += np.packbits(bits).tobytes()
        if total is None and len(buf) >= LEGACY_HEADER:
            total = LEGACY_HEADER + int.from_bytes(buf[4:8], "big")
        if total is not None and len(buf) >= total:
            break
    return bytes(buf)


def legacy_unpack(buf: bytes) -> Tuple[str, bytes]:
    import zlib
    length = int.from_bytes(buf[4:8], "big")
    crc = int.from_bytes(buf[8:12], "big")
    data = bytes(buf[LEGACY_HEADER:LEGACY_HEADER + length])
    if len(data) < length:
        raise FileCorruptionError("Video ended before all data was recovered")
    if zlib.crc32(data) != crc:
        raise FileCorruptionError("Checksum mismatch: the video is damaged")
    return "", data


# ================================ detection ================================

def detect(frame: np.ndarray) -> Optional[str]:
    """Which codec produced this (first) frame, or None if it isn't FOLD."""
    if frame.tobytes()[:4] == container.DENSE_MAGIC:
        return "dense"

    legacy_bits = (frame[..., ::-1] >= 128).reshape(-1)[:32]
    if np.packbits(legacy_bits).tobytes() == container.ROBUST_MAGIC:
        return "legacy"

    levels = _robust_levels(frame)
    idx, plen = _robust_header(levels)
    if idx == 0 and plen >= 32:
        magic_bits = (levels[HEADER_BITS:HEADER_BITS + 32] > 127).astype(np.uint8)
        if np.packbits(magic_bits).tobytes() == container.ROBUST_MAGIC:
            return "robust"
    return None
