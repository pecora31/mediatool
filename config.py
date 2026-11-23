import os
import sys
import json
import subprocess
import ctypes

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(BASE_DIR, "config.json")

# Detect if running in Cloud container (Hugging Face Spaces, Render, etc.)
IS_CLOUD = (
    os.environ.get("IS_CLOUD", "").lower() == "true" or
    os.environ.get("SPACE_ID") is not None or
    os.environ.get("RENDER") is not None or
    sys.platform != "win32"
)

CLOUD_DOWNLOAD_DIR = os.path.join(BASE_DIR, "downloads")
DEFAULT_LOCAL_DIR = os.path.join(os.path.expanduser("~"), "Downloads")

def get_download_dir() -> str:
    if IS_CLOUD:
        os.makedirs(CLOUD_DOWNLOAD_DIR, exist_ok=True)
        return CLOUD_DOWNLOAD_DIR

    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
                d = data.get("download_dir")
                if d and os.path.exists(d):
                    return d
        except Exception:
            pass
    return DEFAULT_LOCAL_DIR

def set_download_dir(new_dir: str) -> str:
    if IS_CLOUD:
        return CLOUD_DOWNLOAD_DIR

    cleaned = os.path.abspath(new_dir.strip())
    os.makedirs(cleaned, exist_ok=True)
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump({"download_dir": cleaned}, f, indent=2)
    return cleaned

def open_in_foreground(target_path: str, is_folder: bool = False, select_file: str = None):
    if IS_CLOUD or sys.platform != "win32":
        return

    try:
        ctypes.windll.user32.AllowSetForegroundWindow(0xFFFFFFFF)
    except Exception:
        pass

    if is_folder:
        if select_file and os.path.exists(select_file):
            norm_file = os.path.normpath(select_file)
            ps_cmd = (
                f"$ws = New-Object -ComObject WScript.Shell; "
                f"Start-Process explorer.exe -ArgumentList '/select,\"{norm_file}\"'; "
                f"Start-Sleep -Milliseconds 400; "
                f"$ws.AppActivate('File Explorer'); "
                f"$ws.AppActivate('Explorer');"
            )
        else:
            norm_folder = os.path.normpath(target_path)
            ps_cmd = (
                f"$ws = New-Object -ComObject WScript.Shell; "
                f"Start-Process explorer.exe -ArgumentList '\"{norm_folder}\"'; "
                f"Start-Sleep -Milliseconds 400; "
                f"$ws.AppActivate('File Explorer'); "
                f"$ws.AppActivate('Explorer');"
            )
    else:
        norm_path = os.path.normpath(target_path)
        ps_cmd = (
            f"$ws = New-Object -ComObject WScript.Shell; "
            f"$p = Start-Process '{norm_path}' -PassThru; "
            f"Start-Sleep -Milliseconds 600; "
            f"if ($p) {{ $ws.AppActivate($p.Id) }};"
        )

    subprocess.Popen(
        ["powershell", "-WindowStyle", "Hidden", "-NoProfile", "-Command", ps_cmd],
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
    )
