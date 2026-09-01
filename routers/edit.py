"""
edit.py — True stream-level PDF text editing using PyMuPDF.

COORDINATE SYSTEM NOTE:
  PyMuPDF uses TOP-LEFT origin, y increases DOWNWARD.
  This matches the HTML canvas / pdf.js coordinate system exactly.
  NO y-axis flip needed when converting from canvas percentages.

Strategy (iLovePDF-style):
  1. Redact the original text span using its exact bounding box (originalBbox).
  2. Apply redactions — cleanly erases glyphs without touching surrounding art.
  3. Insert new text at the same position using the saved origin point.
"""

import json
import os
import tempfile
from typing import List

import pymupdf as fitz
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse

from routers.utils import cleanup, save_upload

router = APIRouter()


# Map CSS font-family names to PyMuPDF base-14 font names
FONT_MAP = {
    "helvetica": "helv",
    "arial": "helv",
    "sans-serif": "helv",
    "times new roman": "tiro",
    "times": "tiro",
    "serif": "tiro",
    "courier new": "cour",
    "courier": "cour",
    "monospace": "cour",
    "georgia": "tiro",
}


def _pick_font(family: str) -> str:
    lower = (family or "").lower().strip()
    for key, val in FONT_MAP.items():
        if key in lower:
            return val
    return "helv"


def _parse_color(hex_color: str) -> tuple:
    """Convert #RRGGBB → (r, g, b) floats 0–1."""
    h = (hex_color or "#000000").lstrip("#")
    if len(h) < 6:
        h = h.ljust(6, "0")
    try:
        return (int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255)
    except Exception:
        return (0.0, 0.0, 0.0)


