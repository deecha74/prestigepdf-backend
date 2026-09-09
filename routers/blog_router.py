"""
blog_router.py — FastAPI Router for PrestigePDF Blog System

Exposes REST API endpoints to fetch, query, and generate blog posts.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from pydantic import BaseModel
from typing import Dict, Any, List, Optional
from database import get_all_blogs, get_blog_by_slug, export_to_json
from blog_generator import generate_and_publish_post

router = APIRouter(prefix="/api/blogs", tags=["Blog Posts"])


# ─── Request body models ───────────────────────────────────────────────────────
class GeminiGenerateRequest(BaseModel):
    topic: Optional[str] = None          # leave empty to auto-pick topic
    word_count: Optional[int] = 1300     # target word count (800-2500)


class SchedulerToggleRequest(BaseModel):
    enabled: Optional[bool] = None


# ─── GET endpoints ─────────────────────────────────────────────────────────────

@router.get("", response_model=List[Dict[str, Any]])
async def list_blogs():
    """Fetch all blog posts from SQLite database."""
    return get_all_blogs()


# ─── Automated Publishing Scheduler ───────────────────────────────────────────

@router.get("/scheduler/status")
async def get_scheduler_info():
    """
    Returns current publishing cadence, next due date, last published title,
    and automated publishing history.
    """
    from scheduler import get_scheduler_status
    return get_scheduler_status()


@router.post("/scheduler/toggle")
async def toggle_scheduler_endpoint(body: Optional[SchedulerToggleRequest] = None):
    """
    Enable or disable the automated alternating-day blog publishing schedule (~every 48h, 3-4 posts/week).
    """
    from scheduler import toggle_scheduler
    enabled_val = body.enabled if body else None
    return toggle_scheduler(enabled=enabled_val)


@router.post("/scheduler/run-now")
async def run_scheduler_now(
    background: bool = Query(
        default=True,
        description="If true (default), runs in background. If false, waits and returns result.",
    ),
    background_tasks: BackgroundTasks = None,
):
    """
    Force an immediate automated blog generation cycle following the 5-pillar rotation.
    """
    from scheduler import run_autonomous_scheduled_post

    if background and background_tasks:
        background_tasks.add_task(run_autonomous_scheduled_post, force=True)
        return {
            "status": "ok",
            "message": "Immediate blog generation triggered in background.",
        }

    try:
        result = run_autonomous_scheduled_post(force=True)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{slug}", response_model=Dict[str, Any])
async def get_blog(slug: str):
    """Fetch a single blog post by slug."""
    post = get_blog_by_slug(slug)
    if not post:
        raise HTTPException(status_code=404, detail="Blog post not found.")
    return post



# ─── Template-based generator (original) ───────────────────────────────────────

@router.post("/generate")
async def generate_blog(background_tasks: BackgroundTasks):
    """Triggers generation of a new AdSense-compliant blog post (template-based) in background."""
    background_tasks.add_task(generate_and_publish_post)
    return {"status": "ok", "message": "Blog generation task started in background."}


# ─── Gemini AI generator (new) ────────────────────────────────────────────────

@router.post("/generate-gemini")
async def generate_blog_gemini(
    body: GeminiGenerateRequest,
    background: bool = Query(
        default=False,
        description="If true, runs in background and returns immediately. "
                    "If false (default), waits and returns the full generated post.",
    ),
    background_tasks: BackgroundTasks = None,
):
    """
    Generate a new AdSense-quality blog post using Gemini 1.5 Pro AI.

    - **topic**: Optional custom topic. Leave blank to auto-select an unused topic.
    - **word_count**: Target article word count (default 1300, range 800-2500).
    - **background**: Set `?background=true` to fire-and-forget; default is synchronous.

    The API key is stored securely in the server's `.env` file — never exposed to the frontend.
    """
    from gemini_blog_generator import generate_and_publish_gemini_post

    word_count = max(800, min(2500, body.word_count or 1300))
    topic      = (body.topic or "").strip() or None

    if background and background_tasks:
        background_tasks.add_task(
            generate_and_publish_gemini_post, topic, word_count
        )
        return {
            "status": "ok",
            "message": "Gemini blog generation started in background.",
            "topic": topic or "auto-selected",
        }

    # Synchronous — wait and return the post
    try:
        post = generate_and_publish_gemini_post(topic, word_count)
        return {
            "status": "ok",
            "message": "Blog post generated and published successfully.",
            "post": post,
        }
    except RuntimeError as e:
        raise HTTPException(status_code=503, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))


@router.get("/generate-gemini/status")
async def gemini_status():
    """Check whether the Gemini API key is configured on the server."""
    import os
    from dotenv import load_dotenv
    from pathlib import Path
    load_dotenv(dotenv_path=Path(__file__).resolve().parent.parent / ".env")
    key = os.getenv("GEMINI_API_KEY", "")
    configured = bool(key) and not key.startswith("AIzaSyPLACEHOLDER")
    return {
        "configured": configured,
        "model": os.getenv("GEMINI_MODEL", "gemini-1.5-pro-latest"),
        "hint": "Set GEMINI_API_KEY in backend/.env" if not configured else "Ready",
    }


# ─── Sync / export ────────────────────────────────────────────────────────────

@router.post("/sync")
async def sync_json():
    """Manually triggers sync from SQLite database to BlogPost.json."""
    export_to_json()
    return {"status": "ok", "message": "SQLite database synced to BlogPost.json successfully."}
