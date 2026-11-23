import sys
import os

# Fix for pythonw where stdout/stderr is None
if sys.stdout is None:
    sys.stdout = open(os.devnull, 'w')
if sys.stderr is None:
    sys.stderr = open(os.devnull, 'w')

import time
import mimetypes
import urllib.parse
import zipfile
import shutil
import subprocess
from typing import List
from pydantic import BaseModel

from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware

import config
import downloader
import converter

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
os.makedirs(STATIC_DIR, exist_ok=True)

app = FastAPI(title="Mediatool")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

class VideoInfoRequest(BaseModel):
    url: str

class DownloadRequest(BaseModel):
    url: str
    format: str = "video"
    quality: str = "best"

class ConfigUpdateRequest(BaseModel):
    download_dir: str

def cleanup_old_files():
    """Remove files older than 1 hour on cloud to preserve disk space."""
    if not config.IS_CLOUD:
        return
    try:
        d = config.get_download_dir()
        now = time.time()
        for f in os.listdir(d):
            fp = os.path.join(d, f)
            if os.path.isfile(fp) and (now - os.path.getmtime(fp)) > 3600:
                os.remove(fp)
    except Exception:
        pass

@app.get("/", response_class=HTMLResponse)
async def serve_index():
    index_file = os.path.join(STATIC_DIR, "index.html")
    if os.path.exists(index_file):
        with open(index_file, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse("index.html not found.")

@app.get("/api/config")
async def api_get_config():
    return {
        "download_dir": config.get_download_dir(),
        "is_cloud": config.IS_CLOUD
    }

@app.post("/api/config")
async def api_set_config(req: ConfigUpdateRequest):
    if config.IS_CLOUD:
        return {"download_dir": config.get_download_dir(), "is_cloud": True}
    if not req.download_dir or not req.download_dir.strip():
        raise HTTPException(status_code=400, detail="Invalid folder path.")
    try:
        updated = config.set_download_dir(req.download_dir)
        return {"download_dir": updated, "is_cloud": False}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/pick-folder")
async def api_pick_folder():
    if config.IS_CLOUD:
        return {"download_dir": config.get_download_dir(), "is_cloud": True}
    try:
        picker_script = os.path.join(BASE_DIR, "picker.py")
        current_dir = config.get_download_dir()
        proc = subprocess.run(
            [sys.executable, picker_script, current_dir],
            capture_output=True,
            text=True,
            encoding='utf-8'
        )
        chosen = proc.stdout.strip()
        if chosen and os.path.exists(chosen):
            updated = config.set_download_dir(chosen)
            return {"download_dir": updated, "is_cloud": False}
        return {"download_dir": current_dir, "is_cloud": False}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/video-info")
async def api_video_info(req: VideoInfoRequest):
    if not req.url:
        raise HTTPException(status_code=400, detail="URL required.")
    try:
        return downloader.get_video_info(req.url)
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@app.post("/api/start-download")
async def api_start_download(req: DownloadRequest, background_tasks: BackgroundTasks):
    if not req.url:
        raise HTTPException(status_code=400, detail="URL required.")
    task_id = downloader.create_download_task(req.url, req.format, req.quality)
    background_tasks.add_task(cleanup_old_files)
    return {"task_id": task_id}

@app.get("/api/task-status/{task_id}")
async def api_task_status(task_id: str):
    status = downloader.get_task_status(task_id)
    if not status:
        raise HTTPException(status_code=404, detail="Task not found.")
    return status

@app.get("/api/get/{task_id}/{filename:path}")
async def api_get_file_by_name(task_id: str, filename: str):
    active_dir = config.get_download_dir()
    status = downloader.get_task_status(task_id)
    if not status or not status.get("filename"):
        matches = [f for f in os.listdir(active_dir) if f.startswith(task_id + ".")]
        if not matches:
            raise HTTPException(status_code=404, detail="File not found.")
        file_path = os.path.join(active_dir, matches[0])
    else:
        file_path = status.get("file_path") or os.path.join(active_dir, status["filename"])

    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found on disk.")

    mime_type, _ = mimetypes.guess_type(file_path)
    if not mime_type:
        mime_type = "video/mp4" if file_path.endswith(".mp4") else "audio/mpeg"

    display_name = urllib.parse.unquote(filename)
    return FileResponse(
        path=file_path,
        filename=display_name,
        media_type=mime_type
    )

@app.get("/api/download-file/{filename:path}")
async def api_download_file(filename: str):
    active_dir = config.get_download_dir()
    decoded_filename = urllib.parse.unquote(filename)
    file_path = os.path.join(active_dir, decoded_filename)
    if not os.path.exists(file_path):
        raise HTTPException(status_code=404, detail="File not found.")

    clean_name = decoded_filename
    if "_" in decoded_filename:
        parts = decoded_filename.split("_")
        clean_name = "_".join(parts[2:]) if decoded_filename.startswith("converted_") else "_".join(parts[1:])

    mime_type, _ = mimetypes.guess_type(file_path)
    return FileResponse(
        path=file_path,
        filename=clean_name or decoded_filename,
        media_type=mime_type or "application/octet-stream"
    )

@app.post("/api/open-file/{task_id}")
async def api_open_file(task_id: str):
    if config.IS_CLOUD:
        return {"success": False, "message": "Disabled on cloud"}

    status = downloader.get_task_status(task_id)
    file_path = status.get("file_path") if status else None
    if not file_path or not os.path.exists(file_path):
        active_dir = config.get_download_dir()
        if status and status.get("filename"):
            cand = os.path.join(active_dir, status["filename"])
            if os.path.exists(cand):
                file_path = cand

    if file_path and os.path.exists(file_path):
        config.open_in_foreground(file_path, is_folder=False)
        return {"success": True}
    raise HTTPException(status_code=404, detail="File not found.")

@app.post("/api/open-folder")
async def api_open_folder(task_id: str = None):
    if config.IS_CLOUD:
        return {"success": False, "message": "Disabled on cloud"}

    active_dir = config.get_download_dir()
    select_file = None
    if task_id:
        status = downloader.get_task_status(task_id)
        if status and status.get("file_path") and os.path.exists(status["file_path"]):
            select_file = status["file_path"]

    config.open_in_foreground(active_dir, is_folder=True, select_file=select_file)
    return {"success": True}

@app.post("/api/convert-media")
async def api_convert_media(
    files: List[UploadFile] = File(...),
    target_ext: str = Form(...),
    quality: int = Form(90),
    resolution: str = Form("original"),
    audio_bitrate: str = Form("320k")
):
    if not files:
        raise HTTPException(status_code=400, detail="No files provided.")

    active_dir = config.get_download_dir()
    converted_filenames = []
    temp_files = []

    try:
        for f in files:
            temp_path = os.path.join(active_dir, f"temp_{f.filename}")
            with open(temp_path, "wb") as buf:
                shutil.copyfileobj(f.file, buf)
            temp_files.append(temp_path)

            file_type = converter.detect_file_type(f.filename)
            target_ext_clean = target_ext.lower().lstrip('.')

            if target_ext_clean in ['png', 'jpg', 'jpeg', 'webp', 'bmp', 'tiff', 'ico', 'gif'] and file_type == 'image':
                out = converter.convert_image(temp_path, target_ext_clean, quality=quality)
                converted_filenames.append(out)
            elif target_ext_clean in ['mp3', 'wav', 'aac', 'flac', 'ogg', 'm4a', 'opus'] or file_type == 'audio':
                out = converter.convert_audio(temp_path, target_ext_clean, bitrate=audio_bitrate)
                converted_filenames.append(out)
            elif target_ext_clean in ['mp4', 'webm', 'mkv', 'avi', 'mov', 'gif'] or file_type == 'video':
                out = converter.convert_video(temp_path, target_ext_clean, resolution=resolution)
                converted_filenames.append(out)
            else:
                out = converter.convert_audio(temp_path, target_ext_clean, bitrate=audio_bitrate)
                converted_filenames.append(out)

        for p in temp_files:
            if os.path.exists(p):
                os.remove(p)

        if len(converted_filenames) == 1:
            encoded_fn = urllib.parse.quote(converted_filenames[0])
            return {
                "success": True,
                "multiple": False,
                "filename": converted_filenames[0],
                "download_url": f"/api/download-file/{encoded_fn}"
            }
        else:
            zip_filename = f"converted_bundle_{converter.uuid.uuid4().hex[:6]}.zip"
            zip_path = os.path.join(active_dir, zip_filename)
            with zipfile.ZipFile(zip_path, 'w') as zipf:
                for fn in converted_filenames:
                    fp = os.path.join(active_dir, fn)
                    if os.path.exists(fp):
                        zipf.write(fp, arcname=fn)

            encoded_zip = urllib.parse.quote(zip_filename)
            return {
                "success": True,
                "multiple": True,
                "filename": zip_filename,
                "download_url": f"/api/download-file/{encoded_zip}",
                "count": len(converted_filenames)
            }
    except Exception as e:
        for p in temp_files:
            if os.path.exists(p):
                os.remove(p)
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/system-status")
async def api_system_status():
    return {
        "status": "ok",
        "is_cloud": config.IS_CLOUD,
        "download_dir": config.get_download_dir()
    }

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 7860 if config.IS_CLOUD else 5000))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=False, log_config=None)
