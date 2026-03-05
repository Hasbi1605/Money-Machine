"""
CikalNews — AI-powered Indonesian News Portal.
FastAPI backend serving auto-generated news articles.
"""

import asyncio
import math
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Request, Query
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from loguru import logger

from shared.database import (
    init_db,
    get_news_articles,
    get_news_by_slug,
    get_news_count,
    get_related_news,
    get_trending_news,
    search_news,
)
from news_app.scheduler import scheduler_loop, run_news_pipeline

# ── App Setup ─────────────────────────────────────────────────

app = FastAPI(title="CikalNews", version="1.0.0")

NEWS_DIR = Path(__file__).parent
TEMPLATES_DIR = NEWS_DIR / "templates"
STATIC_DIR = NEWS_DIR / "static"

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")


@app.on_event("startup")
async def startup():
    await init_db()
    # Start background scheduler
    asyncio.create_task(scheduler_loop())


# ── Category Config ───────────────────────────────────────────

CATEGORIES = {
    "bola": {"label": "Bola", "icon": "⚽", "color": "#27ae60"},
    "teknologi": {"label": "Teknologi", "icon": "💻", "color": "#2980b9"},
    "politik": {"label": "Politik Dunia", "icon": "🌍", "color": "#8e44ad"},
    "ekonomi": {"label": "Ekonomi & Bisnis", "icon": "📊", "color": "#e67e22"},
    "rekomendasi": {"label": "Rekomendasi", "icon": "⭐", "color": "#e74c3c"},
}

ARTICLES_PER_PAGE = 12


def format_date(dt_str: str) -> str:
    """Format ISO date string to Indonesian-friendly format."""
    if not dt_str:
        return ""
    try:
        dt = datetime.fromisoformat(dt_str)
        months = [
            "", "Januari", "Februari", "Maret", "April", "Mei", "Juni",
            "Juli", "Agustus", "September", "Oktober", "November", "Desember",
        ]
        return f"{dt.day} {months[dt.month]} {dt.year}, {dt.strftime('%H:%M')} WIB"
    except Exception:
        return dt_str


def time_ago(dt_str: str) -> str:
    """Convert ISO date string to '... yang lalu' format."""
    if not dt_str:
        return ""
    try:
        dt = datetime.fromisoformat(dt_str)
        now = datetime.utcnow()
        diff = now - dt
        seconds = int(diff.total_seconds())

        if seconds < 60:
            return "Baru saja"
        elif seconds < 3600:
            return f"{seconds // 60} menit yang lalu"
        elif seconds < 86400:
            return f"{seconds // 3600} jam yang lalu"
        elif seconds < 604800:
            return f"{seconds // 86400} hari yang lalu"
        else:
            return format_date(dt_str)
    except Exception:
        return dt_str


# Register template globals
templates.env.globals["categories"] = CATEGORIES
templates.env.globals["format_date"] = format_date
templates.env.globals["time_ago"] = time_ago
templates.env.globals["now"] = datetime.utcnow


# ── Routes ────────────────────────────────────────────────────


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    """Homepage with hero article + latest per category."""

    # Hero: latest overall article
    latest = await get_news_articles(limit=1)
    hero = latest[0] if latest else None

    # Latest per category (5 each)
    category_articles = {}
    for cat_key in CATEGORIES:
        articles = await get_news_articles(category=cat_key, limit=5)
        if articles:
            category_articles[cat_key] = articles

    # Trending sidebar
    trending = await get_trending_news(limit=8)

    return templates.TemplateResponse("home.html", {
        "request": request,
        "hero": hero,
        "category_articles": category_articles,
        "trending": trending,
        "page_title": "CikalNews — Portal Berita AI Indonesia",
    })


@app.get("/kategori/{category}", response_class=HTMLResponse)
async def category_page(
    request: Request,
    category: str,
    page: int = Query(1, ge=1),
):
    """Category listing with pagination."""
    if category not in CATEGORIES:
        return RedirectResponse("/")

    total = await get_news_count(category=category)
    total_pages = max(1, math.ceil(total / ARTICLES_PER_PAGE))
    page = min(page, total_pages)
    offset = (page - 1) * ARTICLES_PER_PAGE

    articles = await get_news_articles(
        category=category,
        limit=ARTICLES_PER_PAGE,
        offset=offset,
    )

    trending = await get_trending_news(limit=8)

    cat_info = CATEGORIES[category]

    return templates.TemplateResponse("category.html", {
        "request": request,
        "category": category,
        "cat_info": cat_info,
        "articles": articles,
        "trending": trending,
        "page": page,
        "total_pages": total_pages,
        "total": total,
        "page_title": f"{cat_info['label']} — CikalNews",
    })


@app.get("/artikel/{slug}", response_class=HTMLResponse)
async def article_page(request: Request, slug: str):
    """Individual article detail page."""
    article = await get_news_by_slug(slug)

    if not article:
        return templates.TemplateResponse("404.html", {
            "request": request,
            "page_title": "Artikel Tidak Ditemukan — CikalNews",
        }, status_code=404)

    # Related articles
    related = await get_related_news(
        category=article["category"],
        exclude_slug=slug,
        limit=4,
    )

    # Trending for sidebar
    trending = await get_trending_news(limit=8)

    # Parse tags
    tags = []
    if article.get("tags"):
        tags = [t.strip() for t in article["tags"].split(",") if t.strip()]

    cat_info = CATEGORIES.get(article["category"], {})

    return templates.TemplateResponse("article.html", {
        "request": request,
        "article": article,
        "tags": tags,
        "related": related,
        "trending": trending,
        "cat_info": cat_info,
        "page_title": f"{article['title']} — CikalNews",
    })


@app.get("/cari", response_class=HTMLResponse)
async def search_page(
    request: Request,
    q: str = Query("", min_length=0),
    page: int = Query(1, ge=1),
):
    """Search articles."""
    articles = []
    total = 0

    if q:
        articles = await search_news(q, limit=20)
        total = len(articles)

    return templates.TemplateResponse("search.html", {
        "request": request,
        "query": q,
        "articles": articles,
        "total": total,
        "page_title": f"Cari: {q} — CikalNews" if q else "Cari Artikel — CikalNews",
    })


@app.get("/health")
async def health():
    """Health check for Render."""
    return {"status": "ok", "service": "CikalNews", "timestamp": datetime.utcnow().isoformat()}


@app.post("/api/generate")
async def trigger_generate(
    category: str = Query("", description="Category to generate (empty = all)"),
    count: int = Query(2, ge=1, le=5),
):
    """Manual trigger to generate articles (for testing)."""
    categories = [category] if category else None
    asyncio.create_task(run_news_pipeline(categories=categories, articles_per_cat=count))
    return JSONResponse({"status": "started", "categories": categories or "all", "count": count})
