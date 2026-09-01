"""
session.py — Session-based PDF editing pipeline.

Full iLovePDF-style flow:
  1. POST /pdf/upload          → stores file, returns session_id + metadata
  2. GET  /pdf/{id}/page/{n}  → renders page as PNG (PyMuPDF)
  3. GET  /pdf/{id}/spans/{n} → extracts text spans with exact PyMuPDF coords
  4. POST /pdf/{id}/save      → applies edits, returns new PDF
  5. DELETE /pdf/{id}         → manual cleanup

Auto-cleanup: sessions older than 2 hours are deleted by a background thread.
"""

import io
import json
import os
import tempfile
import threading
import time
import uuid
from collections import defaultdict
from pathlib import Path

import pymupdf as fitz
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse, StreamingResponse

router = APIRouter(prefix="/pdf", tags=["PDF Session"])

# ── Session store ────────────────────────────────────────────────────────────
_sessions: dict = {}
_lock = threading.Lock()
SESSION_TTL = 7200  # 2 hours


def _auto_cleanup():
    """Background thread: delete sessions older than SESSION_TTL."""
    while True:
        time.sleep(300)  # every 5 min
        now = time.time()
        expired = [sid for sid, s in _sessions.items() if now - s["created"] > SESSION_TTL]
        for sid in expired:
            _remove_session(sid)


def _remove_session(sid: str):
    with _lock:
        info = _sessions.pop(sid, None)
    if info:
        try:
            if os.path.exists(info["path"]):
                os.remove(info["path"])
        except Exception:
            pass


threading.Thread(target=_auto_cleanup, daemon=True).start()


# ── Helpers ──────────────────────────────────────────────────────────────────

FONT_MAP = {
    "helvetica": "helv", "arial": "helv", "sans-serif": "helv",
    "times new roman": "tiro", "times": "tiro", "georgia": "tiro", "serif": "tiro",
    "courier new": "cour", "courier": "cour", "monospace": "cour",
}


def _pick_font(name: str) -> str:
    low = (name or "").lower()
    for k, v in FONT_MAP.items():
        if k in low:
            return v
    return "helv"


def _hex_to_rgb(hex_color: str) -> tuple:
    h = (hex_color or "#000000").lstrip("#").ljust(6, "0")
    try:
        return (int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255)
    except Exception:
        return (0.0, 0.0, 0.0)


def _int_to_hex(color_int: int) -> str:
    r = (color_int >> 16) & 0xFF
    g = (color_int >> 8) & 0xFF
    b = color_int & 0xFF
    return f"#{r:02x}{g:02x}{b:02x}"


def _get_session(session_id: str) -> dict:
    with _lock:
        info = _sessions.get(session_id)
    if not info:
        raise HTTPException(status_code=404, detail="Session not found or expired (> 2h). Please re-upload.")
    return info


# ── 1. Upload ────────────────────────────────────────────────────────────────

@router.post("/upload")
async def upload_pdf(file: UploadFile = File(...)):
    """
    Upload a PDF to the server for editing.
    Returns a session_id that identifies this editing session.
    The file is automatically deleted after 2 hours.
    """
    content = await file.read()

    if not content.startswith(b"%PDF"):
        raise HTTPException(status_code=400, detail="Not a valid PDF file.")

    tmp_path = tempfile.mktemp(suffix=".pdf")
    with open(tmp_path, "wb") as f:
        f.write(content)

    try:
        doc = fitz.open(tmp_path)
        page_count = doc.page_count
        first = doc[0]
        pw, ph = first.rect.width, first.rect.height
        doc.close()
    except Exception as e:
        os.remove(tmp_path)
        raise HTTPException(status_code=400, detail=f"Cannot parse PDF: {e}")

    sid = str(uuid.uuid4())
    with _lock:
        _sessions[sid] = {
            "path": tmp_path,
            "created": time.time(),
            "page_count": page_count,
            "filename": file.filename or "document.pdf",
        }

    return {
        "session_id": sid,
        "page_count": page_count,
        "width": pw,
        "height": ph,
        "filename": file.filename,
        "expires_in_seconds": SESSION_TTL,
    }


