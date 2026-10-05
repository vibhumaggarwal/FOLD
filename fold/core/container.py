"""
Byte-level containers that wrap a payload before it is turned into frames.

Two headers exist:

* FLD2 (lossless mode)
    MAGIC "FLD2" | name_len u8 | name | length u64 | crc32 u32 | data

* FOLD (robust mode — identical to the browser web-app's header)
    MAGIC "FOLD" | name_len u8 | name | length u32 | crc32 u32 | data

All integers are big-endian.
"""

import struct
import zlib
from typing import Optional, Tuple

from ..exceptions import FileCorruptionError

DENSE_MAGIC = b"FLD2"
ROBUST_MAGIC = b"FOLD"
MAX_NAME_BYTES = 255


def _name_bytes(name: Optional[str]) -> bytes:
    raw = (name or "").encode("utf-8")[:MAX_NAME_BYTES]
    # Don't leave a split multi-byte character at the end
    return raw.decode("utf-8", "ignore").encode("utf-8")


def pack(data: bytes, name: Optional[str], magic: bytes) -> bytes:
    nb = _name_bytes(name)
    length_fmt = ">Q" if magic == DENSE_MAGIC else ">I"
    if magic == ROBUST_MAGIC and len(data) > 0xFFFFFFFF:
        raise ValueError("Robust mode supports files up to 4 GiB")
    return b"".join([
        magic,
        bytes([len(nb)]),
        nb,
        struct.pack(length_fmt, len(data)),
        struct.pack(">I", zlib.crc32(data)),
        data,
    ])


def header_size(buf: bytes, magic: bytes) -> Optional[int]:
    """Total header length, or None if `buf` is too short to tell yet."""
    if len(buf) < 5:
        return None
    length_bytes = 8 if magic == DENSE_MAGIC else 4
    return 5 + buf[4] + length_bytes + 4


def total_size(buf: bytes, magic: bytes) -> Optional[int]:
    """Header + payload length, or None if the header isn't complete yet."""
    hs = header_size(buf, magic)
    if hs is None or len(buf) < hs:
        return None
    name_len = buf[4]
    length_fmt = ">Q" if magic == DENSE_MAGIC else ">I"
    (length,) = struct.unpack_from(length_fmt, buf, 5 + name_len)
    return hs + length


def unpack(buf: bytes, magic: bytes) -> Tuple[str, bytes]:
    """Validate and split a container into (filename, data)."""
    if buf[:4] != magic:
        raise FileCorruptionError("Not a FOLD stream (bad magic)")

    total = total_size(buf, magic)
    if total is None or len(buf) < total:
        raise FileCorruptionError("Video ended before all data was recovered")

    name_len = buf[4]
    name = buf[5:5 + name_len].decode("utf-8", "replace")
    hs = header_size(buf, magic)
    (crc,) = struct.unpack_from(">I", buf, hs - 4)
    data = bytes(buf[hs:total])

    if zlib.crc32(data) != crc:
        raise FileCorruptionError("Checksum mismatch: the video is damaged or was re-encoded lossily")
    return name, data
