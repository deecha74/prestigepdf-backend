"""
gemini_blog_generator.py — Gemini AI-Powered AdSense Blog Generator

Uses Google Gemini 1.5 Pro (via REST API) to generate high-quality,
unique, AdSense-compliant blog posts and publish them to the DB + JSON.

API key is loaded from .env (GEMINI_API_KEY) — never hardcoded.

Usage:
    POST /api/blogs/generate-gemini          -> auto-picks a topic
    POST /api/blogs/generate-gemini?topic=.. -> custom topic string
"""

import datetime
import io
import json
import os
import re
import random
import urllib.request
import urllib.error
import urllib.parse
from pathlib import Path
from typing import Any, Dict, List, Optional
from difflib import SequenceMatcher
from PIL import Image

from dotenv import load_dotenv

# Load .env from the backend directory
load_dotenv(dotenv_path=Path(__file__).resolve().parent / ".env")

GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GEMINI_MODEL   = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")

# Authentic editorial authors
AUTHORS = [
    "Deepak Chalise",
    "Nisha Chapagain",
]

# ── Content Pillars (5 Editorial Categories for AdSense Diversity) ─────────────
CONTENT_PILLARS = [
    {
        "id": "troubleshooting",
        "category": "PDF Tips",
        "name": "Troubleshooting & Problem Solving",
        "description": "Fixing common PDF headaches like file bloat, corrupt fonts, blurry scans, printing issues.",
        "audience": "Users facing unexpected file errors, bloated files, or formatting glitches.",
        "seed_topics": [
            "Why your PDF is 50MB with only a few pages and how to shrink it",
            "Why your PDF is blurry when printed and how to fix it easily",
            "How to fix upside-down or sideways pages in a PDF on any device",
            "Why some PDFs won't let you copy text and how to unlock them",
            "How to repair an unreadable or damaged PDF file without buying software",
            "Why your converted PDF text looks jumbled and how to fix formatting",
        ],
    },
    {
        "id": "workflows",
        "category": "How-To Guides",
        "name": "Real-World Professional Workflows",
        "description": "Step-by-step document management for real estate, legal, academia, finance, and small businesses.",
        "audience": "Professionals, students, and businesses completing specific multi-step projects.",
        "seed_topics": [
            "How real estate agents organize and merge buyer disclosure packets",
            "How college students prepare thesis and dissertation PDFs for submission",
            "How accountants extract clean Excel tables from bank statement PDFs",
            "How freelancers create polished client proposals from multiple document types",
            "How teachers split textbook chapters into student-friendly PDF packets",
            "How legal assistants assemble exhibits and contract addendums into one file",
        ],
    },
    {
        "id": "security",
        "category": "Security",
        "name": "Document Security & Privacy",
        "description": "Protecting confidential files, safe sharing, and encryption standards.",
        "audience": "Users dealing with confidential data, contracts, and legal privacy.",
        "seed_topics": [
            "Password protecting a PDF: best security settings for contracts and bank slips",
            "The risks of free online converters and what happens to your private uploads",
            "How to sign contracts and documents online with a legally binding digital signature",
            "How to safely redact and remove sensitive confidential data from a PDF",
            "How to remove metadata and author information from a PDF before emailing",
            "Flattening a PDF form: what it means and how to do it before submitting",
        ],
    },
    {
        "id": "conversion",
        "category": "Conversion",
        "name": "Tech Standards & Format Comparisons",
        "description": "Explaining PDF/A, vector vs raster, DPI, and document formats.",
        "audience": "Users needing accurate document conversion without breaking formatting.",
        "seed_topics": [
            "PDF vs Word: when to send a PDF and when to share an editable document",
            "PDF/A vs Standard PDF: which format should you use for long-term archiving?",
            "Step-by-step guide to converting scanned PDFs into searchable text with OCR",
            "Vector vs raster PDFs: why some scanned documents cannot be searched or edited",
            "How to convert Excel spreadsheets into clean, printable PDF reports",
            "How to convert JPG and PNG photos into a single professional PDF portfolio",
        ],
    },
    {
        "id": "productivity",
        "category": "Productivity",
        "name": "Everyday Productivity & File Optimization",
        "description": "Speeding up document work, email limits, and paperless workflows.",
        "audience": "Busy people looking to save time on everyday document handling.",
        "seed_topics": [
            "How to compress large PDF files without losing quality for email attachments",
            "How to merge multiple PDFs into one neatly organized document for free",
            "How to split a massive PDF into separate chapters or individual pages",
            "How to add clean page numbers to PDF documents without Adobe Acrobat",
            "The fastest ways to crop PDF margins for e-readers and tablet viewing",
            "Essential free PDF productivity tools every college student needs in 2026",
            "How to convert PDF to Word while keeping fonts, tables, and layouts intact",
        ],
    },
]

