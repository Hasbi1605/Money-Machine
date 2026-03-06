"""
CikalNews — AI-powered Indonesian News Portal.
FastAPI backend serving auto-generated news articles.
"""

import asyncio
import hashlib
import math
import re
import urllib.parse
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Optional

import aiohttp
from fastapi import FastAPI, Request, Query, Body
from fastapi.responses import HTMLResponse, RedirectResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from loguru import logger
from pydantic import BaseModel

from shared.database import (
    init_db,
    get_news_articles,
    get_news_by_slug,
    get_news_count,
    get_related_news,
    get_trending_news,
    search_news,
    save_subscriber,
    unsubscribe as db_unsubscribe,
    update_article_summary,
)
from shared.gemini_client import gemini
from shared.config import settings
from news_app.scheduler import scheduler_loop, run_news_pipeline
from news_app.telegram_bot import handle_update, set_webhook, send_message

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
    # Start self-ping keep-alive (prevents Render free tier sleep)
    asyncio.create_task(_keep_alive())
    # Register Telegram webhook if NEWS_SITE_URL is set
    site_url = settings.news.site_url
    if site_url:
        ok = await set_webhook(site_url)
        if ok:
            logger.info(f"Telegram webhook registered for {site_url}")
        else:
            logger.warning("Telegram webhook registration failed — bot commands won't work")
    else:
        logger.info("NEWS_SITE_URL not set — Telegram webhook not registered (use polling for local dev)")


# ── Category Config ───────────────────────────────────────────