# ── 2. Render page as image ──────────────────────────────────────────────────

@router.get("/{session_id}/page/{page}")
async def render_page(session_id: str, page: int, dpi: int = 150):
    """
    Render a PDF page as a PNG image using PyMuPDF.
    DPI 150 = good quality for editing (you can increase to 200 for high-DPI screens).
    """
    info = _get_session(session_id)
    page_num = page - 1

    try:
        doc = fitz.open(info["path"])
        if page_num < 0 or page_num >= doc.page_count:
            doc.close()
            raise HTTPException(status_code=400, detail=f"Page {page} out of range")

        pg = doc[page_num]
        mat = fitz.Matrix(dpi / 72, dpi / 72)
        pix = pg.get_pixmap(matrix=mat, alpha=False)
        png_bytes = pix.tobytes("png")
        doc.close()
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Render failed: {e}")

    return StreamingResponse(
        io.BytesIO(png_bytes),
        media_type="image/png",
        headers={"Cache-Control": "private, max-age=30"},
    )


# ── 3. Extract text spans ────────────────────────────────────────────────────

@router.get("/{session_id}/spans/{page}")
async def get_spans(session_id: str, page: int):
    """
    Extract all text spans from a page using PyMuPDF.

    Coordinates use PyMuPDF's system (top-left origin, y increases downward, PDF points).
    Pre-computed percentage values (xPct, yPct, wPct, hPct) are provided for the
    frontend to position overlays without any coordinate math.

    span.origin = the exact baseline insertion point → pass this back when saving.
    span.bbox   = [x0, y0, x1, y1] for redaction → pass this back when saving.
    """
    info = _get_session(session_id)
    page_num = page - 1

    try:
        doc = fitz.open(info["path"])
        if page_num < 0 or page_num >= doc.page_count:
            doc.close()
            raise HTTPException(status_code=400, detail=f"Page {page} out of range")

        pg = doc[page_num]
        pw, ph = pg.rect.width, pg.rect.height

        spans = []
        idx = 0
        blocks = pg.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]

        for block in blocks:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                line_spans = line.get("spans", [])
                if not line_spans:
                    continue

                full_text = "".join(s.get("text", "") for s in line_spans)
                if not full_text.strip():
                    continue

                x0 = min(s["bbox"][0] for s in line_spans)
                y0 = min(s["bbox"][1] for s in line_spans)
                x1 = max(s["bbox"][2] for s in line_spans)
                y1 = max(s["bbox"][3] for s in line_spans)
                bbox = [x0, y0, x1, y1]

                first_span = line_spans[0]
                origin = list(first_span.get("origin", [x0, y1]))

                spans.append({
                    "id": f"span-p{page}-{idx}",
                    "text": full_text,
                    "bbox": bbox,
                    "origin": origin,
                    "size": round(float(first_span.get("size", 12)), 2),
                    "font": first_span.get("font", "Helvetica"),
                    "color": _int_to_hex(first_span.get("color", 0)),
                    # Pre-computed % positions for CSS overlay
                    "xPct": (x0 / pw) * 100,
                    "yPct": (y0 / ph) * 100,
                    "wPct": max(2.0, ((x1 - x0) / pw) * 100),
                    "hPct": max(0.8, ((y1 - y0) / ph) * 100),
                })
                idx += 1

        doc.close()
        return {"page": page, "width": pw, "height": ph, "spans": spans}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Span extraction failed: {e}")


# ── 4. Save edits ────────────────────────────────────────────────────────────