# Flat list of seed topics for backward compatibility
DEFAULT_TOPICS = [t for p in CONTENT_PILLARS for t in p["seed_topics"]]


def slugify(text: str) -> str:
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    return re.sub(r"[-\s]+", "-", text).strip("-")[:70]


def is_title_too_similar(new_title: str, existing_titles: List[str], threshold: float = 0.68) -> Optional[str]:
    """
    Checks if new_title is too similar to any existing title on the site.
    Uses SequenceMatcher and word-overlap (Jaccard similarity).
    Returns the colliding title if similarity is high, otherwise None.
    """
    if not existing_titles or not new_title:
        return None

    new_clean = re.sub(r"[^\w\s]", "", new_title.lower()).strip()
    new_words = set(new_clean.split())

    for ext in existing_titles:
        ext_clean = re.sub(r"[^\w\s]", "", ext.lower()).strip()
        ext_words = set(ext_clean.split())

        # Character/sequence similarity ratio
        seq_ratio = SequenceMatcher(None, new_clean, ext_clean).ratio()

        # Word-level overlap (Jaccard)
        jaccard = len(new_words & ext_words) / len(new_words | ext_words) if new_words and ext_words else 0.0

        if seq_ratio >= threshold or jaccard >= 0.65:
            return ext

    return None


def _get_fresh_dynamic_topic(existing_titles: List[str], pillar_info: Optional[Dict[str, Any]] = None) -> str:
    """
    When seed topics have already been covered, asks Gemini to brainstorm
    a brand new, high-demand, AdSense-friendly topic for the specific pillar.
    """
    titles_list = "\n".join(f"- {t}" for t in existing_titles[:35])
    pillar_desc = (
        f"in the pillar '{pillar_info['name']}' ({pillar_info['description']})"
        if pillar_info else "about PDF tools and workflows"
    )

    prompt = f"""Suggest a single, high-traffic, AdSense-friendly blog topic {pillar_desc} for PrestigePDF (https://www.prestigepdf.com).
These topics ALREADY EXIST on the site and must NOT be repeated, duplicated, or closely mimicked:
{titles_list}

Return ONLY the single suggested topic as plain text. No quotes, no markdown, no punctuation at the end."""
    try:
        raw = _call_gemini_api(prompt).strip().strip('"').strip("'")
        first_line = raw.split("\n")[0].strip()
        return first_line if len(first_line) > 5 else "How to organize and manage PDF archives efficiently"
    except Exception:
        fallback_topics = [
            "How to redact legal PDF documents securely before sharing",
            "Best ways to manage and catalog large PDF eBook libraries",
            "How to create fillable PDF registration forms for free",
            "How to verify digital signatures and certificates on a PDF",
        ]
        return random.choice(fallback_topics)


