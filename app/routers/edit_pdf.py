# app/routers/edit_pdf.py
from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from fastapi.responses import FileResponse
from pathlib import Path
import tempfile, os
import fitz  # PyMuPDF

router = APIRouter(prefix="", tags=["Edit PDF"])


@router.post("/editpdf/add-text")
async def add_text_annotation(
    file: UploadFile = File(...),
    text: str = Form(...),
    page: int = Form(1),  # 1-based page number
    x: float = Form(100),  # X position in points
    y: float = Form(100),  # Y position in points
):
    """
    Add a text annotation (like a sticky note) to a PDF.
    """
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="File must be a PDF")

    tmp_dir = Path(tempfile.mkdtemp())
    input_path = tmp_dir / file.filename
    output_path = tmp_dir / f"edited_{file.filename}"

    with input_path.open("wb") as f:
        f.write(await file.read())

    try:
        doc = fitz.open(input_path)

        if page < 1 or page > len(doc):
            raise HTTPException(status_code=400, detail="Invalid page number")

        page_obj = doc[page - 1]

        # Add a text annotation at (x, y)
        annot = page_obj.add_text_annot((x, y), text)
        annot.set_colors({"stroke": (1, 0, 0), "fill": (1, 1, 0)})  # red/yellow
        annot.update()

        doc.save(output_path)
        doc.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Edit failed: {e}")

    size_bytes = os.path.getsize(output_path)

    return FileResponse(
        output_path,
        media_type="application/pdf",
        filename=output_path.name,
        headers={"X-Output-Size": str(size_bytes)},
    )
