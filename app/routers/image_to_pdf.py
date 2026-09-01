# app/routers/image_pdf.py
from fastapi import APIRouter, UploadFile, File, HTTPException
from fastapi.responses import FileResponse
from pathlib import Path
import tempfile, os
from typing import List
from PIL import Image

router = APIRouter(prefix="", tags=["Image to PDF"])


@router.post("/image-to-pdf")
async def image_to_pdf(files: List[UploadFile] = File(...)):
    """
    Accept multiple images and merge them into a single PDF (one page per image).
    Order = order of files in the request.
    """
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    tmp_dir = Path(tempfile.mkdtemp())
    image_paths = []

    # Save uploads and normalize to RGB
    pil_images = []
    for idx, upload in enumerate(files):
        if not upload.content_type.startswith("image/"):
            raise HTTPException(status_code=400, detail="All files must be images")

        img_path = tmp_dir / f"page_{idx}_{upload.filename}"
        with img_path.open("wb") as f:
            f.write(await upload.read())
        image_paths.append(img_path)

        img = Image.open(img_path)
        if img.mode != "RGB":
            img = img.convert("RGB")
        pil_images.append(img)

    if not pil_images:
        raise HTTPException(status_code=400, detail="No valid images")

    output_path = tmp_dir / "merged_images.pdf"

    # First image + append others
    first, *rest = pil_images
    first.save(output_path, save_all=True, append_images=rest)

    size_bytes = os.path.getsize(output_path)

    return FileResponse(
        output_path,
        media_type="application/pdf",
        filename="images.pdf",
        headers={"X-Output-Size": str(size_bytes)},
    )
