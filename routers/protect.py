"""
protect.py — PDF password protection and unlocking using pikepdf.
pikepdf uses QPDF under the hood for robust encryption handling.
"""

import tempfile

import pikepdf
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from routers.utils import cleanup, save_upload

router = APIRouter()


@router.post("/protect-pdf")
async def protect_pdf(
    file: UploadFile = File(...),
    password: str = Form(...),
):
    """
    Apply AES-256 password protection to a PDF.
    Both user password (open) and owner password are set.
    """
    in_path = await save_upload(file, suffix=".pdf")
    out_path = tempfile.mktemp(suffix="_protected.pdf")

    try:
        with pikepdf.open(in_path) as pdf:
            encryption = pikepdf.Encryption(
                user=password,
                owner=password + "_owner",
                R=6,  # AES-256
                allow=pikepdf.Permissions(
                    print_highres=True,
                    extract=False,
                    modify_annotation=False,
                    modify_other=False,
                ),
            )
            pdf.save(out_path, encryption=encryption)

    except Exception as e:
        cleanup(in_path, out_path)
        raise HTTPException(
            status_code=500, detail=f"PDF protection failed: {str(e)}"
        )

    cleanup(in_path)
    return FileResponse(
        out_path,
        media_type="application/pdf",
        filename="protected.pdf",
    )


@router.post("/unlock-pdf")
async def unlock_pdf(
    file: UploadFile = File(...),
    password: str = Form(""),
):
    """
    Remove password protection from a PDF.
    Provide the user/owner password; if empty, attempts to open without password.
    """
    in_path = await save_upload(file, suffix=".pdf")
    out_path = tempfile.mktemp(suffix="_unlocked.pdf")

    try:
        open_kwargs = {}
        if password:
            open_kwargs["password"] = password

        with pikepdf.open(in_path, **open_kwargs) as pdf:
            pdf.save(out_path)

    except pikepdf.PasswordError:
        cleanup(in_path, out_path)
        raise HTTPException(
            status_code=403,
            detail="Incorrect password. Please provide the correct PDF password.",
        )
    except Exception as e:
        cleanup(in_path, out_path)
        raise HTTPException(
            status_code=500, detail=f"PDF unlock failed: {str(e)}"
        )

    cleanup(in_path)
    return FileResponse(
        out_path,
        media_type="application/pdf",
        filename="unlocked.pdf",
    )
