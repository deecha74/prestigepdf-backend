"""
blog_router.py — FastAPI Router for PrestigePDF Blog System

Exposes REST API endpoints to fetch, query, and generate blog posts.
"""

from fastapi import APIRouter, HTTPException, BackgroundTasks, Query
from typing import Dict, Any, List, Optional
from database import get_all_blogs, get_blog_by_slug, export_to_json
from blog_generator import generate_and_publish_post

router = APIRouter(prefix="/api/blogs", tags=["Blog Posts"])


@router.get("", response_model=List[Dict[str, Any]])
async def list_blogs():
    """Fetch all blog posts from SQLite database."""
    return get_all_blogs()


@router.get("/{slug}", response_model=Dict[str, Any])
async def get_blog(slug: str):
    """Fetch a single blog post by slug."""
    post = get_blog_by_slug(slug)
    if not post:
        raise HTTPException(status_code=404, detail="Blog post not found.")
    return post


@router.post("/generate")
async def generate_blog(background_tasks: BackgroundTasks):
    """Triggers generation of a new AdSense-compliant blog post in background."""
    background_tasks.add_task(generate_and_publish_post)
    return {"status": "ok", "message": "Blog generation task started in background."}


@router.post("/sync")
async def sync_json():
    """Manually triggers sync from SQLite database to BlogPost.json."""
    export_to_json()
    return {"status": "ok", "message": "SQLite database synced to BlogPost.json successfully."}
