# FOLD - Fractal Optimized Layered Data

FOLD stores any file inside a video and gets it back byte-for-byte. Every video carries the original filename and a CRC32 checksum, so a decode either returns exactly what went in or tells you the video is damaged.

There are two ways to encode:

| Mode | Container | Survives re-compression? | Size for a 3 MB file | Decode in browser? |
|---|---|---|---|---|
| **lossless** (default) | `.avi` (PNG codec) or `.mkv` (FFV1) | No, needs the exact file | ~3 MB | No |
| **robust** | `.mp4` (H.264) or `.webm` | Yes: tested after re-encoding at CRF 40 and after shrinking to half size | ~10 MB | Yes |

Use **lossless** for archiving and moving files around as-is. Use **robust** when the video will pass through something that re-encodes it (a video host, a messaging app).

## Install

```bash
pip install -r requirements.txt
# or, as a package with the `fold` command:
pip install -e ".[api]"
```

## Command line

```bash
fold encode report.pdf                 # -> report.pdf.avi
fold encode report.pdf --robust        # -> report.pdf.mp4
fold decode report.pdf.mp4             # -> report.pdf (original name restored)
fold info report.pdf.mp4               # show the stored filename and size
```

Without installing, use `python -m fold.cli.main` in place of `fold`.

## Python

```python
from fold import store, retrieve, retrieve_file

store("report.pdf", "report.avi")                    # a path is read as a file
store(b"raw bytes", "data.avi")                      # bytes or text work too
store("report.pdf", "report.mp4", mode="robust")

data = retrieve("report.avi")                        # -> bytes
name, data = retrieve_file("report.mp4")             # -> ("report.pdf", bytes)
```

`retrieve` detects the format automatically, including videos made by FOLD 1.0.

## Web app

`web-app/` is a self-contained page that encodes and decodes in the browser with no server. It writes robust-format WebM videos, so its output decodes with `fold decode`, and robust `.mp4` files from Python decode in the page.

```bash
python -m fold.api.server     # serves the web app at http://localhost:8000
```

Opening `web-app/index.html` directly also works.

## REST API

The same server exposes:

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | Service status |
| POST | `/encode?mode=lossless\|robust` | Upload a file (`file` form field), get a video back |
| POST | `/decode` | Upload a FOLD video, get the original file back with its name |

Uploads are capped at 100 MB (set `FOLD_MAX_UPLOAD_MB` to change). Temporary files are deleted after each request.

## How it works

Every payload gets a header before it's drawn into frames:

```
lossless:  "FLD2" | name length (1 byte) | name | data length (8 bytes) | CRC32 | data
robust:    "FOLD" | name length (1 byte) | name | data length (4 bytes) | CRC32 | data
```

**Lossless mode** writes the bytes straight into pixel colour channels: 3 bytes per pixel, 6.2 MB per 1920×1080 frame. A lossless codec keeps every value exact.

**Robust mode** draws one bit per 4×4 black or white block on a 128×128 grid (512×512 px frames). Each frame starts with a 32-bit frame index and a 16-bit payload length, and each frame is written 3 times. When decoding:

- each block's brightness is averaged, so blurry compression edges don't matter;
- frames are resized to the grid first, so a downscaled re-upload still decodes;
- repeated copies of a frame vote on every bit;
- dropped or duplicated frames are handled by the frame index, and missing frames are reported by number.

**FOLD 1.0 videos** (1 bit per colour channel, uncompressed RGBA AVI) still decode. The new lossless format is about 400× smaller for small files: the 5 KB README took 8.4 MB as a 1.0 video and takes 20 KB now.

## Development

```bash
pip install pytest
python -m pytest tests
```

The tests cover round trips in every mode and container, filename storage, FOLD 1.0 compatibility, rejection of non-FOLD videos, and (when `ffmpeg` is installed) decoding after a lossy re-encode.

```
fold/
├── core/
│   ├── container.py  # headers, length and checksum
│   ├── frames.py     # bytes <-> frames for each mode, format detection
│   ├── encoder.py    # store()
│   └── decoder.py    # retrieve(), retrieve_file()
├── api/server.py     # FastAPI server + web app hosting
├── cli/main.py       # `fold` command
└── utils/
web-app/              # browser encoder/decoder
tests/
```

## License

Proprietary - All rights reserved.
