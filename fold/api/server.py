import os
import tempfile
import uuid
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

from fold import store, retrieve

app = FastAPI(title="FOLD API Server")

# Allow CORS for development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Create a temporary directory for storing uploaded and encoded files
WORKSPACE_DIR = os.path.join(tempfile.gettempdir(), "fold_workspace")
os.makedirs(WORKSPACE_DIR, exist_ok=True)

@app.post("/encode")
async def encode_file(file: UploadFile = File(...)):
    if not file:
        raise HTTPException(status_code=400, detail="No file provided")
    
    contents = await file.read()
    
    # Store the file using FOLD encoder
    output_filename = f"encoded_{uuid.uuid4().hex[:8]}.avi"
    output_path = os.path.join(WORKSPACE_DIR, output_filename)
    
    try:
        # Encode returns the actual path saved
        final_path = store(contents, output_path=output_path)
        return FileResponse(
            path=final_path, 
            media_type="video/x-msvideo", 
            filename=f"{file.filename}.avi"
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

def guess_extension(data: bytes) -> str:
    # Detect common image signatures
    if data.startswith(b'\xFF\xD8\xFF'):
        return '.jpg'
    elif data.startswith(b'\x89PNG\r\n\x1a\n'):
        return '.png'
    elif data.startswith(b'GIF87a') or data.startswith(b'GIF89a'):
        return '.gif'
    elif data.startswith(b'BM'):
        return '.bmp'
    elif data.startswith(b'RIFF') and data[8:12] == b'WEBP':
        return '.webp'
    return ''

@app.post("/decode")
async def decode_file(file: UploadFile = File(...)):
    if not file:
        raise HTTPException(status_code=400, detail="No file provided")
    
    # Save the uploaded video temporarily
    temp_video_path = os.path.join(WORKSPACE_DIR, f"temp_{uuid.uuid4().hex[:8]}.avi")
    try:
        with open(temp_video_path, "wb") as f:
            f.write(await file.read())
            
        # Decode
        original_bytes = retrieve(temp_video_path)
        
        # Try to guess original filename
        original_filename = file.filename
        if original_filename.endswith(".avi"):
            original_filename = original_filename[:-4]
        elif original_filename.endswith(".mp4"):
            original_filename = original_filename[:-4]
        else:
            original_filename = "decoded_file"
            
        # Auto-detect image extensions
        ext = guess_extension(original_bytes)
        if ext and not original_filename.lower().endswith(ext):
            original_filename += ext
            
        return Response(
            content=original_bytes,
            media_type="application/octet-stream",
            headers={"Content-Disposition": f'attachment; filename="{original_filename}"'}
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        if os.path.exists(temp_video_path):
            os.remove(temp_video_path)

# Mount static files
static_dir = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(static_dir):
    app.mount("/", StaticFiles(directory=static_dir, html=True), name="static")

if __name__ == "__main__":
    uvicorn.run("fold.api.server:app", host="0.0.0.0", port=8000)
