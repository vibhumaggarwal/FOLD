import os
import shutil
import subprocess
from pathlib import Path

import pytest

from fold import retrieve, retrieve_file, store
from fold.exceptions import FileCorruptionError, ValidationError

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def blob():
    return os.urandom(200_000)


@pytest.mark.parametrize("ext", [".avi", ".mkv"])
def test_lossless_roundtrip(tmp_path, blob, ext):
    out = store(blob, tmp_path / f"v{ext}", width=320, height=240)
    assert retrieve(out) == blob


@pytest.mark.parametrize("ext", [".mp4", ".avi"])
def test_robust_roundtrip(tmp_path, blob, ext):
    out = store(blob, tmp_path / f"v{ext}", mode="robust", repeat=1)
    assert retrieve(out) == blob


def test_filename_is_stored(tmp_path):
    src = tmp_path / "notes ✓.txt"
    src.write_text("hello")
    name, data = retrieve_file(store(src, tmp_path / "v.avi"))
    assert (name, data) == ("notes ✓.txt", b"hello")


def test_empty_and_text_input(tmp_path):
    assert retrieve(store(b"", tmp_path / "a.avi")) == b""
    assert retrieve(store("plain text", tmp_path / "b.avi")) == b"plain text"


def test_decodes_fold_1_0_videos():
    expected = (FIXTURES / "legacy_v1.json").read_bytes()
    assert retrieve(str(FIXTURES / "legacy_v1.avi")) == expected


def test_lossless_rejects_lossy_container(tmp_path):
    with pytest.raises(ValidationError):
        store(b"x", tmp_path / "v.mp4")


def test_rejects_non_fold_video(tmp_path):
    import cv2
    import numpy as np
    path = str(tmp_path / "plain.avi")
    w = cv2.VideoWriter(path, cv2.VideoWriter_fourcc(*"png "), 30, (64, 64))
    w.write(np.full((64, 64, 3), 90, dtype=np.uint8))
    w.release()
    with pytest.raises(FileCorruptionError):
        retrieve(path)


@pytest.mark.skipif(not shutil.which("ffmpeg"), reason="ffmpeg not installed")
def test_robust_survives_lossy_reencode(tmp_path, blob):
    src = store(blob, tmp_path / "v.mp4", mode="robust")
    reup = tmp_path / "reupload.mp4"
    subprocess.run(["ffmpeg", "-loglevel", "error", "-y", "-i", str(src),
                    "-vf", "scale=360:360", "-crf", "30", "-c:v", "libx264", str(reup)], check=True)
    assert retrieve(str(reup)) == blob
