from fastapi import APIRouter, UploadFile, File, HTTPException, Form
from fastapi.responses import FileResponse
from pathlib import Path
import tempfile, os
from pypdf import PdfReader, PdfWriter

router = APIRouter(prefix="", tags=["Protect PDF"])


@router.post("/protect-pdf")
async def protect_pdf(
    file: UploadFile = File(...),
    password: str = Form(...),
):
    """
    Add an open-password to a PDF.
    """
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="File must be a PDF")

    if not password:
        raise HTTPException(status_code=400, detail="Password is required")

    tmp_dir = Path(tempfile.mkdtemp())
    input_path = tmp_dir / file.filename
    output_path = tmp_dir / f"protected_{file.filename}"

    # save uploaded PDF
    with input_path.open("wb") as f:
        f.write(await file.read())

    try:
        reader = PdfReader(str(input_path))
        writer = PdfWriter()

        for page in reader.pages:
            writer.add_page(page)

        # simple user password; AES-256 by default on new versions
        writer.encrypt(password)  # or writer.encrypt(user_password=password)
        with output_path.open("wb") as f:
            writer.write(f)

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Protection failed: {e}")

    size_bytes = os.path.getsize(output_path)

    return FileResponse(
        output_path,
        media_type="application/pdf",
        filename=output_path.name,
        headers={
            "X-Output-Size": str(size_bytes),
            "X-Protection": "password",
        },
    )


@router.post("/unlock-pdf")
async def unlock_pdf(
    file: UploadFile = File(...),
    password: str = Form(...),
):
    """
    Remove password from a protected PDF using the correct password.
    """
    if file.content_type != "application/pdf":
        raise HTTPException(status_code=400, detail="File must be a PDF")
    if not password:
        raise HTTPException(status_code=400, detail="Password is required")

    tmp_dir = Path(tempfile.mkdtemp())
    input_path = tmp_dir / file.filename
    output_path = tmp_dir / f"unlocked_{file.filename}"

    with input_path.open("wb") as f:
        f.write(await file.read())

    try:
        reader = PdfReader(str(input_path))

        # Try to decrypt
        if reader.is_encrypted:
            ok = reader.decrypt(password)
            # pypdf returns 0/1/2 depending on which password matched
            if ok == 0:
                raise HTTPException(status_code=401, detail="Wrong password")
        else:
            raise HTTPException(status_code=400, detail="PDF is not password-protected")

        writer = PdfWriter()
        for page in reader.pages:
            writer.add_page(page)

        # Do NOT call writer.encrypt() => output is unprotected
        with output_path.open("wb") as f:
            writer.write(f)

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unlock failed: {e}")

    return FileResponse(
        output_path,
        media_type="application/pdf",
        filename=output_path.name,
    )
