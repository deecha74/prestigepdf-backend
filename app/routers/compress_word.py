# app/routers/compress_word.py
import io

from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from fastapi.responses import FileResponse, StreamingResponse
from pathlib import Path
import tempfile
import os
import fitz  # PyMuPDF
from pdf2docx import Converter
import pikepdf

router = APIRouter(prefix="", tags=["Compress & PDF to Word"])


from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from fastapi.responses import StreamingResponse
from pathlib import Path
import tempfile
import subprocess
import io

router = APIRouter()

GS_QUALITY_MAP = {
    "low": "/screen",  # smallest size, lowest quality
    "medium": "/ebook",  # balanced
    "high": "/printer",  # better quality, less compression
}


def ghostscript_compress(input_bytes: bytes, level: str = "medium") -> bytes:
    pdf_setting = GS_QUALITY_MAP.get(level, "/ebook")

    with tempfile.TemporaryDirectory() as tmpdir:
        tmpdir_path = Path(tmpdir)
        in_path = tmpdir_path / "input.pdf"
        out_path = tmpdir_path / "output.pdf"

        in_path.write_bytes(input_bytes)

        cmd = [
            "gs",
            "-sDEVICE=pdfwrite",
            "-dCompatibilityLevel=1.4",
            f"-dPDFSETTINGS={pdf_setting}",
            "-dNOPAUSE",
            "-dQUIET",
            "-dBATCH",
            f"-sOutputFile={out_path}",
            str(in_path),
        ]

        subprocess.check_call(cmd)
        return out_path.read_bytes()


@router.post("/compress")
async def compress_pdf(
    file: UploadFile = File(...),
    level: str = Query("medium", pattern="^(low|medium|high)$"),
):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="File must be a PDF")

    input_bytes = await file.read()

    try:
        output_bytes = ghostscript_compress(input_bytes, level=level)
    except subprocess.CalledProcessError as e:
        raise HTTPException(status_code=500, detail=f"Ghostscript failed: {e}")

    original_size = len(input_bytes)
    compressed_size = len(output_bytes)
    reduction = (
        round((1 - compressed_size / original_size) * 100, 1)
        if original_size > 0
        else 0
    )

    return StreamingResponse(
        io.BytesIO(output_bytes),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'attachment; filename="compressed_{file.filename}"',
            "X-Original-Size": str(original_size),
            "X-Compressed-Size": str(compressed_size),
            "X-Reduction-Percent": str(reduction),
            "X-Level": level,
        },
    )


@router.post("/pdf-to-word")
async def pdf_to_word(file: UploadFile = File(...)):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="File must be a PDF")

    tmp_dir = Path(tempfile.mkdtemp())
    input_path = tmp_dir / file.filename
    output_filename = file.filename.replace(".pdf", ".docx")
    output_path = tmp_dir / output_filename

    with input_path.open("wb") as f:
        f.write(await file.read())

    try:
        cv = Converter(str(input_path))
        cv.convert(str(output_path))
        cv.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Conversion failed: {e}")

    if not output_path.exists():
        raise HTTPException(status_code=500, detail="Output file not created")

    return FileResponse(
        output_path,
        media_type=(
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
        ),
        filename=output_filename,
    )
