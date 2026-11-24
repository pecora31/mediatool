import os
import uuid
import re
import threading
from typing import Dict, Any, Optional
import yt_dlp
import config

TASKS: Dict[str, Dict[str, Any]] = {}

YOUTUBE_EXTRACTOR_ARGS = {
    'youtube': {
        'player_client': ['android', 'ios', 'web']
    }
}

def normalize_url(url: str) -> str:
    cleaned = url.strip()
    shorts_match = re.search(r'youtube\.com/shorts/([a-zA-Z0-9_-]+)', cleaned)
    if shorts_match:
        video_id = shorts_match.group(1)
        return f'https://www.youtube.com/watch?v={video_id}'
    return cleaned

def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/*?:"<>|,;]', '', name)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned[:100] if cleaned else "video"

def get_video_info(url: str) -> Dict[str, Any]:
    target_url = normalize_url(url)
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': False,
        'noplaylist': True,
        'extractor_args': YOUTUBE_EXTRACTOR_ARGS,
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(target_url, download=False)
        if not info:
            raise ValueError("Unable to retrieve video information.")

        title = info.get('title', 'Video')
        thumbnail = info.get('thumbnail', '')
        duration = info.get('duration', 0)
        uploader = info.get('uploader') or info.get('channel') or ''

        formats = info.get('formats', [])
        resolutions = set()
        for f in formats:
            height = f.get('height')
            vcodec = f.get('vcodec')
            if height and isinstance(height, int) and height >= 144 and vcodec != 'none':
                resolutions.add(height)

        return {
            "title": title,
            "thumbnail": thumbnail,
            "duration": duration,
            "uploader": uploader,
            "resolutions": sorted(list(resolutions), reverse=True)
        }

def _run_download(task_id: str, url: str, format_choice: str, quality: str):
    target_url = normalize_url(url)
    task = TASKS[task_id]
    task["status"] = "downloading"
    task["progress"] = 0
    task["speed"] = ""
    task["eta"] = ""

    # Get active download folder dynamically
    download_dir = config.get_download_dir()
    os.makedirs(download_dir, exist_ok=True)

    def progress_hook(d):
        if d['status'] == 'downloading':
            total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
            downloaded = d.get('downloaded_bytes', 0)
            if total > 0:
                task["progress"] = round((downloaded / total) * 100, 1)

            speed = d.get('speed')
            if speed:
                task["speed"] = f"{speed / (1024 * 1024):.1f} MB/s" if speed > 1024 * 1024 else f"{speed / 1024:.1f} KB/s"

            eta = d.get('eta')
            if eta:
                task["eta"] = f"{eta}s"
        elif d['status'] == 'finished':
            task["status"] = "processing"
            task["progress"] = 99

    out_template = os.path.join(download_dir, f"{task_id}_%(title).100s.%(ext)s")

    ydl_opts: Dict[str, Any] = {
        'outtmpl': out_template,
        'progress_hooks': [progress_hook],
        'noplaylist': True,
        'quiet': True,
        'no_warnings': True,
        'extractor_args': YOUTUBE_EXTRACTOR_ARGS,
    }

    if format_choice == 'audio':
        ydl_opts.update({
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '320',
            }],
        })
    else:
        if quality and quality != 'best' and quality.isdigit():
            target_h = int(quality)
            ydl_opts.update({
                'format': f'bestvideo[height<={target_h}]+bestaudio/best[height<={target_h}]/best',
                'merge_output_format': 'mp4',
            })
        else:
            ydl_opts.update({
                'format': 'bestvideo+bestaudio/best',
                'merge_output_format': 'mp4',
            })

    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            extracted_info = ydl.extract_info(url, download=True)
            raw_title = extracted_info.get('title', 'video') if extracted_info else 'video'

        downloaded_files = [f for f in os.listdir(download_dir) if f.startswith(task_id + "_")]
        if downloaded_files:
            original_filename = downloaded_files[0]
            clean_display_name = original_filename[len(task_id) + 1:]
            
            old_full_path = os.path.join(download_dir, original_filename)
            new_full_path = os.path.join(download_dir, clean_display_name)
            
            if not os.path.exists(new_full_path):
                try:
                    os.rename(old_full_path, new_full_path)
                    final_path = new_full_path
                    final_name = clean_display_name
                except Exception:
                    final_path = old_full_path
                    final_name = original_filename
            else:
                final_path = old_full_path
                final_name = original_filename

            task["status"] = "completed"
            task["progress"] = 100
            task["filename"] = final_name
            task["display_name"] = clean_display_name
            task["file_path"] = final_path
        else:
            task["status"] = "error"
            task["error"] = "Output file not found."
    except Exception as e:
        task["status"] = "error"
        task["error"] = str(e)

def create_download_task(url: str, format_choice: str = "video", quality: str = "best") -> str:
    task_id = str(uuid.uuid4())[:8]
    TASKS[task_id] = {
        "id": task_id,
        "url": url,
        "format": format_choice,
        "quality": quality,
        "status": "queued",
        "progress": 0,
        "speed": "",
        "eta": "",
        "filename": None,
        "display_name": None,
        "file_path": None,
        "error": None
    }
    t = threading.Thread(target=_run_download, args=(task_id, url, format_choice, quality), daemon=True)
    t.start()
    return task_id

def get_task_status(task_id: str) -> Optional[Dict[str, Any]]:
    return TASKS.get(task_id)