def pick_autonomous_topic(
    existing_titles: List[str],
    existing_slugs: set,
    preferred_pillar_id: Optional[str] = None,
) -> tuple[str, Dict[str, Any]]:
    """
    Autonomously selects the next blog topic by balancing across the 5 content pillars:
      1. Identifies the least-covered pillar (or honors preferred_pillar_id).
      2. Finds an unused seed topic in that pillar.
      3. If all seed topics in that pillar are used, dynamically brainstorms with Gemini.
    Returns: (topic_string, pillar_dict)
    """
    pillar_counts = {p["id"]: 0 for p in CONTENT_PILLARS}
    for title in existing_titles:
        for p in CONTENT_PILLARS:
            if p["category"].lower() in title.lower() or any(w in title.lower() for w in p["id"].split("_")):
                pillar_counts[p["id"]] += 1

    if preferred_pillar_id and any(p["id"] == preferred_pillar_id for p in CONTENT_PILLARS):
        selected_pillar = next(p for p in CONTENT_PILLARS if p["id"] == preferred_pillar_id)
    else:
        min_count = min(pillar_counts.values())
        candidates = [p for p in CONTENT_PILLARS if pillar_counts[p["id"]] == min_count]
        selected_pillar = random.choice(candidates)

    print(f"[Pillar Engine] Selected Pillar: '{selected_pillar['name']}' (Category: {selected_pillar['category']})")

    unused_seeds = [
        t for t in selected_pillar["seed_topics"]
        if slugify(t) not in existing_slugs
        and not is_title_too_similar(t, existing_titles)
    ]

    if unused_seeds:
        chosen_topic = random.choice(unused_seeds)
        print(f"[Pillar Engine] Using seed topic from pillar: '{chosen_topic}'")
        return chosen_topic, selected_pillar

    print(f"[Pillar Engine] All seed topics for '{selected_pillar['name']}' used. Brainstorming dynamic topic with Gemini...")
    topic = _get_fresh_dynamic_topic(existing_titles, selected_pillar)
    return topic, selected_pillar


