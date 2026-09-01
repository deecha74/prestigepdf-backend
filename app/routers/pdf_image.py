# app/routers/pdf_image.py
from fastapi import APIRouter, UploadFile, File, HTTPException, Query
from fastapi.responses import FileResponse
from pathlib import Path
import tempfile
import os
import fitz  # PyMuPDF
import zipfile

router = APIRouter(prefix="", tags=["PDF to Images"])


@router.post("/pdf-to-images")
async def pdf_to_images(
    file: UploadFile = File(...),
    image_format: str = Query("png", pattern="^(png|jpg|jpeg)$"),
    dpi: int = Query(150, ge=72, le=300),
):
    """
    Convert all pages of a PDF to images and return them as a ZIP.
    """
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="File must be a PDF")

    tmp_dir = Path(tempfile.mkdtemp())
    input_path = tmp_dir / file.filename
    base_name = input_path.stem
    images_dir = tmp_dir / "images"
    images_dir.mkdir(exist_ok=True)

    # save uploaded PDF
    with input_path.open("wb") as f:
        f.write(await file.read())

    try:
        doc = fitz.open(input_path)
        zoom = dpi / 72
        mat = fitz.Matrix(zoom, zoom)

        image_paths = []

        for page_index in range(len(doc)):
            page = doc.load_page(page_index)
            pix = page.get_pixmap(matrix=mat, alpha=False)
            img_name = f"{base_name}_page_{page_index + 1}.{image_format}"
            img_path = images_dir / img_name
            pix.save(str(img_path))
            image_paths.append(img_path)

        doc.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Conversion failed: {e}")

    # create ZIP
    zip_path = tmp_dir / f"{base_name}_images.zip"
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zipf:
        for img_path in image_paths:
            zipf.write(img_path, arcname=img_path.name)

    return FileResponse(
        zip_path,
        media_type="application/zip",
        filename=zip_path.name,
        headers={
            "X-Page-Count": str(len(image_paths)),
            "X-DPI": str(dpi),
            "X-Format": image_format,
        },
    )
