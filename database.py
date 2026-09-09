"""
database.py — SQLite Database Layer & JSON Exporter for PrestigePDF Blog System

Handles creation and management of backend/blogs.db SQLite database,
blog post persistence, queries, and automatic sync to src/data/BlogPost.json.
"""

import json
import os
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# Paths
BACKEND_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BACKEND_DIR.parent
DB_PATH = BACKEND_DIR / "blogs.db"
BLOG_JSON_PATH = PROJECT_ROOT / "tools-menu-magic-main" / "src" / "data" / "BlogPost.json"


def get_connection() -> sqlite3.Connection:
    """Returns a SQLite connection with dict-like row factory."""
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """Initialize the blogs table in SQLite database."""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS blogs (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            slug TEXT UNIQUE NOT NULL,
            excerpt TEXT NOT NULL,
            description TEXT NOT NULL,
            meta_description TEXT NOT NULL,
            category TEXT NOT NULL,
            read_time TEXT NOT NULL,
            date TEXT NOT NULL,
            image TEXT NOT NULL,
            author TEXT NOT NULL,
            keywords TEXT NOT NULL,
            is_featured INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()
    print(f"[SQLite] Database initialized at {DB_PATH}")


def clean_database_descriptions():
    """
    Cleans any existing blog post descriptions in SQLite that contain literal '\\n' escape strings.
    """
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT id, description FROM blogs")
        rows = cursor.fetchall()
        for row in rows:
            desc = row["description"]
            if desc and (r"\n" in desc or r"\r" in desc):
                cleaned_desc = desc.replace(r"\r\n", "\n").replace(r"\n", "\n").replace(r"\r", "")
                cursor.execute("UPDATE blogs SET description = ? WHERE id = ?", (cleaned_desc, row["id"]))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[SQLite] Warning cleaning descriptions: {e}")


def insert_blog_post(post: Dict[str, Any]) -> Optional[int]:
    """
    Inserts a new blog post into SQLite DB and triggers JSON export.
    Returns post ID on success, or None if slug already exists or on error.
    """
    conn = get_connection()
    cursor = conn.cursor()

    try:
        desc = post["description"]
        if isinstance(desc, str):
            desc = desc.replace(r"\r\n", "\n").replace(r"\n", "\n").replace(r"\r", "")

        cursor.execute(
            """
            INSERT INTO blogs (
                title, slug, excerpt, description, meta_description,
                category, read_time, date, image, author, keywords, is_featured
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                post["title"],
                post["slug"],
                post["excerpt"],
                desc,
                post.get("metaDescription", post.get("meta_description", "")),
                post.get("category", "PDF Guides"),
                post.get("readTime", post.get("read_time", "6 min")),
                post.get("date", datetime.now().strftime("%B %d, %Y")),
                post["image"],
                post.get("author", "PrestigePDF Editorial Team"),
                post.get("keywords", "pdf tools, edit pdf, merge pdf"),
                1 if post.get("is_featured") else 0,
            ),
        )

        conn.commit()
        post_id = cursor.lastrowid
        conn.close()

        # Sync database to BlogPost.json for frontend
        export_to_json()
        return post_id

    except sqlite3.IntegrityError:
        print(f"[SQLite] Blog post with slug '{post['slug']}' already exists.")
        conn.close()
        return None
    except Exception as e:
        print(f"[SQLite Error] Failed to insert post: {e}")
        conn.close()
        return None


def get_all_blogs() -> List[Dict[str, Any]]:
    """Fetch all blog posts from SQLite ordered by creation date desc."""
    init_db()
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM blogs ORDER BY id DESC")
    rows = cursor.fetchall()
    conn.close()

    posts = []
    for row in rows:
        desc = row["description"] or ""
        if r"\n" in desc or r"\r" in desc:
            desc = desc.replace(r"\r\n", "\n").replace(r"\n", "\n").replace(r"\r", "")
        posts.append({
            "id": row["id"],
            "title": row["title"],
            "slug": row["slug"],
            "excerpt": row["excerpt"],
            "description": desc,
            "metaDescription": row["meta_description"],
            "category": row["category"],
            "readTime": row["read_time"],
            "date": row["date"],
            "image": row["image"],
            "author": row["author"],
            "keywords": row["keywords"],
            "is_featured": bool(row["is_featured"]),
        })

    return posts


def get_blog_by_slug(slug: str) -> Optional[Dict[str, Any]]:
    """Fetch a single blog post by slug."""
    init_db()
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM blogs WHERE slug = ?", (slug,))
    row = cursor.fetchone()
    conn.close()

    if not row:
        return None

    desc = row["description"] or ""
    if r"\n" in desc or r"\r" in desc:
        desc = desc.replace(r"\r\n", "\n").replace(r"\n", "\n").replace(r"\r", "")

    return {
        "id": row["id"],
        "title": row["title"],
        "slug": row["slug"],
        "excerpt": row["excerpt"],
        "description": desc,
        "metaDescription": row["meta_description"],
        "category": row["category"],
        "readTime": row["read_time"],
        "date": row["date"],
        "image": row["image"],
        "author": row["author"],
        "keywords": row["keywords"],
        "is_featured": bool(row["is_featured"]),
    }


def fix_broken_image_urls():
    """
    Ensures posts have a valid image. Only fills empty or null image entries,
    never overwrites AI-generated Flux images or existing valid URLs.
    """
    conn = get_connection()
    cursor = conn.cursor()

    default_cdn = "https://images.unsplash.com/photo-1563986768609-322da13575f3?auto=format&fit=crop&w=1200&q=80"
    cursor.execute("SELECT id, image FROM blogs WHERE image IS NULL OR image = ''")
    rows = cursor.fetchall()

    for row in rows:
        cursor.execute("UPDATE blogs SET image = ? WHERE id = ?", (default_cdn, row["id"]))

    conn.commit()
    conn.close()


def export_to_json():
    """
    Reads all blog posts from SQLite and updates src/data/BlogPost.json.
    Also preserves existing static posts from BlogPost.json if DB is newly created.
    """
    init_db()
    fix_broken_image_urls()
    clean_database_descriptions()

    # Load existing JSON data to preserve existing posts if any
    existing_featured = None
    existing_posts = []

    if BLOG_JSON_PATH.exists():
        try:
            with open(BLOG_JSON_PATH, "r", encoding="utf-8") as f:
                data = json.load(f)
                existing_featured = data.get("featured")
                existing_posts = data.get("posts", [])
        except Exception:
            pass

    # Read posts from DB
    db_posts = get_all_blogs()

    if db_posts:
        # Build merged posts list, avoiding duplicate slugs
        seen_slugs = set()
        final_posts = []

        for p in db_posts:
            if p["slug"] not in seen_slugs:
                seen_slugs.add(p["slug"])
                final_posts.append(p)

        for p in existing_posts:
            if p["slug"] not in seen_slugs:
                seen_slugs.add(p["slug"])
                final_posts.append(p)

        featured_post = existing_featured if existing_featured else final_posts[0]

        json_data = {
            "featured": featured_post,
            "posts": final_posts,
        }

        BLOG_JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
        with open(BLOG_JSON_PATH, "w", encoding="utf-8") as f:
            json.dump(json_data, f, indent=2, ensure_ascii=False)

        print(f"[JSON Sync] Updated {BLOG_JSON_PATH} with {len(final_posts)} posts.")


def seed_db_from_json():
    """Seeds SQLite DB with existing posts from BlogPost.json if DB is empty."""
    init_db()
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT COUNT(*) as count FROM blogs")
    count = cursor.fetchone()["count"]
    conn.close()

    if count > 0:
        return

    if not BLOG_JSON_PATH.exists():
        return

    print("[SQLite Seed] Importing initial posts from BlogPost.json into SQLite...")
    try:
        with open(BLOG_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)

        posts_to_seed = []
        if data.get("featured"):
            f_post = data["featured"]
            f_post["is_featured"] = True
            posts_to_seed.append(f_post)

        for p in data.get("posts", []):
            posts_to_seed.append(p)

        for p in posts_to_seed:
            insert_blog_post(p)

        print("[SQLite Seed] Complete.")
    except Exception as e:
        print(f"[SQLite Seed Error]: {e}")


if __name__ == "__main__":
    init_db()
    seed_db_from_json()
