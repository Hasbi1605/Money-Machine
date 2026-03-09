"""
News Scraper — fetches latest news from RSS feeds + Google News.
Returns structured headline data for the AI rewriter.
Enhanced: semantic dedup, expanded sources, soccer-only for bola.
"""

import asyncio
import re
import random
from datetime import datetime
from typing import Dict, List, Optional
from difflib import SequenceMatcher

import aiohttp
import feedparser
from loguru import logger

from shared.config import settings
from shared.database import get_news_articles


# ── RSS Feed Sources per Category ─────────────────────────────
# Expanded with more diverse sources for better coverage

RSS_SOURCES: Dict[str, List[Dict]] = {
    "bola": [
        # === SOCCER-ONLY FEEDS (no mixed sports) ===
        {"name": "Goal Indonesia", "url": "https://www.goal.com/feeds/id/news"},
        {"name": "Bola.net", "url": "https://www.bola.net/feed/"},
        {"name": "Kompas Bola", "url": "https://bola.kompas.com/rss"},
        {"name": "Bola.com", "url": "https://www.bola.com/rss"},
        {"name": "Tribun Bola", "url": "https://www.tribunnews.com/rss/superskor"},
        {"name": "BBC Sport Football", "url": "https://feeds.bbci.co.uk/sport/football/rss.xml"},
        {"name": "ESPN FC", "url": "https://www.espn.com/espn/rss/soccer/news"},
    ],
    "teknologi": [
        {"name": "CNN Tech", "url": "https://www.cnnindonesia.com/teknologi/rss"},
        {"name": "The Verge", "url": "https://www.theverge.com/rss/index.xml"},
        {"name": "Ars Technica", "url": "https://feeds.arstechnica.com/arstechnica/index"},
        {"name": "TechCrunch", "url": "https://techcrunch.com/feed/"},
        {"name": "Wired", "url": "https://www.wired.com/feed/rss"},
        {"name": "Detik Inet", "url": "https://rss.detik.com/index.php/inet"},
        {"name": "Kompas Tekno", "url": "https://tekno.kompas.com/rss"},
    ],
    "politik": [
        {"name": "BBC Indonesia", "url": "https://feeds.bbci.co.uk/indonesia/rss.xml"},
        {"name": "CNN Internasional", "url": "https://www.cnnindonesia.com/internasional/rss"},
        {"name": "CNN Nasional", "url": "https://www.cnnindonesia.com/nasional/rss"},
        {"name": "Reuters World", "url": "https://www.reutersagency.com/feed/?taxonomy=best-sectors&post_type=best"},
        {"name": "Al Jazeera", "url": "https://www.aljazeera.com/xml/rss/all.xml"},
        {"name": "Kompas Internasional", "url": "https://internasional.kompas.com/rss"},
        {"name": "Detik News", "url": "https://rss.detik.com/index.php/detikcom"},
    ],
    "ekonomi": [
        {"name": "CNBC Indonesia", "url": "https://www.cnbcindonesia.com/rss"},
        {"name": "CNN Ekonomi", "url": "https://www.cnnindonesia.com/ekonomi/rss"},
        {"name": "Detik Finance", "url": "https://rss.detik.com/index.php/finance"},
        {"name": "Kompas Money", "url": "https://money.kompas.com/rss"},
        {"name": "Bisnis.com", "url": "https://www.bisnis.com/rss"},
        {"name": "Bloomberg", "url": "https://www.bloomberg.com/feed/podcast/decrypted.xml"},
        {"name": "Kontan", "url": "https://www.kontan.co.id/rss"},
    ],
    "rekomendasi": [
        {"name": "GSMArena", "url": "https://www.gsmarena.com/rss-news-reviews.php3"},
        {"name": "Gadgets360", "url": "https://feeds.feedburner.com/gadgets360-latest"},
        {"name": "Tom's Guide", "url": "https://www.tomsguide.com/feeds/all"},
    ],
}

