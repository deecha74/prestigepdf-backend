@echo off
SETLOCAL

echo ============================================================
echo   PrestigePDF Backend - Startup Script
echo ============================================================
echo.

REM ── Check Python ─────────────────────────────────────────────
where python >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Python not found. Install Python 3.9+ from https://python.org
    pause
    exit /b 1
)

FOR /F "tokens=*" %%i IN ('python --version') DO SET PY_VER=%%i
echo [OK] Found %PY_VER%

REM ── Move into backend directory ───────────────────────────────
cd /d "%~dp0"

REM ── Create venv if missing ────────────────────────────────────
IF NOT EXIST ".venv\Scripts\activate.bat" (
    echo.
    echo [SETUP] Creating virtual environment...
    python -m venv .venv
    IF %ERRORLEVEL% NEQ 0 (
        echo [ERROR] Failed to create virtual environment.
        pause
        exit /b 1
    )
    echo [OK] Virtual environment created.
)

REM ── Activate venv ────────────────────────────────────────────
call .venv\Scripts\activate.bat

REM ── Install / upgrade dependencies ───────────────────────────
echo.
echo [SETUP] Installing/updating Python packages...
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
IF %ERRORLEVEL% NEQ 0 (
    echo [ERROR] Package installation failed. Check requirements.txt.
    pause
    exit /b 1
)
echo [OK] All packages installed.

REM ── Optional: check Poppler for pdf-to-images ─────────────────
where pdftoppm >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo.
    echo [WARN] Poppler not found on PATH.
    echo        PDF to Images will use PyMuPDF fallback ^(lower quality^).
    echo        Install Poppler: https://github.com/oschwartz10612/poppler-windows/releases
    echo        Then add 'poppler-xx/Library/bin' to your system PATH.
)

REM ── Optional: check LibreOffice for Office conversions ────────
where soffice >nul 2>&1
IF %ERRORLEVEL% NEQ 0 (
    echo.
    echo [WARN] LibreOffice not found on PATH.
    echo        Word/Excel/PPT to PDF conversions will be unavailable.
    echo        Install LibreOffice: https://www.libreoffice.org/download/
)

REM ── Launch FastAPI server ────────────────────────────────────
echo.
echo ============================================================
echo   Starting PrestigePDF Backend on http://127.0.0.1:8005
echo   API Docs:  http://127.0.0.1:8005/docs
echo   Press Ctrl+C to stop the server.
echo ============================================================
echo.

uvicorn main:app --host 127.0.0.1 --port 8005 --reload

ENDLOCAL
