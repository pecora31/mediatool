import os
import subprocess
import uuid
from typing import Dict, Any, Optional
from PIL import Image
import config

IMAGE_EXTENSIONS = {'.png', '.jpg', '.jpeg', '.webp', '.bmp', '.tiff', '.tif', '.gif', '.ico'}
AUDIO_EXTENSIONS = {'.mp3', '.wav', '.aac', '.flac', '.ogg', '.m4a', '.opus', '.wma'}
VIDEO_EXTENSIONS = {'.mp4', '.mkv', '.webm', '.avi', '.mov', '.flv', '.wmv', '.m4v', '.ts'}

def detect_file_type(filename: str) -> str:
    ext = os.path.splitext(filename)[1].lower()
    if ext in IMAGE_EXTENSIONS:
        return 'image'
    elif ext in AUDIO_EXTENSIONS:
        return 'audio'
    elif ext in VIDEO_EXTENSIONS:
        return 'video'
    return 'unknown'

def convert_image(
    input_path: str,
    target_ext: str,
    quality: int = 90,
    resize_width: Optional[int] = None,
    resize_height: Optional[int] = None
) -> str:
    download_dir = config.get_download_dir()
    os.makedirs(download_dir, exist_ok=True)

    target_ext = target_ext.lower().lstrip('.')
    base_name = os.path.splitext(os.path.basename(input_path))[0]
    out_filename = f"{base_name}.{target_ext}"
    output_path = os.path.join(download_dir, out_filename)
    
    if os.path.exists(output_path):
        out_filename = f"{base_name}_{uuid.uuid4().hex[:4]}.{target_ext}"
        output_path = os.path.join(download_dir, out_filename)

    with Image.open(input_path) as img:
        if resize_width and resize_height:
            img = img.resize((resize_width, resize_height), Image.Resampling.LANCZOS)
        elif resize_width:
            w_percent = (resize_width / float(img.size[0]))
            h_size = int((float(img.size[1]) * float(w_percent)))
            img = img.resize((resize_width, h_size), Image.Resampling.LANCZOS)

        if target_ext in ['jpg', 'jpeg']:
            if img.mode in ('RGBA', 'LA', 'P'):
                background = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                background.paste(img, mask=img.split()[3])
                img = background
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            img.save(output_path, 'JPEG', quality=quality, optimize=True)
        elif target_ext == 'png':
            img.save(output_path, 'PNG', optimize=True)
        elif target_ext == 'webp':
            img.save(output_path, 'WEBP', quality=quality)
        elif target_ext == 'ico':
            ico_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
            img.save(output_path, format='ICO', sizes=ico_sizes)
        elif target_ext == 'bmp':
            if img.mode != 'RGB':
                img = img.convert('RGB')
            img.save(output_path, 'BMP')
        elif target_ext in ['tiff', 'tif']:
            img.save(output_path, 'TIFF')
        elif target_ext == 'gif':
            img.save(output_path, 'GIF')
        else:
            img.save(output_path)

    return out_filename

def convert_audio(
    input_path: str,
    target_ext: str,
    bitrate: str = "320k"
) -> str:
    download_dir = config.get_download_dir()
    os.makedirs(download_dir, exist_ok=True)

    target_ext = target_ext.lower().lstrip('.')
    base_name = os.path.splitext(os.path.basename(input_path))[0]
    out_filename = f"{base_name}.{target_ext}"
    output_path = os.path.join(download_dir, out_filename)
    
    if os.path.exists(output_path):
        out_filename = f"{base_name}_{uuid.uuid4().hex[:4]}.{target_ext}"
        output_path = os.path.join(download_dir, out_filename)

    cmd = ["ffmpeg", "-y", "-i", input_path]
    if target_ext == 'mp3':
        cmd += ["-c:a", "libmp3lame", "-b:a", bitrate]
    elif target_ext == 'wav':
        cmd += ["-c:a", "pcm_s16le"]
    elif target_ext == 'aac':
        cmd += ["-c:a", "aac", "-b:a", bitrate]
    elif target_ext == 'flac':
        cmd += ["-c:a", "flac"]
    elif target_ext == 'ogg':
        cmd += ["-c:a", "libvorbis", "-b:a", bitrate]
    elif target_ext == 'm4a':
        cmd += ["-c:a", "aac", "-b:a", bitrate]
    elif target_ext == 'opus':
        cmd += ["-c:a", "libopus", "-b:a", bitrate]
    else:
        cmd += ["-b:a", bitrate]

    cmd.append(output_path)
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore')
    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg error: {res.stderr[-400:]}")

    return out_filename

def convert_video(
    input_path: str,
    target_ext: str,
    resolution: str = "original",
    video_bitrate: Optional[str] = None
) -> str:
    download_dir = config.get_download_dir()
    os.makedirs(download_dir, exist_ok=True)

    target_ext = target_ext.lower().lstrip('.')
    base_name = os.path.splitext(os.path.basename(input_path))[0]
    out_filename = f"{base_name}.{target_ext}"
    output_path = os.path.join(download_dir, out_filename)

    if os.path.exists(output_path):
        out_filename = f"{base_name}_{uuid.uuid4().hex[:4]}.{target_ext}"
        output_path = os.path.join(download_dir, out_filename)

    if target_ext == 'gif':
        scale_filter = "scale=480:-1:flags=lanczos"
        if resolution == '720p':
            scale_filter = "scale=720:-1:flags=lanczos"
        elif resolution == '360p':
            scale_filter = "scale=360:-1:flags=lanczos"
            
        vf = f"fps=15,{scale_filter},split[s0][s1];[s0]palettegen[p];[s1][p]paletteuse"
        cmd = ["ffmpeg", "-y", "-i", input_path, "-vf", vf, output_path]
        res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore')
        if res.returncode != 0:
            raise RuntimeError(f"FFmpeg GIF error: {res.stderr[-400:]}")
        return out_filename

    cmd = ["ffmpeg", "-y", "-i", input_path]
    scale_dict = {
        "1080p": "scale=-2:1080",
        "720p": "scale=-2:720",
        "480p": "scale=-2:480",
        "360p": "scale=-2:360"
    }
    if resolution in scale_dict:
        cmd += ["-vf", scale_dict[resolution]]

    if target_ext == 'mp4':
        cmd += ["-c:v", "libx264", "-preset", "fast", "-crf", "22", "-c:a", "aac", "-b:a", "192k"]
    elif target_ext == 'webm':
        cmd += ["-c:v", "libvpx-vp9", "-crf", "30", "-b:v", "0", "-c:a", "libopus"]
    elif target_ext == 'mkv':
        cmd += ["-c:v", "libx264", "-c:a", "aac"]
    elif target_ext == 'avi':
        cmd += ["-c:v", "mpeg4", "-qscale:v", "3", "-c:a", "libmp3lame"]
    elif target_ext == 'mov':
        cmd += ["-c:v", "libx264", "-c:a", "aac"]

    cmd.append(output_path)
    res = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='ignore')
    if res.returncode != 0:
        raise RuntimeError(f"FFmpeg error: {res.stderr[-400:]}")

    return out_filename