# Google News search queries per category (expanded & more specific)
GOOGLE_NEWS_QUERIES: Dict[str, List[str]] = {
    "bola": [
        # Soccer-specific queries only (no badminton, basketball, etc.)
        "sepak bola hari ini",
        "liga 1 BRI indonesia terbaru",
        "transfer pemain sepak bola 2026",
        "liga champions UEFA terbaru",
        "timnas indonesia sepak bola",
        "premier league terbaru",
        "la liga spanyol terbaru",
        "serie A italia terbaru",
        "piala dunia FIFA terbaru",
        "hasil pertandingan sepak bola",
    ],
    "teknologi": [
        "teknologi terbaru 2026",
        "gadget baru rilis",
        "update smartphone terbaru",
        "AI artificial intelligence terbaru",
        "aplikasi baru populer",
        "cybersecurity keamanan siber",
        "startup teknologi Indonesia",
        "chip prosesor terbaru",
    ],
    "politik": [
        "berita politik dunia hari ini",
        "konflik internasional terbaru",
        "geopolitik dunia",
        "kebijakan pemerintah terbaru",
        "hubungan internasional diplomasi",
        "pemilu demokrasi dunia",
        "PBB United Nations terbaru",
    ],
    "ekonomi": [
        "ekonomi indonesia terbaru",
        "bisnis startup indonesia",
        "saham IHSG hari ini",
        "inflasi ekonomi global",
        "peluang bisnis 2026",
        "Bank Indonesia kebijakan moneter",
        "UMKM digital Indonesia",
        "harga emas investasi",
    ],
    "rekomendasi": [
        "HP terbaik 2026",
        "smartwatch terbaik murah",
        "laptop terbaik mahasiswa",
        "earbuds TWS terbaik",
        "gadget murah berkualitas",
    ],
}

# Keywords to EXCLUDE from bola/soccer category
# This ensures only soccer content, not mixed sports
BOLA_EXCLUDE_KEYWORDS = [
    "badminton", "bulu tangkis", "bulutangkis",
    "basket", "basketball", "NBA",
    "tenis", "tennis", "voli", "volleyball",
    "tinju", "boxing", "MMA", "UFC",
    "Formula 1", "F1", "MotoGP", "motogp",
    "renang", "swimming", "atletik", "athletics",
    "golf", "cricket", "rugby", "hockey",
    "e-sport", "esport", "esports",
    "olimpiade", "olympics",
]


# ── Deduplication Functions ───────────────────────────────────

def _normalize_text(text: str) -> str:
    """Normalize text for comparison: lowercase, strip punctuation, collapse spaces."""
    text = text.lower().strip()
    text = re.sub(r'[^\w\s]', '', text)  # remove punctuation
    text = re.sub(r'\s+', ' ', text)      # collapse spaces
    return text


def _title_similarity(title1: str, title2: str) -> float:
    """Calculate similarity ratio between two titles (0.0 to 1.0)."""
    t1 = _normalize_text(title1)
    t2 = _normalize_text(title2)
    return SequenceMatcher(None, t1, t2).ratio()


def _extract_keywords(title: str) -> set:
    """Extract meaningful keywords from a title (ignoring stop words)."""
    STOP_WORDS_ID = {
        "dan", "di", "ke", "dari", "yang", "ini", "itu", "untuk", "dengan",
        "pada", "adalah", "juga", "akan", "atau", "oleh", "saat", "dalam",
        "tidak", "sudah", "bisa", "ada", "lebih", "tahun", "baru", "setelah",
        "the", "of", "in", "to", "for", "a", "an", "and", "is", "on", "at",
        "by", "as", "with", "its", "has", "be", "was", "were", "been",
    }
    words = _normalize_text(title).split()
    return {w for w in words if len(w) > 2 and w not in STOP_WORDS_ID}


def _topic_overlap(title1: str, title2: str) -> float:
    """Calculate keyword overlap ratio between two titles."""
    kw1 = _extract_keywords(title1)
    kw2 = _extract_keywords(title2)
    if not kw1 or not kw2:
        return 0.0
    intersection = kw1 & kw2
    union = kw1 | kw2
    return len(intersection) / len(union) if union else 0.0


def is_duplicate(new_title: str, existing_titles: list, threshold: float = 0.55) -> bool:
    """
    Check if a headline is a duplicate of any existing title.
    Uses BOTH sequence matching AND keyword overlap for better accuracy.
    Threshold 0.55 = titles sharing >55% similarity are considered duplicates.
    """
    for existing in existing_titles:
        # Method 1: Sequence similarity (catches paraphrased titles)
        seq_sim = _title_similarity(new_title, existing)
        if seq_sim > threshold:
            return True

        # Method 2: Keyword overlap (catches same-topic different wording)
        kw_overlap = _topic_overlap(new_title, existing)
        if kw_overlap > 0.6:  # >60% keyword overlap = same topic
            return True

    return False