@router.post("/{session_id}/save")
async def save_pdf(session_id: str, edits: str = Form(...)):
    """
    Apply text edits to the PDF and return the modified file.

    edits: JSON array — only send MODIFIED spans:
    [
      {
        "page":         1,
        "text":         "new text",
        "originalText": "old text",
        "bbox":   [x0, y0, x1, y1],  // for redaction (exact PyMuPDF coords)
        "origin": [x, y],            // baseline insertion point
        "size":   10.5,
        "font":   "Helvetica-Bold",
        "color":  "#000000"
      }
    ]
    """
    info = _get_session(session_id)

    try:
        edit_list: list = json.loads(edits)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid edits JSON")

    if not edit_list:
        # No edits — just return the original file
        return FileResponse(
            info["path"],
            media_type="application/pdf",
            filename=info["filename"],
        )

    out_path = tempfile.mktemp(suffix="_edited.pdf")

    try:
        doc = fitz.open(info["path"])
        by_page = defaultdict(list)
        for edit in edit_list:
            pg_idx = max(0, int(edit.get("page", 1)) - 1)
            by_page[pg_idx].append(edit)

        # Pass 1 — Redact original text
        for pg_idx, page_edits in by_page.items():
            if pg_idx >= doc.page_count:
                continue
            pg = doc[pg_idx]
            for edit in page_edits:
                bbox = edit.get("bbox")
                if bbox and len(bbox) == 4:
                    rect = fitz.Rect(bbox[0], bbox[1], bbox[2], bbox[3])
                    rect = rect + (-1.0, -1.0, 1.0, 1.0)  # clean coverage of line box
                    pg.add_redact_annot(rect, fill=(1, 1, 1))

        # Pass 2 — Apply redactions
        for pg_idx in by_page:
            if pg_idx < doc.page_count:
                doc[pg_idx].apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

        # Pass 3 — Insert new text at exact origin points
        for pg_idx, page_edits in by_page.items():
            if pg_idx >= doc.page_count:
                continue
            pg = doc[pg_idx]
            pw, ph = pg.rect.width, pg.rect.height

            for edit in page_edits:
                new_text = edit.get("text", "").strip()
                if not new_text:
                    continue

                font_size = float(edit.get("size", 12))
                font_name = _pick_font(edit.get("font", ""))
                color = _hex_to_rgb(edit.get("color", "#000000"))

                # Use the exact origin returned by /spans (most accurate)
                origin = edit.get("origin")
                bbox = edit.get("bbox")

                if origin and len(origin) == 2:
                    ix, iy = float(origin[0]), float(origin[1])
                elif bbox and len(bbox) == 4:
                    ix, iy = float(bbox[0]), float(bbox[3])
                else:
                    continue

                ix = max(2.0, min(pw - 4.0, ix))
                iy = max(font_size, min(ph - 2.0, iy))

                for line_idx, line in enumerate(new_text.split("\n")):
                    safe = "".join(c for c in line if 32 <= ord(c) <= 126)
                    if not safe:
                        continue
                    line_y = iy + line_idx * font_size * 1.25
                    if line_y > ph - 2:
                        break
                    try:
                        pg.insert_text(
                            fitz.Point(ix, line_y),
                            safe,
                            fontname=font_name,
                            fontsize=font_size,
                            color=color,
                        )
                    except Exception as ex:
                        print(f"[WARN] insert_text p{pg_idx}: {ex}")

        doc.save(out_path, garbage=4, deflate=True, clean=True)
        doc.close()

    except Exception as e:
        if os.path.exists(out_path):
            os.remove(out_path)
        raise HTTPException(status_code=500, detail=f"Save failed: {e}")

    stem = Path(info["filename"]).stem
    return FileResponse(
        out_path,
        media_type="application/pdf",
        filename=f"{stem}_edited.pdf",
    )


# ── 5. Delete session ─────────────────────────────────────────────────────────

@router.delete("/{session_id}")
async def delete_session(session_id: str):
    """Manually delete a session and its temp file immediately."""
    _remove_session(session_id)
    return {"status": "deleted", "session_id": session_id}


# ── 6. Session info ──────────────────────────────────────────────────────────

@router.get("/{session_id}/info")
async def session_info(session_id: str):
    """Returns session metadata and time remaining."""
    info = _get_session(session_id)
    elapsed = time.time() - info["created"]
    remaining = max(0, SESSION_TTL - elapsed)
    return {
        "session_id": session_id,
        "filename": info["filename"],
        "page_count": info["page_count"],
        "expires_in_seconds": int(remaining),
    }