def _build_prompt(
    topic: str,
    word_count: int = 1150,
    existing_titles: Optional[List[str]] = None,
    pillar_info: Optional[Dict[str, Any]] = None,
) -> str:
    today = datetime.datetime.now().strftime("%B %d, %Y")
    slug = slugify(topic)
    category = pillar_info.get("category", "How-To Guides") if pillar_info else "How-To Guides"

    # If existing titles are provided, list them so AI strictly avoids repeating them
    existing_context = ""
    if existing_titles:
        sample_existing = "\n".join(f"  - {t}" for t in existing_titles[:25])
        existing_context = f"""
EXISTING ARTICLES CURRENTLY ON THE SITE (DO NOT DUPLICATE THESE TITLES OR ANGLES):
{sample_existing}
* CRITICAL: Your new article must offer a distinct angle, fresh hook, and completely unique title that does not collide or sound identical to any of the above.
"""

    pillar_context = ""
    if pillar_info:
        pillar_context = f"""
EDITORIAL PILLAR & INTENT:
- Content Pillar: {pillar_info['name']}
- Blog Category: {category}
- Audience Focus: {pillar_info.get('audience', 'General users')}
"""

    return f"""You are a seasoned document workflow specialist and practical tech writer creating an in-depth, genuinely helpful blog post for PrestigePDF (https://www.prestigepdf.com), a free online PDF tools platform.

Target Subject: "{topic}"
{pillar_context}{existing_context}
══════════════════════════════════════════════════════════════════════════
CORE EDITORIAL DIRECTIVE: 100% HUMAN WRITING STYLE & ZERO REPETITION
══════════════════════════════════════════════════════════════════════════

1. WRITE LIKE A THOUGHTFUL HUMAN EXPERT:
   - Cadence & Rhythm (Burstiness): Mix short, punchy statements (3–7 words) with longer, detailed explanations (15–25 words). Never write in uniform, robotic paragraph lengths.
   - Tone: Pragmatic, friendly, and authoritative. Write in the first and second person ("you", "we"), as if walking a colleague through a solution on their screen.
   - Real Scenarios & Context: Mention real-world limitations (e.g., "Outlook's 20MB attachment ceiling", "Gmail's 25MB limit", "300 DPI print quality vs 72 DPI screen display", "vector text vs rasterized images").
   - Troubleshooting & Gotchas: Include real pain points (e.g., what happens if a font isn't embedded, why compression can make charts blurry if done wrong, how mobile browsers handle downloads).

2. STRICTLY BANNED AI CLICHÉS (NEVER USE ANY OF THESE):
   - BANNED INTROS:
     * "In today's fast-paced digital world / landscape..."
     * "In an era where digital documents reign supreme..."
     * "Whether you're a student, a busy professional, or an entrepreneur..."
     * "Look no further..." or "You've come to the right place..."
   - BANNED FILLER BUZZWORDS:
     * "Delve into", "Dive deep", "Tapestry", "Testament", "Beacon", "Revolutionize", "Game changer", "Plethora", "Seamlessly elevate"
   - BANNED ROBOTIC TRANSITIONS:
     * "Moreover", "Furthermore", "In summary", "In conclusion, it is clear that", "Needless to say", "It is crucial to remember", "It is important to note"
   - BANNED PADDING:
     * NEVER repeat the same explanation across different headings using synonyms. Every section must deliver NEW, distinct information.

3. STRICT PUNCTUATION RULE — ABSOLUTELY NO EM-DASHES:
   - NEVER use em-dashes (—) or en-dashes (–) anywhere in the title, headings, excerpt, or body text.
   - Em-dashes immediately signal AI-generated content to human readers and editors.
   - Use standard commas, parentheses, colons, or simple hyphens (-) instead.

4. UNIQUE & COMPELLING HEADLINE (TITLE):
   - Create an engaging, high-CTR headline between 50 and 65 characters.
   - Avoid generic cookie-cutter titles. Use natural human formats:
     * Problem-solver: "Why Your PDF Won't Open (And 5 Quick Ways to Fix It)"
     * Practical tutorial: "The Step-by-Step Way to Redact Sensitive Info From a PDF"
     * Comparison: "PDF/A vs Standard PDF: Which Should You Use for Archiving?"
     * Pro tips: "How to Shrink Massive PDF Files Under 20MB for Email"
   - Make sure the title sounds hand-crafted, not machine-spun.

5. ADSENSE CONTENT & STRUCTURE SPECIFICATIONS:
   - Target Length: {word_count} words (strict minimum 900 words, maximum 1500 words). High substance, zero fluff.
   - Structure:
     * Begins immediately with <h1> containing your exact title.
     * 5 to 7 logical, informative <h2> sections that guide the reader from the core problem through step-by-step execution, practical tips, and edge-case handling.
     * Exactly one numbered list (<ol>) with 4 to 6 specific, actionable steps.
     * 1 or 2 bullet lists (<ul>) for checklists, pros/cons, or common mistakes to avoid.
     * One <h2> FAQ section with 3-4 realistic user questions answered concisely in <h3> and <p> pairs.
     * Concluding <h2> section named something natural like "Final Advice", "Summary Checklist", or "Wrapping Up" (NEVER name it "In Conclusion").
     * Naturally weave in 2 or 3 internal links to PrestigePDF tools using relative URLs:
       e.g., <a href="/tools/compress">PrestigePDF's compression tool</a>, <a href="/tools/merge">PrestigePDF PDF merger</a>, <a href="/tools/split">PrestigePDF split tool</a>, etc.

══════════════════════════════════════════════════════════════════════════
OUTPUT FORMAT (STRICT JSON ONLY)
══════════════════════════════════════════════════════════════════════════
Return ONLY a single valid JSON object. No markdown code blocks, no backticks, no text before or after. Just the raw JSON string:

{{
  "title": "Natural human SEO title without em-dashes (50-65 characters)",
  "slug": "{slug}",
  "excerpt": "A sharp, engaging 1-2 sentence hook under 160 characters describing the specific problem this guide solves.",
  "description": "FULL HTML content string. Escape all double quotes inside as \\\\\" (e.g. <a href=\\\"/tools/compress\\\">). Use valid semantic tags: <h1>, <h2>, <h3>, <p>, <ul>, <ol>, <li>, <strong>, <em>, <a>. No outer container div. Absolutely no em-dashes.",
  "metaDescription": "145-158 character meta description with target keyword and clear call to action.",
  "category": "{category}",
  "readTime": "7 min",
  "date": "{today}",
  "author": "{random.choice(AUTHORS)}",
  "keywords": "8-12 comma-separated long-tail search keywords",
  "is_featured": false
}}"""


