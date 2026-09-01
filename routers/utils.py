"""
Shared utility helpers for PrestigePDF FastAPI routers.
"""
import os
import tempfile
import shutil
from pathlib import Path
from fastapi import UploadFile


async def save_upload(upload: UploadFile, suffix: str = ".pdf") -> str:
    """Save an UploadFile to a temp file and return the path."""
    tmp = tempfile.mktemp(suffix=suffix)
    content = await upload.read()
    with open(tmp, "wb") as f:
        f.write(content)
    return tmp


def cleanup(*paths: str) -> None:
    """Delete temp files, ignoring errors."""
    for p in paths:
        try:
            if p and os.path.exists(p):
                os.remove(p)
        except Exception:
            pass


def cleanup_dir(dirpath: str) -> None:
    """Delete a temp directory tree, ignoring errors."""
    try:
        if dirpath and os.path.isdir(dirpath):
            shutil.rmtree(dirpath, ignore_errors=True)
    except Exception:
        pass


def make_tmp_dir() -> str:
    """Create and return a new temp directory path."""
    d = tempfile.mkdtemp()
    return d


def get_extension(filename: str) -> str:
    return Path(filename).suffix.lower()
