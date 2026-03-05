"""
News Scraper — fetches latest news from RSS feeds + Google News.
Returns structured headline data for the AI rewriter.
"""

import asyncio
import re
from datetime import datetime
from typing import Dict, List, Optional

import aiohttp
import feedparser
from loguru import logger

from shared.config import settings
from shared.database import get_news_articles

# ── RSS Feed Sources per Category ─────────────────────────────

RSS_SOURCES: Dict[str, List[Dict]] = {
    "bola": [
        {"name": "CNN Sport", "url": "https://www.cnnindonesia.com/olahraga/rss"},
        {"name": "Detik Sport", "url": "https://rss.detik.com/index.php/sport"},
        {"name": "Kompas Bola", "url": "https://bola.kompas.com/rss"},
    ],
    "teknologi": [
        {"name": "CNN Tech", "url": "https://www.cnnindonesia.com/teknologi/rss"},
        {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml"},
        {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index"},
    ],
    "politik": [
        {"name": "BBC Indonesia", "url": "https://feeds.bbci.co.uk/indonesia/rss.xml"},
        {"name": "CNN Internasional", "url": "https://www.cnnindonesia.com/internasional/rss"},
        {"name": "CNN Nasional", "url": "https://www.cnnindonesia.com/nasional/rss"},
    ],
    "ekonomi": [
        {"name": "CNBC Indonesia", "url": "https://www.cnbcindonesia.com/rss"},
        {"name": "CNN Ekonomi", "url": "https://www.cnnindonesia.com/ekonomi/rss"},
        {"name": "Detik Finance", "url": "https://rss.detik.com/index.php/finance"},
    ],
    "rekomendasi": [
        {"name": "GSMArena", "url": "https://www.gsmarena.com/rss-news-reviews.php3"},
    ],
}

# Google News search queries per category
GOOGLE_NEWS_QUERIES: Dict[str, List[str]] = {
    "bola": [
        "sepak bola hari ini",
        "liga 1 indonesia terbaru",
        "transfer pemain bola",
        "liga champions terbaru",
        "timnas indonesia",
    ],
    "teknologi": [
        "teknologi terbaru 2026",
        "gadget baru rilis",
        "update smartphone terbaru",
        "AI artificial intelligence terbaru",
        "aplikasi baru populer",
    ],
    "politik": [
        "berita politik dunia hari ini",
        "konflik internasional terbaru",
        "geopolitik dunia",
        "perang terbaru 2026",
        "hubungan internasional",
    ],
    "ekonomi": [
        "ekonomi indonesia terbaru",
        "bisnis startup indonesia",
        "saham kripto hari ini",
        "inflasi ekonomi global",
        "peluang bisnis 2026",
    ],
    "rekomendasi": [
        "HP terbaik 2026",
        "smartwatch terbaik murah",
        "laptop terbaik mahasiswa",
        "earbuds TWS terbaik",
        "gadget murah berkualitas",
    ],
}

# Track used headlines to avoid duplicates (DB-based, survives Render restarts)


async def get_existing_titles() -> set:
    """Get title prefixes of existing articles from DB to avoid duplicates."""
    try:
        articles = await get_news_articles(limit=200)
        return {a["title"][:40].lower().strip() for a in articles}
    except Exception:
        return set()


def _title_key(title: str) -> str:
    """Normalize title for comparison."""
    return title[:40].lower().strip()


# ── RSS Feed Parser ───────────────────────────────────────────

async def fetch_rss_feed(url: str, source_name: str = "") -> List[Dict]:
    """Fetch and parse a single RSS feed. Returns list of headline dicts."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status != 200:
                    logger.warning(f"RSS {source_name} returned {resp.status}")
                    return []
                text = await resp.text()

        feed = feedparser.parse(text)
        results = []

        for entry in feed.entries[:10]:  # max 10 per feed
            title = entry.get("title", "").strip()
            summary = entry.get("summary", entry.get("description", "")).strip()
            link = entry.get("link", "")
            published = entry.get("published", entry.get("updated", ""))

            if not title:
                continue

            # Clean HTML from summary
            summary = re.sub(r"<[^>]+>", "", summary)
            summary = summary[:500]  # limit length

            results.append({
                "title": title,
                "summary": summary,
                "source_url": link,
                "source_name": source_name,
                "published": published,
            })

        return results

    except Exception as e:
        logger.warning(f"RSS fetch failed ({source_name}): {e}")
        return []


async def fetch_all_rss(category: str) -> List[Dict]:
    """Fetch all RSS feeds for a category in parallel."""
    sources = RSS_SOURCES.get(category, [])
    if not sources:
        return []

    tasks = [fetch_rss_feed(s["url"], s["name"]) for s in sources]
    results = await asyncio.gather(*tasks, return_exceptions=True)

    all_headlines = []
    for r in results:
        if isinstance(r, list):
            all_headlines.extend(r)

    logger.info(f"RSS [{category}]: fetched {len(all_headlines)} headlines from {len(sources)} sources")
    return all_headlines


# ── Google News Search ────────────────────────────────────────

async def search_google_news(query: str, num_results: int = 5) -> List[Dict]:
    """Search Google News RSS for a query."""
    url = "https://news.google.com/rss/search"
    params = {
        "q": query,
        "hl": "id",
        "gl": "ID",
        "ceid": "ID:id",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                url, params=params, timeout=aiohttp.ClientTimeout(total=15)
            ) as resp:
                if resp.status != 200:
                    return []
                text = await resp.text()

        feed = feedparser.parse(text)
        results = []

        for entry in feed.entries[:num_results]:
            title = entry.get("title", "").strip()
            # Google News titles often have " - Source" suffix
            source_name = ""
            if " - " in title:
                parts = title.rsplit(" - ", 1)
                title = parts[0].strip()
                source_name = parts[1].strip() if len(parts) > 1 else "Google News"

            summary = entry.get("summary", entry.get("description", "")).strip()
            summary = re.sub(r"<[^>]+>", "", summary)[:500]
            link = entry.get("link", "")

            if title:
                results.append({
                    "title": title,
                    "summary": summary,
                    "source_url": link,
                    "source_name": source_name or "Google News",
                    "published": entry.get("published", ""),
                })

        return results

    except Exception as e:
        logger.warning(f"Google News search failed for '{query}': {e}")
        return []


async def fetch_google_news(category: str) -> List[Dict]:
    """Fetch Google News for all queries in a category."""
    import random
    queries = GOOGLE_NEWS_QUERIES.get(category, [])
    if not queries:
        return []

    # Pick 2 random queries to avoid excessive requests
    selected = random.sample(queries, min(2, len(queries)))
    all_results = []

    for query in selected:
        results = await search_google_news(query, num_results=5)
        all_results.extend(results)
        await asyncio.sleep(1)  # rate limit

    logger.info(f"Google News [{category}]: fetched {len(all_results)} headlines")
    return all_results


# ── Combined: Get Trending Topics ─────────────────────────────

async def get_trending_topics(
    category: str,
    count: int = 3,
) -> List[Dict]:
    """
    Get the best trending topics for a category.
    Combines RSS + Google News, deduplicates, filters already-published topics.
    Returns top `count` fresh topics.
    """
    # Fetch from both sources in parallel
    rss_task = fetch_all_rss(category)
    google_task = fetch_google_news(category)
    existing_task = get_existing_titles()
    rss_results, google_results, existing_titles = await asyncio.gather(
        rss_task, google_task, existing_task
    )

    # Combine and deduplicate by title similarity
    all_headlines = rss_results + google_results
    seen_titles = set()
    unique = []

    for item in all_headlines:
        title_lower = item["title"].lower().strip()
        # Simple dedup: skip if first 30 chars match
        title_key = title_lower[:30]
        if title_key in seen_titles:
            continue
        seen_titles.add(title_key)

        # Skip headlines already published in DB
        if _title_key(item["title"]) in existing_titles:
            continue

        unique.append(item)

    # Shuffle to add variety, then return top `count`
    import random
    random.shuffle(unique)
    result = unique[:count]

    logger.info(
        f"Trending [{category}]: {len(all_headlines)} total → "
        f"{len(unique)} unique → returning {len(result)}"
    )
    return result
