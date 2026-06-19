"""
Update logic: check GitHub releases, download new exe, apply via helper batch.
"""
import sys
import os
import tempfile
import threading
import urllib.request
import urllib.error
import json
from pathlib import Path
from typing import Optional

from version import __version__, GITHUB_REPO

API_URL = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
EXE_ASSET_NAME = "IntermitDoc.exe"


def _parse_version(tag: str) -> tuple:
    """Convert 'v1.2.3' or '1.2.3' to (1, 2, 3)."""
    return tuple(int(x) for x in tag.lstrip("v").split("."))


def check_for_update() -> Optional[dict]:
    """
    Returns release info dict if a newer version is available, else None.
    Raises on network error.
    """
    req = urllib.request.Request(
        API_URL,
        headers={"Accept": "application/vnd.github+json", "User-Agent": "IntermitDoc"},
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        data = json.loads(resp.read().decode())

    remote_tag = data.get("tag_name", "")
    try:
        if _parse_version(remote_tag) > _parse_version(__version__):
            asset_url = next(
                (a["browser_download_url"] for a in data.get("assets", [])
                 if a["name"] == EXE_ASSET_NAME),
                None,
            )
            return {
                "version": remote_tag,
                "url": asset_url,
                "notes": data.get("body", ""),
                "published_at": data.get("published_at", ""),
            }
    except (ValueError, TypeError):
        pass
    return None


def _current_exe() -> Path:
    """Path to the running exe (works both frozen and dev)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable)
    # In dev mode, simulate path for testing
    return Path(sys.executable)


def download_and_apply(url: str, progress_cb=None, done_cb=None, error_cb=None):
    """
    Downloads the new exe to a temp file, writes an updater.bat, launches it,
    then exits the app. Runs in a background thread.
    """
    def _run():
        try:
            tmp = tempfile.NamedTemporaryFile(
                delete=False, suffix=".exe", prefix="IntermitDoc_new_"
            )
            tmp_path = Path(tmp.name)

            # Download with progress
            req = urllib.request.Request(url, headers={"User-Agent": "IntermitDoc"})
            with urllib.request.urlopen(req, timeout=60) as resp:
                total = int(resp.headers.get("Content-Length", 0))
                downloaded = 0
                chunk = 65536
                while True:
                    data = resp.read(chunk)
                    if not data:
                        break
                    tmp.write(data)
                    downloaded += len(data)
                    if progress_cb and total:
                        progress_cb(downloaded / total)
            tmp.close()

            if progress_cb:
                progress_cb(1.0)

            exe_path = _current_exe()
            bat_path = exe_path.parent / "_updater_run.bat"
            bat_path.write_text(
                f'@echo off\n'
                f'timeout /t 2 /nobreak >nul\n'
                f'copy /y "{tmp_path}" "{exe_path}"\n'
                f'start "" "{exe_path}"\n'
                f'del "%~f0"\n',
                encoding="ascii",
            )

            if done_cb:
                done_cb(str(bat_path))

        except Exception as exc:
            if error_cb:
                error_cb(str(exc))

    threading.Thread(target=_run, daemon=True).start()


def launch_updater_and_exit(bat_path: str):
    """Launch the updater batch and close the app."""
    os.startfile(bat_path)
    sys.exit(0)
