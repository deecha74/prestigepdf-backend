"""
compress.py — PDF compression using pikepdf (lossless) with optional
Ghostscript subprocess for aggressive image downsampling.
"""

import os
import subprocess
import tempfile

import pikepdf
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from routers.utils import cleanup, save_upload

router = APIRouter()


def _ghostscript_compress(in_path: str, out_path: str, level: str) -> bool:
    """
    Try to run Ghostscript for high-quality compression.
    Returns True on success, False if GS is not installed.
    """
    settings_map = {
        "low": "/printer",
        "medium": "/ebook",
        "high": "/screen",
    }
    gs_setting = settings_map.get(level, "/ebook")

    gs_cmd = None
    for candidate in ["gswin64c", "gswin32c", "gs"]:
        if subprocess.run(
            ["where", candidate], capture_output=True, shell=True
        ).returncode == 0:
            gs_cmd = candidate
            break

    if not gs_cmd:
        return False

    try:
        result = subprocess.run(
            [
                gs_cmd,
                "-sDEVICE=pdfwrite",
                "-dCompatibilityLevel=1.4",
                f"-dPDFSETTINGS={gs_setting}",
                "-dNOPAUSE",
                "-dQUIET",
                "-dBATCH",
                f"-sOutputFile={out_path}",
                in_path,
            ],
            timeout=120,
            capture_output=True,
        )
        return result.returncode == 0 and os.path.exists(out_path)
    except Exception:
        return False


@router.post("/compress")
async def compress_pdf(
    file: UploadFile = File(...),
    level: str = Form("medium"),
):
    """
    Compress a PDF.
    - low: lossless stream rewrite (pikepdf, fast)
    - medium: Ghostscript /ebook (150 DPI images) or pikepdf fallback
    - high: Ghostscript /screen (72 DPI images) or pikepdf fallback
    """
    in_path = await save_upload(file, suffix=".pdf")
    out_path = tempfile.mktemp(suffix="_compressed.pdf")

    try:
        if level in ("medium", "high"):
            gs_ok = _ghostscript_compress(in_path, out_path, level)
            if gs_ok:
                cleanup(in_path)
                return FileResponse(
                    out_path,
                    media_type="application/pdf",
                    filename="compressed.pdf",
                )

        # Fallback: pikepdf lossless rewrite
        with pikepdf.open(in_path) as pdf:
            pdf.save(
                out_path,
                compress_streams=True,
                object_stream_mode=pikepdf.ObjectStreamMode.generate,
                recompress_flate=True,
            )

    except Exception as e:
        cleanup(in_path, out_path)
        raise HTTPException(status_code=500, detail=f"Compression failed: {str(e)}")

    cleanup(in_path)
    return FileResponse(
        out_path,
        media_type="application/pdf",
        filename="compressed.pdf",
    )