def _call_gemini_api(prompt: str) -> str:
    """
    Calls the Gemini REST API and returns the text response.
    Raises RuntimeError on failure.
    """
    if not GEMINI_API_KEY or GEMINI_API_KEY.startswith("AIzaSyPLACEHOLDER"):
        raise RuntimeError(
            "GEMINI_API_KEY is not set. Add your real key to backend/.env"
        )

    key   = os.getenv("GEMINI_API_KEY", GEMINI_API_KEY)
    model = os.getenv("GEMINI_MODEL", GEMINI_MODEL)
    url   = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent?key={key}"
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "responseMimeType": "application/json",
            "temperature": 0.8,
            "topK": 40,
            "topP": 0.95,
            "maxOutputTokens": 8192,
        },
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=90) as response:
            data = json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="replace")
        raise RuntimeError(f"Gemini API HTTP {e.code}: {body[:300]}")
    except urllib.error.URLError as e:
        raise RuntimeError(f"Gemini API network error: {e.reason}")

    try:
        return data["candidates"][0]["content"]["parts"][0]["text"]
    except (KeyError, IndexError) as e:
        raise RuntimeError(f"Unexpected Gemini response structure: {e}\n{data}")


def sanitize_ai_text(text: str) -> str:
    """
    Cleans text to ensure:
      - 0 AI-tell punctuation like em-dashes (—) or en-dashes (–).
      - Converts literal escaped '\\n' and '\\r' strings into real newlines/spaces.
    """
    if not isinstance(text, str):
        return text

    # Convert literal string escape sequences like \r\n, \n, \r into real newlines
    text = text.replace(r"\r\n", "\n").replace(r"\n", "\n").replace(r"\r", "")

    # Replace em-dashes and en-dashes with comma or clean hyphen
    text = text.replace("—", ", ").replace("–", "-")
    # Clean up any clumsy spacing/punctuation produced by replacement
    text = re.sub(r",\s*,+", ",", text)
    text = re.sub(r",\s*\.", ".", text)
    text = re.sub(r",\s*:", ":", text)
    text = re.sub(r"[\t ]+", " ", text)
    return text.strip()


