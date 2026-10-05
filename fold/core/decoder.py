"""
Core decoder for FOLD - converts video back to data
"""

import itertools
import os
import time
from typing import Iterator, Tuple

import cv2
import numpy as np

from . import container, frames
from ..utils.validation import validate_file_path
from ..utils.logging import setup_logger, log_performance
from ..exceptions import DecodingError, FileCorruptionError

logger = setup_logger("fold.decoder")


def retrieve(video_path: str) -> bytes:
    """
    Convert a FOLD video back to the original data.

    Handles lossless, robust and FOLD 1.0 videos; the format is detected
    automatically.

    Raises:
        DecodingError: if the video can't be read
        FileCorruptionError: if it isn't a FOLD video or the data is damaged
    """
    return retrieve_file(video_path)[1]


def retrieve_file(video_path: str) -> Tuple[str, bytes]:
    """Like retrieve(), but returns (original_filename, data). The filename may be ''."""
    start_time = time.time()
    try:
        video_path = validate_file_path(video_path)
        logger.info(f"Decoding {video_path} ({os.path.getsize(video_path)} bytes)")

        frame_iter = _read_frames(video_path)
        first = next(frame_iter, None)
        if first is None:
            raise FileCorruptionError("Video contains no decodable frames")

        kind = frames.detect(first)
        if kind is None:
            raise FileCorruptionError("This video wasn't made by FOLD, or it was too damaged to recognise")
        logger.info(f"Detected {kind} format")

        all_frames = itertools.chain([first], frame_iter)
        if kind == "dense":
            name, data = container.unpack(frames.dense_decode(all_frames), container.DENSE_MAGIC)
        elif kind == "robust":
            name, data = container.unpack(frames.robust_decode(all_frames), container.ROBUST_MAGIC)
        else:
            name, data = frames.legacy_unpack(frames.legacy_decode(all_frames))

        log_performance(logger, "Decoding", time.time() - start_time, len(data))
        return name, data

    except (FileCorruptionError, FileNotFoundError):
        raise
    except Exception as e:
        logger.error(f"Decoding failed: {e}")
        raise DecodingError(f"Failed to decode video: {e}") from e


def _read_frames(video_path: str) -> Iterator[np.ndarray]:
    """Yield frames one at a time, so long videos don't have to fit in memory."""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise DecodingError("Failed to open video file")
    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            yield frame
    finally:
        cap.release()
