"""
main.py — PrestigePDF FastAPI Backend

Runs on http://127.0.0.1:8000

All endpoints return proper file downloads (FileResponse / StreamingResponse).
CORS is open for localhost development (ports 3000–3100).
"""

from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from routers import blog_router, compress, convert, edit, protect, session
from database import init_db, seed_db_from_json

BACKEND_DIR = Path(__file__).resolve().parent
BLOGIMAGE_DIR = BACKEND_DIR / "blogimage"
BLOGIMAGE_DIR.mkdir(parents=True, exist_ok=True)

app = FastAPI(
    title="PrestigePDF Backend",
    description="Robust PDF processing backend: edit, convert, compress, protect, blog automation.",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# Mount local server blogimage directory
app.mount("/blogimage", StaticFiles(directory=str(BLOGIMAGE_DIR)), name="blogimage")

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


# ─── Health & Dynamic Sitemap ──────────────────────────────────────────────────
@app.get("/health", tags=["Health"])
async def health():
    """Liveness check — returns OK when the server is running."""
    return {"status": "ok", "service": "PrestigePDF Backend", "version": "1.0.0"}


@app.get("/sitemap.xml", tags=["SEO"])
async def dynamic_sitemap():
    """Generates real-time sitemap XML directly from SQLite database."""
    from datetime import datetime
    from fastapi import Response
    from database import get_all_blogs

    blogs = get_all_blogs()
    today = datetime.now().strftime("%Y-%m-%d")

    core_urls = [
        ("https://www.prestigepdf.com/", "1.0", "daily"),
        ("https://www.prestigepdf.com/tools", "0.9", "weekly"),
        ("https://www.prestigepdf.com/blogs", "0.9", "daily"),
        ("https://www.prestigepdf.com/about-us", "0.6", "monthly"),
        ("https://www.prestigepdf.com/privacy", "0.5", "monthly"),
        ("https://www.prestigepdf.com/terms-of-service", "0.5", "monthly"),
        ("https://www.prestigepdf.com/tools/compress", "0.9", "weekly"),
        ("https://www.prestigepdf.com/tools/merge", "0.9", "weekly"),
        ("https://www.prestigepdf.com/tools/pdf-to-word", "0.9", "weekly"),
        ("https://www.prestigepdf.com/tools/split", "0.85", "weekly"),
        ("https://www.prestigepdf.com/tools/edit", "0.85", "weekly"),
        ("https://www.prestigepdf.com/tools/sign", "0.85", "weekly"),
        ("https://www.prestigepdf.com/tools/word-to-pdf", "0.85", "weekly"),
        ("https://www.prestigepdf.com/tools/pdf-to-jpg", "0.85", "weekly"),
        ("https://www.prestigepdf.com/tools/jpg-to-pdf", "0.85", "weekly"),
        ("https://www.prestigepdf.com/tools/pdf-to-excel", "0.85", "weekly"),
        ("https://www.prestigepdf.com/tools/excel-to-pdf", "0.85", "weekly"),
        ("https://www.prestigepdf.com/tools/pdf-to-ppt", "0.8", "weekly"),
        ("https://www.prestigepdf.com/tools/ppt-to-pdf", "0.8", "weekly"),
        ("https://www.prestigepdf.com/tools/rotate", "0.8", "weekly"),
        ("https://www.prestigepdf.com/tools/delete-pages", "0.8", "weekly"),
        ("https://www.prestigepdf.com/tools/watermark", "0.8", "weekly"),
        ("https://www.prestigepdf.com/tools/protect", "0.8", "weekly"),
        ("https://www.prestigepdf.com/tools/unlock", "0.8", "weekly"),
        ("https://www.prestigepdf.com/tools/reader", "0.75", "weekly"),
        ("https://www.prestigepdf.com/tools/number-pages", "0.75", "weekly"),
        ("https://www.prestigepdf.com/tools/crop", "0.75", "weekly"),
        ("https://www.prestigepdf.com/tools/flatten", "0.75", "weekly"),
    ]

    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">',
    ]

    for loc, priority, freq in core_urls:
        xml_lines.append(
            f"  <url>\n    <loc>{loc}</loc>\n    <lastmod>{today}</lastmod>\n    <changefreq>{freq}</changefreq>\n    <priority>{priority}</priority>\n  </url>"
        )

    seen_slugs = set()
    for b in blogs:
        slug = b.get("slug")
        if slug and slug not in seen_slugs:
            seen_slugs.add(slug)
            blog_url = f"https://www.prestigepdf.com/blogs/{slug}"
            xml_lines.append(
                f"  <url>\n    <loc>{blog_url}</loc>\n    <lastmod>{today}</lastmod>\n    <changefreq>weekly</changefreq>\n    <priority>0.8</priority>\n  </url>"
            )

    xml_lines.append("</urlset>")
    return Response(content="\n".join(xml_lines), media_type="application/xml")


@app.get("/", tags=["Health"])
async def root():
    return {
        "message": "PrestigePDF Backend is running.",
        "docs": "http://127.0.0.1:8000/docs",
        "health": "http://127.0.0.1:8000/health",
        "sitemap": "http://127.0.0.1:8000/sitemap.xml",
    }
