from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from fastapi.responses import FileResponse
from pathlib import Path
import tempfile, os
import fitz  # PyMuPDF

router = APIRouter(prefix="", tags=["Watermark PDF"])


@router.post("/watermark-pdf")
async def watermark_pdf(
    file: UploadFile = File(...),
    text: str = Form("CONFIDENTIAL"),
):
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="File must be a PDF")

    if not text:
        raise HTTPException(status_code=400, detail="Watermark text is required")

    tmp_dir = Path(tempfile.mkdtemp())
    input_path = tmp_dir / file.filename
    output_path = tmp_dir / f"watermarked_{file.filename}"

    with input_path.open("wb") as f:
        f.write(await file.read())

    try:
        doc = fitz.open(input_path)

        for page_index in range(len(doc)):
            page = doc[page_index]
            rect = page.rect

            box_width = rect.width * 0.8
            box_height = 80
            x0 = (rect.width - box_width) / 2
            y0 = rect.height / 2 - box_height / 2
            watermark_rect = fitz.Rect(x0, y0, x0 + box_width, y0 + box_height)

            page.insert_textbox(
                watermark_rect,
                text,
                fontsize=50,
                color=(0.7, 0.7, 0.7),
            )

        doc.save(output_path)
        doc.close()
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Watermark failed: {e}")

    size_bytes = os.path.getsize(output_path)

    return FileResponse(
        output_path,
        media_type="application/pdf",
        filename=output_path.name,
        headers={"X-Output-Size": str(size_bytes)},
    )