def is_soccer_content(title: str, summary: str = "") -> bool:
    """Check if content is about soccer/football (not other sports)."""
    combined = f"{title} {summary}".lower()
    for keyword in BOLA_EXCLUDE_KEYWORDS:
        if keyword.lower() in combined:
            return False
    return True


# Track used headlines to avoid duplicates (DB-based, survives Render restarts)

async def get_existing_titles() -> list:
    """Get titles of existing articles from DB for deduplication."""
    try:
        articles = await get_news_articles(limit=300)
        return [a["title"] for a in articles]
    except Exception:
        return []


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

            # Clean HTML from summary but first try to extract image if any
            image_url = ""
            if "media_content" in entry and len(entry.media_content) > 0:
                image_url = entry.media_content[0].get("url", "")
            elif "media_thumbnail" in entry and len(entry.media_thumbnail) > 0:
                image_url = entry.media_thumbnail[0].get("url", "")
            elif "links" in entry:
                for link in entry.links:
                    if link.get("rel") == "enclosure" and "image" in link.get("type", ""):
                        image_url = link.get("href", "")
                        break
            
            if not image_url and "<img" in summary:
                match = re.search(r'src="([^"]+)"', summary)
                if match:
                    image_url = match.group(1)

            summary = re.sub(r"<[^>]+>", "", summary)
            summary = summary[:500]  # limit length

            results.append({
                "title": title,
                "summary": summary,
                "source_url": link,
                "source_name": source_name,
                "published": published,
                "original_image_url": image_url,
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
            
            image_url = ""
            if "<img" in summary:
                match = re.search(r'src="([^"]+)"', summary)
                if match:
                    image_url = match.group(1)

            summary = re.sub(r"<[^>]+>", "", summary)[:500]
            link = entry.get("link", "")

            if title:
                results.append({
                    "title": title,
                    "summary": summary,
                    "source_url": link,
                    "source_name": source_name or "Google News",
                    "published": entry.get("published", ""),
                    "original_image_url": image_url,
                })

        return results

    except Exception as e:
        logger.warning(f"Google News search failed for '{query}': {e}")
        return []


async def fetch_google_news(category: str) -> List[Dict]:
    """Fetch Google News for random queries in a category."""
    queries = GOOGLE_NEWS_QUERIES.get(category, [])
    if not queries:
        return []

    # Pick 3 random queries (increased from 2) for more diversity
    selected = random.sample(queries, min(3, len(queries)))
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
    Combines RSS + Google News, deduplicates semantically,
    filters already-published topics and non-soccer content for bola.
    Returns top `count` fresh topics.
    """
    # Fetch from both sources in parallel
    rss_task = fetch_all_rss(category)
    google_task = fetch_google_news(category)
    existing_task = get_existing_titles()
    rss_results, google_results, existing_titles = await asyncio.gather(
        rss_task, google_task, existing_task
    )

    # Combine all headlines
    all_headlines = rss_results + google_results

    # Filter: for bola category, ONLY keep soccer content
    if category == "bola":
        before_count = len(all_headlines)
        all_headlines = [
            h for h in all_headlines
            if is_soccer_content(h["title"], h.get("summary", ""))
        ]
        filtered = before_count - len(all_headlines)
        if filtered > 0:
            logger.info(f"Bola filter: removed {filtered} non-soccer headlines")

    # Semantic deduplication against existing DB articles
    unique = []
    accepted_titles = []  # titles accepted in this batch

    for item in all_headlines:
        title = item["title"]

        # Skip if too similar to existing DB articles
        if is_duplicate(title, existing_titles, threshold=0.55):
            continue

        # Skip if too similar to already-accepted headlines in this batch
        if is_duplicate(title, accepted_titles, threshold=0.50):
            continue

        unique.append(item)
        accepted_titles.append(title)

    # Shuffle to add variety, then return top `count`
    random.shuffle(unique)
    result = unique[:count]

    logger.info(
        f"Trending [{category}]: {len(all_headlines)} total → "
        f"{len(unique)} unique (semantic dedup) → returning {len(result)}"
    )
    return result