CATEGORIES = {
    "bola": {"label": "Sepak Bola", "icon": "⚽", "color": "#27ae60"},
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
    """Homepage with redesigned layout: breaking, hero, hot, trending, daily, weekly."""

    # All recent articles
    all_recent = await get_news_articles(limit=30)

    # Hero: latest article
    hero = all_recent[0] if all_recent else None

    # Sub-heroes: next 3 articles
    sub_heroes = all_recent[1:4] if len(all_recent) > 1 else []

    # Hot News: articles from last 6 hours (recent ones after sub-heroes)
    hot_news = all_recent[4:12] if len(all_recent) > 4 else []

    # Daily News: all recent articles for infinite scroll effect
    daily_news = all_recent[4:20] if len(all_recent) > 4 else []

    # Trending: most viewed
    trending = await get_trending_news(limit=10)

    # Weekly picks: top viewed (simulates editor's pick)
    weekly_picks = await get_trending_news(limit=6)

    return templates.TemplateResponse("home.html", {
        "request": request,
        "hero": hero,
        "sub_heroes": sub_heroes,
        "hot_news": hot_news,
        "daily_news": daily_news,
        "trending": trending,
        "weekly_picks": weekly_picks,
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

    # Parse AI summary (stored as "|||" separated string)
    ai_summary = []
    if article.get("ai_summary"):
        ai_summary = [s.strip() for s in article["ai_summary"].split("|||") if s.strip()]

    # Generate infographic URL if prompt exists
    infographic_url = ""
    if article.get("infographic_prompt") and article["infographic_prompt"].strip():
        encoded_prompt = urllib.parse.quote(article["infographic_prompt"])
        infographic_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width=800&height=600&nologo=true"

    cat_info = CATEGORIES.get(article["category"], {})

    return templates.TemplateResponse("article.html", {
        "request": request,
        "article": article,
        "tags": tags,
        "related": related,
        "trending": trending,
        "cat_info": cat_info,
        "ai_summary": ai_summary,
        "infographic_url": infographic_url,
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


# ── Feature API Endpoints ─────────────────────────────────────


class ChatRequest(BaseModel):
    message: str


class SubscribeRequest(BaseModel):
    email: str
    topics: str = ""


class TranslateRequest(BaseModel):
    slug: str
    lang: str = "en"


# Translation cache: {"slug:lang": {"title": ..., "content": ..., "excerpt": ...}}
_translation_cache: dict = {}

# Chat rate limiting: {"ip": [timestamps]}
_chat_rate: dict = defaultdict(list)


@app.post("/api/chat")
async def api_chat(request: Request, body: ChatRequest):
    """AI News Chat — answer questions using recent articles as context."""
    client_ip = request.client.host
    now = datetime.utcnow()

    # Rate limit: 10 chats per hour per IP
    _chat_rate[client_ip] = [
        t for t in _chat_rate[client_ip]
        if (now - t).total_seconds() < 3600
    ]
    if len(_chat_rate[client_ip]) >= 10:
        return JSONResponse(
            {"error": "Rate limit: maksimal 10 pertanyaan per jam"},
            status_code=429,
        )
    _chat_rate[client_ip].append(now)

    try:
        # Get recent articles as context
        recent = await get_news_articles(limit=15)
        context_parts = []
        for art in recent:
            context_parts.append(
                f"[{art['category'].upper()}] {art['title']}\n"
                f"Ringkasan: {art.get('excerpt', '')}\n"
                f"Tanggal: {art.get('created_at', '')}\n"
            )
        context = "\n---\n".join(context_parts)

        system = (
            "Kamu adalah CikalBot, asisten berita AI dari portal CikalNews. "
            "Jawab pertanyaan pengguna berdasarkan konteks berita terbaru di bawah. "
            "Jawab dalam Bahasa Indonesia yang natural dan informatif. "
            "Jika pertanyaan tidak terkait berita, tetap jawab dengan ramah. "
            "Jangan membuat fakta — hanya gunakan informasi dari konteks."
        )

        prompt = f"""Konteks berita terbaru CikalNews:
{context}

Pertanyaan pengguna: {body.message}

Jawab dengan ringkas dan informatif (maks 200 kata):"""

        response = await gemini.generate(prompt, system_instruction=system)
        return JSONResponse({"response": response})

    except Exception as e:
        logger.error(f"Chat API error: {e}")
        return JSONResponse(
            {"error": "Maaf, CikalBot sedang sibuk. Coba lagi nanti."},
            status_code=500,
        )


@app.get("/api/summarize/{slug}")
async def api_summarize(slug: str):
    """Generate AI summary for an existing article (on-demand)."""
    article = await get_news_by_slug(slug)
    if not article:
        return JSONResponse({"error": "Article not found"}, status_code=404)

    # Return existing summary if available
    if article.get("ai_summary"):
        points = [s.strip() for s in article["ai_summary"].split("|||") if s.strip()]
        return JSONResponse({"summary": points})

    # Generate summary on the fly
    try:
        prompt = f"""Buat 3 poin ringkasan utama dari artikel berita berikut. Setiap poin maksimal 1 kalimat singkat.

Judul: {article['title']}
Konten: {article.get('excerpt', '')} {article.get('content', '')[:1500]}

Output format JSON:
{{"summary": ["Poin 1", "Poin 2", "Poin 3"]}}"""

        result = await gemini.generate_json(prompt)
        points = result.get("summary", []) if result else []

        # Save to DB for future use
        if points:
            await update_article_summary(slug, "|||".join(points))

        return JSONResponse({"summary": points})

    except Exception as e:
        logger.error(f"Summarize API error: {e}")
        return JSONResponse({"error": "Failed to generate summary"}, status_code=500)


@app.post("/api/translate")
async def api_translate(body: TranslateRequest):
    """Translate article content to another language."""
    cache_key = f"{body.slug}:{body.lang}"
    if cache_key in _translation_cache:
        return JSONResponse(_translation_cache[cache_key])

    article = await get_news_by_slug(body.slug)
    if not article:
        return JSONResponse({"error": "Article not found"}, status_code=404)

    lang_names = {"en": "English", "ms": "Malay", "zh": "Chinese", "ja": "Japanese"}
    target_lang = lang_names.get(body.lang, "English")

    try:
        prompt = f"""Translate the following Indonesian news article to {target_lang}.
Keep the HTML formatting intact. Translate naturally, not word-by-word.

Title: {article['title']}
Excerpt: {article.get('excerpt', '')}
Content: {article['content']}

Output format JSON:
{{{{
  "title": "Translated title",
  "excerpt": "Translated excerpt",
  "content": "Translated HTML content"
}}}}"""

        result = await gemini.generate_json(prompt)
        if result:
            _translation_cache[cache_key] = result
            return JSONResponse(result)
        return JSONResponse({"error": "Translation failed"}, status_code=500)

    except Exception as e:
        logger.error(f"Translate API error: {e}")
        return JSONResponse({"error": "Translation failed"}, status_code=500)


@app.post("/api/subscribe")
async def api_subscribe(body: SubscribeRequest):
    """Subscribe to newsletter."""
    if not body.email or "@" not in body.email:
        return JSONResponse({"error": "Email tidak valid"}, status_code=400)

    token = hashlib.md5(f"{body.email}{datetime.utcnow().isoformat()}".encode()).hexdigest()[:16]
    result = await save_subscriber(body.email, body.topics, token)

    if result:
        return JSONResponse({"status": "success", "message": "Berhasil berlangganan newsletter CikalNews!"})
    return JSONResponse({"error": "Gagal berlangganan"}, status_code=500)


@app.get("/api/unsubscribe")
async def api_unsubscribe(email: str = Query(...), token: str = Query("")):
    """Unsubscribe from newsletter."""
    await db_unsubscribe(email, token)
    return HTMLResponse(
        "<html><body style='font-family:sans-serif;text-align:center;padding:60px'>"
        "<h2>Berhasil Berhenti Berlangganan</h2>"
        "<p>Email Anda telah dihapus dari newsletter CikalNews.</p>"
        "<a href='/'>Kembali ke Beranda</a>"
        "</body></html>"
    )


@app.get("/api/infographic/{slug}")
async def api_infographic(slug: str):
    """Get infographic URL for an article."""
    article = await get_news_by_slug(slug)
    if not article:
        return JSONResponse({"error": "Article not found"}, status_code=404)

    prompt = article.get("infographic_prompt", "")
    if not prompt or not prompt.strip():
        return JSONResponse({"error": "No infographic available", "url": ""}, status_code=404)

    encoded = urllib.parse.quote(prompt)
    url = f"https://image.pollinations.ai/prompt/{encoded}?width=800&height=600&nologo=true"
    return JSONResponse({"url": url, "prompt": prompt})


# ── Telegram Webhook ──────────────────────────────────────────


@app.post("/api/telegram")
async def telegram_webhook(request: Request):
    """Receive Telegram bot updates via webhook."""
    try:
        data = await request.json()
        # Process in background so we respond fast to Telegram
        asyncio.create_task(handle_update(data))
        return JSONResponse({"ok": True})
    except Exception as e:
        logger.error(f"Telegram webhook error: {e}")
        return JSONResponse({"ok": False}, status_code=400)


# ── Keep-Alive (self-ping to prevent Render sleep) ──────────


async def _keep_alive():
    """Ping own /health every 10 min to prevent Render free tier from sleeping."""
    site_url = settings.news.site_url
    if not site_url:
        return
    url = f"{site_url.rstrip('/')}/health"
    logger.info(f"🟢 Keep-alive: pinging {url} every 10 min")
    await asyncio.sleep(30)
    while True:
        try:
            async with aiohttp.ClientSession() as s:
                async with s.get(url, timeout=aiohttp.ClientTimeout(total=10)) as r:
                    logger.debug(f"Keep-alive ping: {r.status}")
        except Exception:
            pass
        await asyncio.sleep(600)  # 10 minutes
