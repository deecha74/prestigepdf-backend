# PrestigePDF Backend

A robust **Python FastAPI** backend for PrestigePDF that handles all PDF processing requiring server-side power.

## Requirements

- **Python 3.9+** — [Download](https://python.org)
- **Poppler for Windows** *(optional, for PDF → Images high quality)*
  - Download from: https://github.com/oschwartz10612/poppler-windows/releases
  - Extract and add `poppler-xx/Library/bin` to your system PATH
- **LibreOffice** *(optional, for Word/Excel/PPT → PDF)*
  - Download from: https://www.libreoffice.org/download/
  - Ensure `soffice` is accessible from your PATH

## Quick Start

```bat
# Double-click or run in a terminal:
backend\start.bat
```

The script automatically:
1. Detects your Python installation
2. Creates a `.venv` virtual environment
3. Installs all Python packages from `requirements.txt`
4. Warns you about missing optional dependencies
5. Launches the FastAPI server on `http://127.0.0.1:8000`

## API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Server liveness check |
| GET | `/docs` | Interactive Swagger UI |
| POST | `/edit-pdf` | True stream-level PDF text editing (PyMuPDF) |
| POST | `/compress` | PDF compression (pikepdf + Ghostscript) |
| POST | `/pdf-to-word` | PDF → Word .docx (pdf2docx) |
| POST | `/pdf-to-excel` | PDF → Excel .xlsx (pdfplumber) |
| POST | `/pdf-to-ppt` | PDF → PowerPoint .pptx |
| POST | `/pdf-to-images` | PDF → ZIP of JPEG images |
| POST | `/word-to-pdf` | Word → PDF (LibreOffice) |
| POST | `/excel-to-pdf` | Excel → PDF (LibreOffice) |
| POST | `/ppt-to-pdf` | PowerPoint → PDF (LibreOffice) |
| POST | `/protect-pdf` | Add AES-256 password protection |
| POST | `/unlock-pdf` | Remove password protection |

## Edit PDF — How It Works

Uses **PyMuPDF stream-level editing** (iLovePDF style):
1. Adds a redaction annotation at the exact bounding box of the original text
2. Applies redactions — cleanly erases glyphs without touching surrounding artwork
3. Inserts replacement text at the same position

This eliminates visible white box patches that cut through table borders.

## Development

```bash
cd backend
.venv\Scripts\activate
uvicorn main:app --reload --port 8000
```

Visit `http://127.0.0.1:8000/docs` for the interactive API explorer.
