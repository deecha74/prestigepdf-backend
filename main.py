"""
main.py — PrestigePDF FastAPI Backend

Runs on http://127.0.0.1:8000

All endpoints return proper file downloads (FileResponse / StreamingResponse).
CORS is open for localhost development (ports 3000–3100).
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from routers import blog_router, compress, convert, edit, protect, session
from database import init_db, seed_db_from_json

app = FastAPI(
    title="PrestigePDF Backend",
    description="Robust PDF processing backend: edit, convert, compress, protect, blog automation.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

@app.on_event("startup")
def startup_db():
    init_db()
    seed_db_from_json()

# ─── CORS ───────────────────────────────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://localhost:3001",
        "http://localhost:3039",
        "http://127.0.0.1:3039",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://prestigepdf.com",
        "https://www.prestigepdf.com",
        "https://api.prestigepdf.com",
        "https://prestigepdf.pages.dev",
    ],
    allow_origin_regex=r"https?://.*",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Routers ─────────────────────────────────────────────────────────────────
app.include_router(edit.router, tags=["Edit PDF"])
app.include_router(compress.router, tags=["Compress"])
app.include_router(convert.router, tags=["Convert"])
app.include_router(protect.router, tags=["Protect / Unlock"])
app.include_router(session.router, tags=["PDF Session (Edit)"])
app.include_router(blog_router.router, tags=["Blog Management"])


# ─── Health ──────────────────────────────────────────────────────────────────
@app.get("/health", tags=["Health"])
async def health():
    """Liveness check — returns OK when the server is running."""
    return {"status": "ok", "service": "PrestigePDF Backend", "version": "1.0.0"}


@app.get("/", tags=["Health"])
async def root():
    return {
        "message": "PrestigePDF Backend is running.",
        "docs": "http://127.0.0.1:8000/docs",
        "health": "http://127.0.0.1:8000/health",
    }