def _parse_gemini_json(raw: str, topic: str) -> Dict[str, Any]:
    """
    Extracts, auto-heals, and parses the JSON object from Gemini's response text.
    Handles unclosed JSON, raw newlines, and sanitizes away em-dashes.
    """
    text = raw.strip()

    # Strip markdown code fences
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
    text = re.sub(r"\s*```$", "", text)
    text = text.strip()

    # Find outermost JSON object
    start = text.find("{")
    if start == -1:
        raise ValueError(f"No JSON object found in Gemini response. Raw (first 500): {text[:500]}")

    end = text.rfind("}")
    if end == -1 or end <= start:
        # Response was cut off before closing brace — auto-heal
        print("[Gemini Generator] Warning: JSON response unclosed. Auto-healing...")
        if text.count('"') % 2 != 0:
            text += '"'
        text += '\n}'
        end = text.rfind("}")

    json_str = text[start : end + 1]

    try:
        post = json.loads(json_str, strict=False)
    except json.JSONDecodeError:
        # Fallback: fix unescaped double quotes or newlines inside description field
        json_str_fixed = re.sub(
            r'"description"\s*:\s*"(.*?)"(?=\s*,\s*"metaDescription")',
            lambda m: '"description": "' + m.group(1).replace("\n", "\\n").replace("\r", "") + '"',
            json_str,
            flags=re.DOTALL,
        )
        try:
            post = json.loads(json_str_fixed, strict=False)
        except json.JSONDecodeError as e:
            # Last-ditch regex extraction for essential fields
            title_m = re.search(r'"title"\s*:\s*"([^"]+)"', json_str)
            desc_m = re.search(r'"description"\s*:\s*"(.*?)(?:"\s*,\s*"metaDescription"|"$)', json_str, re.DOTALL)
            excerpt_m = re.search(r'"excerpt"\s*:\s*"([^"]+)"', json_str)
            meta_m = re.search(r'"metaDescription"\s*:\s*"([^"]+)"', json_str)
            if title_m and desc_m:
                desc_raw = desc_m.group(1).replace(r"\r\n", "\n").replace(r"\n", "\n").replace(r"\r", "")
                post = {
                    "title": title_m.group(1),
                    "slug": slugify(topic),
                    "excerpt": excerpt_m.group(1) if excerpt_m else title_m.group(1),
                    "description": desc_raw,
                    "metaDescription": meta_m.group(1) if meta_m else (excerpt_m.group(1) if excerpt_m else title_m.group(1)),
                    "category": "How-To Guides",
                    "readTime": "6 min",
                    "author": random.choice(AUTHORS),
                    "keywords": "pdf tools, free pdf online",
                    "is_featured": False
                }
            else:
                raise ValueError(f"JSON parse error: {e}\nRaw (first 800):\n{json_str[:800]}")

    # Sanitize all text fields to guarantee NO em-dashes (— or –) or literal \n exist
    for key in ("title", "excerpt", "description", "metaDescription", "keywords"):
        if key in post and isinstance(post[key], str):
            post[key] = sanitize_ai_text(post[key])

    # Clean description specifically so any leftover literal '\n' strings are real whitespace
    if "description" in post and isinstance(post["description"], str):
        post["description"] = (
            post["description"]
            .replace(r"\r\n", "\n")
            .replace(r"\n", "\n")
            .replace(r"\r", "")
        )

    # Ensure required fields
    if not post.get("slug"):
        post["slug"] = slugify(post.get("title", topic))
    else:
        post["slug"] = slugify(post["slug"])

    if "is_featured" not in post:
        post["is_featured"] = False

    return post


def generate_ai_cover_image(topic: str, slug: str) -> str:
    """
    Generates a high-quality AI cover illustration for the blog post using Flux (via Pollinations).
    Returns the direct CDN URL so the image loads everywhere (static frontend, private backend,
    social cards, and Google Image Search) without static hosting sync issues.
    Also saves a local backup in backend/blogimage/<slug>.jpg.
    """
    clean_topic = re.sub(r"[^\w\s]", " ", topic)
    image_prompt = (
        f"minimalist modern 3d render of {clean_topic}, clean tech desk workspace, "
        f"sleek digital documents and folders, soft vibrant studio lighting, isometric aesthetic, "
        f"8k resolution, graphic design art, absolutely no text, no words, no letters"
    )
    encoded = urllib.parse.quote(image_prompt)
    seed = random.randint(1000, 999999)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=1200&height=675&seed={seed}&nologo=true"

    print(f"[AI Image Generator] Generated unique AI cover URL for '{topic}':\n  -> {url}")

    # Save a local backup copy on the backend server
    try:
        backend_dir = Path(__file__).resolve().parent
        backend_img_dir = backend_dir / "blogimage"
        backend_img_dir.mkdir(parents=True, exist_ok=True)
        backend_file = backend_img_dir / f"{slug}.jpg"

        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=15) as response:
            data = response.read()

        img = Image.open(io.BytesIO(data)).convert("RGB")
        img.thumbnail((1200, 675), Image.Resampling.LANCZOS)
        img.save(backend_file, "JPEG", quality=85, optimize=True)
        print(f"[AI Image Generator] [OK] Saved local backup image: {backend_file}")
    except Exception as e:
        print(f"[AI Image Generator] Note: Local backup save skipped ({e}). CDN URL is active.")

    return url