@router.post("/edit-pdf")
async def edit_pdf(
    file: UploadFile = File(...),
    annotations: str = Form(...),
):
    """
    Perform true stream-level text editing on a PDF.

    Annotation fields:
      page          int    1-indexed page number
      text          str    replacement text to insert
      isOriginal    bool   if true AND text unchanged → skip
      x             float  left edge as % of page width  (0–100, top-left origin)
      y             float  top  edge as % of page height (0–100, top-left origin)
      fontSize      float  font size in points
      fontFamily    str    CSS font-family string
      color         str    #RRGGBB hex string
      originalBbox  list   [x0, y0, x1, y1] in PDF points (top-left origin)
                           used for precise redaction of original text
    """
    in_path = await save_upload(file, suffix=".pdf")
    out_path = tempfile.mktemp(suffix="_edited.pdf")

    try:
        annots: List[dict] = json.loads(annotations)
    except Exception:
        cleanup(in_path)
        raise HTTPException(status_code=400, detail="Invalid annotations JSON")

    # Only process annotations that were actually modified
    modified = [
        a for a in annots
        if not a.get("isOriginal") or a.get("text") != a.get("originalText")
    ]

    # Skip if nothing changed
    if not modified:
        cleanup(in_path)
        raise HTTPException(status_code=400, detail="No modifications detected")

    try:
        doc = fitz.open(in_path)

        # ── PASS 1: Add redaction annotations for all modified spans ──────────
        for anno in modified:
            page_num = max(0, int(anno.get("page", 1)) - 1)
            if page_num >= doc.page_count:
                continue

            orig_bbox = anno.get("originalBbox")
            if orig_bbox and len(orig_bbox) == 4:
                page = doc[page_num]
                # originalBbox is already in PyMuPDF space (top-left, y-down)
                rect = fitz.Rect(
                    float(orig_bbox[0]),
                    float(orig_bbox[1]),
                    float(orig_bbox[2]),
                    float(orig_bbox[3]),
                )
                # Expand rect slightly for full coverage (kerning/antialiasing)
                rect = rect + (-1, -1, 1, 1)
                page.add_redact_annot(rect, fill=(1, 1, 1))

        # ── PASS 2: Apply all redactions (clean erasure, no white-patch artifact)
        for page_idx in range(doc.page_count):
            doc[page_idx].apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)

        # ── PASS 3: Insert replacement text at the correct positions ──────────
        for anno in modified:
            page_num = max(0, int(anno.get("page", 1)) - 1)
            if page_num >= doc.page_count:
                continue

            text = anno.get("text", "").strip()
            if not text:
                continue

            page = doc[page_num]
            pw = page.rect.width   # page width  in PDF points
            ph = page.rect.height  # page height in PDF points

            font_size = float(anno.get("fontSize", 12))
            font_name = _pick_font(anno.get("fontFamily", "helv"))
            color = _parse_color(anno.get("color", "#000000"))

            # Determine insertion point ─────────────────────────────────────
            # PyMuPDF: insert_text(point) places the TEXT BASELINE at point.y
            #
            # Prefer originalBbox for pixel-perfect placement:
            #   x0 = left edge of original text
            #   y1 = bottom of glyph box ≈ baseline in PyMuPDF (top-left, y-down)
            orig_bbox = anno.get("originalBbox")
            if orig_bbox and len(orig_bbox) == 4:
                ix = float(orig_bbox[0])
                iy = float(orig_bbox[3])  # y1 = bottom ≈ baseline in top-left coords
            else:
                # Fallback: compute from x/y percentages
                # x, y are % of page, measured from TOP-LEFT (same as PyMuPDF)
                # NO Y-FLIP needed — PyMuPDF y-axis = canvas y-axis
                ix = float(anno.get("x", 0)) / 100.0 * pw
                iy_top = float(anno.get("y", 0)) / 100.0 * ph
                iy = iy_top + font_size * 0.85  # approximate baseline offset

            # Clamp to page boundaries
            ix = max(2.0, min(pw - 4.0, ix))
            iy = max(font_size, min(ph - 2.0, iy))

            # Insert each line of text
            for line_idx, line in enumerate(text.split("\n")):
                sanitized = "".join(c for c in line if 32 <= ord(c) <= 126 or c in "\t")
                if not sanitized:
                    continue
                line_y = iy + line_idx * font_size * 1.25
                if line_y > ph - 2:
                    break
                try:
                    page.insert_text(
                        fitz.Point(ix, line_y),
                        sanitized,
                        fontname=font_name,
                        fontsize=font_size,
                        color=color,
                        render_mode=0,
                    )
                except Exception as draw_err:
                    print(f"[WARN] insert_text failed: {draw_err}")

        doc.save(out_path, garbage=4, deflate=True, clean=True)
        doc.close()

    except HTTPException:
        raise
    except Exception as e:
        cleanup(in_path, out_path)
        raise HTTPException(status_code=500, detail=f"PDF edit failed: {str(e)}")

    cleanup(in_path)
    return FileResponse(
        out_path,
        media_type="application/pdf",
        filename="edited.pdf",
    )


@router.post("/extract-text")
async def extract_text(
    file: UploadFile = File(...),
    page: int = Form(1),
):
    """
    Extract all text spans from a PDF page using PyMuPDF.
    Returns spans with exact bounding boxes in PyMuPDF coordinate space
    (top-left origin, y increases downward, units = PDF points).

    The frontend uses these coordinates to:
    - Display overlays at the correct visual positions
    - Pass bboxes back to /edit-pdf for accurate redaction
    """
    in_path = await save_upload(file, suffix=".pdf")
    try:
        doc = fitz.open(in_path)
        page_num = max(0, page - 1)
        if page_num >= doc.page_count:
            raise HTTPException(status_code=400, detail=f"Page {page} out of range")

        pg = doc[page_num]
        pw = pg.rect.width
        ph = pg.rect.height

        spans = []
        blocks = pg.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
        for block in blocks:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    txt = span.get("text", "")
                    if not txt.strip():
                        continue
                    bbox = span["bbox"]  # [x0, y0, x1, y1] in PyMuPDF space
                    origin = span.get("origin", [bbox[0], bbox[3]])
                    spans.append({
                        "text": txt,
                        "bbox": list(bbox),
                        "origin": list(origin),
                        "size": span.get("size", 12),
                        "font": span.get("font", "Helvetica"),
                        "color": span.get("color", 0),
                    })

        doc.close()
        return {"page": page, "width": pw, "height": ph, "spans": spans}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Text extraction failed: {str(e)}")
    finally:
        cleanup(in_path)
