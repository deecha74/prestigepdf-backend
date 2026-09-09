"""
scheduler.py — Automated Blog Publishing Scheduler for PrestigePDF

Publishes 3-4 posts per week on an alternating-day cadence (~every 48 hours).
Rotates across the 5 Content Pillars to guarantee diverse, non-repetitive,
AdSense-compliant articles with custom AI-generated cover art.
"""

import asyncio
import datetime
import json
import os
from pathlib import Path
from typing import Any, Dict, Optional

from database import get_connection

BACKEND_DIR = Path(__file__).resolve().parent
STATE_FILE = BACKEND_DIR / "scheduler_state.json"

# Default configuration: Alternating days (48 hours)
DEFAULT_CADENCE_HOURS = 48


def _get_latest_db_post_time() -> Optional[datetime.datetime]:
    """Retrieves the creation timestamp of the latest blog post in SQLite."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT created_at FROM blogs ORDER BY id DESC LIMIT 1")
        row = cursor.fetchone()
        conn.close()
        if row and row["created_at"]:
            # Format: 'YYYY-MM-DD HH:MM:SS'
            return datetime.datetime.strptime(row["created_at"], "%Y-%m-%d %H:%M:%S")
    except Exception as e:
        print(f"[Scheduler] Could not read latest DB post time: {e}")
    return None


def load_scheduler_state() -> Dict[str, Any]:
    """Loads current scheduler state from file or initializes from DB."""
    if STATE_FILE.exists():
        try:
            with open(STATE_FILE, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass

    # Initialize from DB state
    latest_db_time = _get_latest_db_post_time()
    last_run_str = latest_db_time.isoformat() if latest_db_time else None

    state = {
        "enabled": True,
        "cadence_hours": DEFAULT_CADENCE_HOURS,
        "last_run_at": last_run_str,
        "last_slug": None,
        "last_title": None,
        "last_pillar": None,
        "total_automated_posts": 0,
    }
    save_scheduler_state(state)
    return state


def save_scheduler_state(state: Dict[str, Any]) -> None:
    """Persists scheduler state to scheduler_state.json."""
    try:
        with open(STATE_FILE, "w", encoding="utf-8") as f:
            json.dump(state, f, indent=2)
    except Exception as e:
        print(f"[Scheduler] Failed to write state file: {e}")


def get_scheduler_status() -> Dict[str, Any]:
    """Returns human-readable scheduler status and time until next post."""
    state = load_scheduler_state()
    cadence_hours = state.get("cadence_hours", DEFAULT_CADENCE_HOURS)

    last_run_dt = None
    if state.get("last_run_at"):
        try:
            last_run_dt = datetime.datetime.fromisoformat(state["last_run_at"])
        except ValueError:
            pass

    # Fallback to DB latest post if state has no timestamp
    if not last_run_dt:
        last_run_dt = _get_latest_db_post_time()

    now = datetime.datetime.now()
    if last_run_dt:
        next_due_dt = last_run_dt + datetime.timedelta(hours=cadence_hours)
        seconds_remaining = max(0, (next_due_dt - now).total_seconds())
        hours_remaining = round(seconds_remaining / 3600, 1)
        next_scheduled_str = next_due_dt.strftime("%B %d, %Y at %I:%M %p")
    else:
        next_due_dt = now
        hours_remaining = 0.0
        next_scheduled_str = "Immediately (no previous posts recorded)"

    return {
        "enabled": state.get("enabled", True),
        "cadence": "Alternating days (~48 hours, 3-4 posts per week)",
        "cadence_hours": cadence_hours,
        "last_run_at": last_run_dt.strftime("%B %d, %Y at %I:%M %p") if last_run_dt else "Never",
        "last_title": state.get("last_title"),
        "last_slug": state.get("last_slug"),
        "next_scheduled_post": next_scheduled_str,
        "hours_until_next_post": hours_remaining,
        "is_due_now": hours_remaining <= 0,
        "total_automated_posts": state.get("total_automated_posts", 0),
    }


def toggle_scheduler(enabled: Optional[bool] = None) -> Dict[str, Any]:
    """Enables, disables, or flips the automated publishing schedule."""
    state = load_scheduler_state()
    if enabled is None:
        state["enabled"] = not state.get("enabled", True)
    else:
        state["enabled"] = bool(enabled)
    save_scheduler_state(state)
    print(f"[Scheduler] Automated publishing state set to: {state['enabled']}")
    return get_scheduler_status()


def run_autonomous_scheduled_post(force: bool = False) -> Dict[str, Any]:
    """
    Executes an autonomous post generation & publishing cycle:
      - Rotates through the 5 content pillars
      - Generates human-written, AdSense-grade content (0 em-dashes)
      - Generates custom AI cover illustration via Flux
      - Persists to DB, exports to JSON, updates sitemap, and pings search engines

    Returns published post dict on success, or status dict if skipped.
    """
    from gemini_blog_generator import generate_and_publish_gemini_post

    state = load_scheduler_state()

    # Check if due (unless forced manually)
    if not force:
        if not state.get("enabled", True):
            return {"status": "skipped", "reason": "Scheduler is disabled."}

        status = get_scheduler_status()
        if not status["is_due_now"]:
            return {
                "status": "skipped",
                "reason": f"Next post due in {status['hours_until_next_post']} hours ({status['next_scheduled_post']}).",
            }

    print("\n[AutoScheduler] 🚀 Starting automated alternating-day blog publishing cycle...")

    try:
        # None topic = fully autonomous pillar rotation
        post = generate_and_publish_gemini_post(topic=None)

        # Update state
        now_iso = datetime.datetime.now().isoformat()
        state["last_run_at"] = now_iso
        state["last_slug"] = post.get("slug")
        state["last_title"] = post.get("title")
        state["last_pillar"] = post.get("category")
        state["total_automated_posts"] = state.get("total_automated_posts", 0) + 1
        save_scheduler_state(state)

        print(
            f"[AutoScheduler] [OK] Successfully published scheduled post: "
            f"'{post['title']}' (#{post.get('id')})\n"
        )
        return {
            "status": "published",
            "post_id": post.get("id"),
            "title": post.get("title"),
            "slug": post.get("slug"),
            "category": post.get("category"),
            "image": post.get("image"),
        }

    except Exception as e:
        print(f"[AutoScheduler Error] Failed to publish scheduled post: {e}")
        raise


async def scheduler_background_loop():
    """
    Continuous background task running inside FastAPI.
    Checks every 30 minutes if an alternating-day post is due.
    """
    print("[AutoScheduler] Background loop active. Monitoring 48h publishing cadence...")
    # Initial sleep on startup to let server fully spin up
    await asyncio.sleep(10)

    while True:
        try:
            status = get_scheduler_status()
            if status["enabled"] and status["is_due_now"]:
                print("[AutoScheduler] Alternating-day post is due! Triggering autonomous generation...")
                # Run the synchronous generation in a background worker thread
                await asyncio.to_thread(run_autonomous_scheduled_post, force=False)
        except Exception as err:
            print(f"[AutoScheduler Loop Error] {err}")

        # Sleep 30 minutes before next check
        await asyncio.sleep(1800)