def generate_gemini_post(
    topic: Optional[str] = None,
    word_count: int = 1150,
    pillar_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Generates a single AdSense-quality blog post using Gemini AI.

    Args:
        topic:      Custom topic string. If None, picks autonomously across the 5 content pillars.
        word_count: Target article word count (default 1150).
        pillar_id:  Optional specific pillar to target ('troubleshooting', 'workflows', 'security', 'conversion', 'productivity').

    Returns:
        Dict matching the BlogPost schema (title, slug, description, …)

    Raises:
        RuntimeError: if Gemini API call fails
        ValueError:   if response cannot be parsed
    """
    from database import get_all_blogs
    blogs = get_all_blogs()
    existing_slugs = {b["slug"] for b in blogs}
    existing_titles = [b["title"] for b in blogs if b.get("title")]

    pillar_info = None
    if not topic:
        topic, pillar_info = pick_autonomous_topic(
            existing_titles=existing_titles,
            existing_slugs=existing_slugs,
            preferred_pillar_id=pillar_id,
        )
        print(f"[Gemini Generator] Autonomous topic: '{topic}' (Pillar: {pillar_info['name']})")
    else:
        print(f"[Gemini Generator] Custom topic requested: '{topic}'")

    prompt   = _build_prompt(topic, word_count, existing_titles=existing_titles, pillar_info=pillar_info)
    raw_text = _call_gemini_api(prompt)
    post     = _parse_gemini_json(raw_text, topic)

    if pillar_info and not post.get("category"):
        post["category"] = pillar_info["category"]

    # Check generated title for similarity against existing titles
    similar_match = is_title_too_similar(post.get("title", topic), existing_titles)
    if similar_match:
        print(f"[Gemini Generator] Notice: Title '{post['title']}' was similar to '{similar_match}'. Differentiating angle...")
        post["title"] = f"{post['title']}: Practical Guide"

    # Ensure slug uniqueness against all existing database slugs
    base_slug = post.get("slug") or slugify(post.get("title", topic))
    final_slug = base_slug
    counter = 2
    while final_slug in existing_slugs:
        final_slug = f"{base_slug}-{counter}"
        counter += 1
    post["slug"] = final_slug

    print(f"[Gemini Generator] [OK] Generated unique post: '{post.get('title', topic)}' (slug: {post['slug']}, category: {post.get('category')})")
    return post


def generate_and_publish_gemini_post(
    topic: Optional[str] = None,
    word_count: int = 1150,
    pillar_id: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Full pipeline:
      1. Generate article with Gemini AI (human-written, no em-dashes, pillar-driven)
      2. Generate unique AI cover illustration
      3. Insert into SQLite database
      4. Export to BlogPost.json
      5. Update sitemap.xml + ping search engines

    Returns the published post dict with the assigned DB id.
    Raises RuntimeError / ValueError on failure.
    """
    from database import insert_blog_post, get_all_blogs
    from blog_generator import update_sitemap_xml, slugify as _slugify

    post = generate_gemini_post(topic, word_count, pillar_id=pillar_id)

    # Generate unique AI cover image
    image_path = generate_ai_cover_image(
        post.get("title", topic or "PDF Tools Guide"), post["slug"]
    )
    post["image"] = image_path

    # Persist to DB + JSON
    post_id = insert_blog_post(post)
    if not post_id:
        raise RuntimeError(
            f"DB insert failed — post with slug '{post['slug']}' may already exist."
        )

    post["id"] = post_id

    # Update sitemap & ping search engines
    update_sitemap_xml(post["slug"])

    print(
        f"\n{'='*60}\n"
        f"  [Gemini] Published #{post_id}: {post['title']}\n"
        f"  URL: https://www.prestigepdf.com/blogs/{post['slug']}\n"
        f"  Category: {post.get('category')}\n"
        f"  Cover Image: {post['image']}\n"
        f"{'='*60}\n"
    )
    return post


# ── CLI quick-test ─────────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    custom_topic = " ".join(sys.argv[1:]) if len(sys.argv) > 1 else None
    try:
        result = generate_gemini_post(custom_topic)
        print("\n--- Generated Post Metadata ---")
        print(f"Title:  {result['title']}")
        print(f"Slug:   {result['slug']}")
        print(f"Words:  {len(result['description'].split())}")
        print(f"Meta:   {result['metaDescription']}")
        print("--- Description preview (first 300 chars) ---")
        print(result["description"][:300])
    except Exception as err:
        print(f"[ERROR] {err}")
        sys.exit(1)
