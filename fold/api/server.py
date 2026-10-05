import os
import tempfile
import uuid
from urllib.parse import quote

import uvicorn
from fastapi import FastAPI, File, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from starlette.background import BackgroundTask

from fold import retrieve_file, store
from fold.exceptions import DecodingError, FileCorruptionError, FOLDException, ValidationError

app = FastAPI(title="FOLD API Server", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MAX_UPLOAD_BYTES = int(os.getenv("FOLD_MAX_UPLOAD_MB", "100")) * 1024 * 1024

WORKSPACE_DIR = os.path.join(tempfile.gettempdir(), "fold_workspace")
os.makedirs(WORKSPACE_DIR, exist_ok=True)


def _read_upload(file: UploadFile) -> bytes:
    contents = file.file.read(MAX_UPLOAD_BYTES + 1)
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail=f"File is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB")
    return contents


def _remove(path: str):
    if os.path.exists(path):
        os.remove(path)


def _attachment(filename: str) -> dict:
    # RFC 5987 so non-ASCII filenames survive
    return {"Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}"}


@app.get("/health")
def health():
    return {"status": "ok"}


# Plain `def` endpoints run in a thread pool, so encoding doesn't block the server
@app.post("/encode")
def encode_file(file: UploadFile = File(...),
                mode: str = Query("lossless", pattern="^(lossless|robust)$")):
    contents = _read_upload(file)
    ext = ".avi" if mode == "lossless" else ".mp4"
    output_path = os.path.join(WORKSPACE_DIR, f"encoded_{uuid.uuid4().hex}{ext}")

    try:
        store(contents, output_path=output_path, mode=mode, name=file.filename)
    except ValidationError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except FOLDException as e:
        _remove(output_path)
        raise HTTPException(status_code=500, detail=str(e))

    return FileResponse(
        path=output_path,
        media_type="video/x-msvideo" if ext == ".avi" else "video/mp4",
        headers=_attachment(f"{file.filename or 'data'}{ext}"),
        background=BackgroundTask(_remove, output_path),
    )


@app.post("/decode")
def decode_file(file: UploadFile = File(...)):
    contents = _read_upload(file)
    ext = os.path.splitext(file.filename or "")[1] or ".avi"
    temp_path = os.path.join(WORKSPACE_DIR, f"upload_{uuid.uuid4().hex}{ext}")

    try:
        with open(temp_path, "wb") as f:
            f.write(contents)
        name, data = retrieve_file(temp_path)
    except (FileCorruptionError, DecodingError) as e:
        # Not a readable FOLD video: the upload is at fault, not the server
        raise HTTPException(status_code=422, detail=str(e))
    except FOLDException as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        _remove(temp_path)

    return Response(
        content=data,
        media_type="application/octet-stream",
        headers=_attachment(name or "decoded_file.bin"),
    )


# Serve the browser app (web-app/) at / when running from a checkout
web_dir = os.path.join(os.path.dirname(__file__), "..", "..", "web-app")
if os.path.isdir(web_dir):
    app.mount("/", StaticFiles(directory=web_dir, html=True), name="web")


if __name__ == "__main__":
    uvicorn.run("fold.api.server:app", host="0.0.0.0", port=8000)
