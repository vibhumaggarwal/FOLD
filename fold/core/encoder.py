"""
Core encoder for FOLD - converts data to video
"""

import os
import time
from typing import Optional, Union

import cv2

from . import container, frames
from ..utils.validation import validate_input_data, validate_output_path
from ..utils.logging import setup_logger, log_performance
from ..exceptions import EncodingError, ValidationError

logger = setup_logger("fold.encoder")

MODES = ("lossless", "robust")

# Extension -> codecs to try, in order. Lossless codecs keep every byte intact.
LOSSLESS_CODECS = {".avi": ["png "], ".mkv": ["FFV1"]}
LOSSY_CODECS = {".mp4": ["avc1", "mp4v"], ".webm": ["VP90", "VP80"]}


def store(data: Union[str, bytes, bytearray, os.PathLike],
          output_path: Optional[str] = None,
          mode: str = "lossless",
          name: Optional[str] = None,
          fps: int = 30,
          width: int = 1920,
          height: int = 1080,
          block: int = 4,
          repeat: int = 3) -> str:
    """
    Convert data to a video file.

    Args:
        data: bytes/bytearray, a str of text, or a path to a file (os.PathLike
              or a str naming an existing file)
        output_path: where to write the video. Defaults to fold_<hash>.avi
                     (lossless) or .mp4 (robust) in the current directory.
        mode: "lossless" packs 3 bytes per pixel and needs .avi or .mkv.
              "robust" draws 4x4 black/white blocks that survive MP4/WebM
              compression and can be decoded by the browser web-app.
        name: filename stored inside the video (defaults to the input file's name)
        fps: frames per second
        width, height: frame size for lossless mode
        block: block size in pixels for robust mode (frame is 128*block square)
        repeat: how many times each robust frame is written

    Returns:
        Path to the created video file
    """
    start_time = time.time()
    if mode not in MODES:
        raise ValidationError(f"mode must be one of {MODES}, got {mode!r}")

    try:
        byte_data, inferred_name = _read_input(data)
        name = name if name is not None else inferred_name
        logger.info(f"Encoding {len(byte_data)} bytes in {mode} mode")

        if output_path is None:
            output_path = _generate_output_path(byte_data, mode)
        output_path = validate_output_path(output_path)
        ext = os.path.splitext(output_path)[1].lower()

        if mode == "lossless":
            if ext not in LOSSLESS_CODECS:
                raise ValidationError(
                    f"Lossless mode needs a lossless container (.avi or .mkv), got {ext or 'no extension'}. "
                    "Use mode='robust' for .mp4/.webm."
                )
            buf = container.pack(byte_data, name, container.DENSE_MAGIC)
            frame_iter = frames.dense_encode(buf, width, height)
            size = (width, height)
            codecs = LOSSLESS_CODECS[ext]
        else:
            if ext not in {**LOSSLESS_CODECS, **LOSSY_CODECS}:
                raise ValidationError(f"Unsupported video extension {ext!r}; use .mp4, .webm, .avi or .mkv")
            buf = container.pack(byte_data, name, container.ROBUST_MAGIC)
            frame_iter = frames.robust_encode(buf, block=block, repeat=repeat)
            side = frames.GRID * block
            size = (side, side)
            codecs = LOSSLESS_CODECS.get(ext) or LOSSY_CODECS[ext]

        count = _write_video(frame_iter, output_path, fps, size, codecs)
        logger.info(f"Wrote {count} frames, {os.path.getsize(output_path)} bytes -> {output_path}")
        log_performance(logger, "Encoding", time.time() - start_time, len(byte_data))
        return output_path

    except (EncodingError, ValidationError):
        raise
    except Exception as e:
        logger.error(f"Encoding failed: {e}")
        raise EncodingError(f"Failed to encode data: {e}") from e


def _read_input(data):
    """Returns (bytes, filename-or-None)."""
    if isinstance(data, os.PathLike) or (isinstance(data, str) and os.path.isfile(data)):
        path = os.fspath(data)
        with open(path, "rb") as f:
            return f.read(), os.path.basename(path)
    return validate_input_data(data), None


def _generate_output_path(data: bytes, mode: str) -> str:
    import hashlib
    data_hash = hashlib.md5(data).hexdigest()[:8]
    ext = ".avi" if mode == "lossless" else ".mp4"
    return os.path.join(os.getcwd(), f"fold_{data_hash}_{int(time.time())}{ext}")


def _write_video(frame_iter, output_path: str, fps: int, size, codecs) -> int:
    writer = None
    for codec in codecs:
        writer = cv2.VideoWriter(output_path, cv2.VideoWriter_fourcc(*codec), fps, size)
        if writer.isOpened():
            break
        writer.release()
        writer = None
    if writer is None:
        raise EncodingError(f"No working video codec for {output_path} (tried {', '.join(codecs)})")

    count = 0
    try:
        for frame in frame_iter:
            writer.write(frame)
            count += 1
    finally:
        writer.release()

    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        raise EncodingError("Video file was not created")
    return count
