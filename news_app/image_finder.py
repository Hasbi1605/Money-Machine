"""
Image Finder — searches Pexels for relevant news thumbnails.
Reuses Pexels API integration from social_engine.
"""

import random
from typing import Optional

import aiohttp
from loguru import logger

from shared.config import settings


async def find_thumbnail(
    query: str,
    orientation: str = "landscape",
    per_page: int = 10,
) -> Optional[str]:
    """
    Search Pexels for a relevant thumbnail image.
    Returns the image URL (direct link) or None.

    We return the Pexels URL directly instead of downloading,
    to save storage on Render free tier.
    """
    api_key = settings.pexels.api_key
    if not api_key:
        logger.warning("Pexels API key not set — no thumbnail")
        return None

    headers = {"Authorization": api_key}
    params = {
        "query": query,
        "per_page": per_page,
        "orientation": orientation,
        "size": "medium",
    }

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(
                "https://api.pexels.com/v1/search",
                params=params,
                timeout=aiohttp.ClientTimeout(total=15),
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"Pexels API returned {resp.status}")
                    return None

                data = await resp.json()
                photos = data.get("photos", [])

                if not photos:
                    logger.info(f"No Pexels results for: {query}")
                    return None

                photo = random.choice(photos)
                # "landscape" size ≈ 1200x627 — perfect for article thumbnail
                url = (
                    photo.get("src", {}).get("landscape")
                    or photo.get("src", {}).get("large")
                    or photo.get("src", {}).get("original")
                )
                return url

    except Exception as e:
        logger.error(f"Pexels search failed for '{query}': {e}")
        return None


# Fallback placeholder images per category
CATEGORY_FALLBACKS = {
    "bola": "https://images.pexels.com/photos/46798/the-ball-stadion-football-the-pitch-46798.jpeg?auto=compress&cs=tinysrgb&w=1200",
    "teknologi": "https://images.pexels.com/photos/546819/pexels-photo-546819.jpeg?auto=compress&cs=tinysrgb&w=1200",
    "politik": "https://images.pexels.com/photos/3873876/pexels-photo-3873876.jpeg?auto=compress&cs=tinysrgb&w=1200",
    "ekonomi": "https://images.pexels.com/photos/6801648/pexels-photo-6801648.jpeg?auto=compress&cs=tinysrgb&w=1200",
    "rekomendasi": "https://images.pexels.com/photos/1294886/pexels-photo-1294886.jpeg?auto=compress&cs=tinysrgb&w=1200",
}


async def get_article_thumbnail(query: str, category: str) -> str:
    """
    Get a thumbnail URL for an article.
    Tries Pexels first, falls back to a category-specific default.
    """
    url = await find_thumbnail(query)
    if url:
        return url

    # Try a simpler query (just the category keyword)
    simple_queries = {
        "bola": "football soccer",
        "teknologi": "technology gadget",
        "politik": "world politics",
        "ekonomi": "business economy",
        "rekomendasi": "smartphone gadget review",
    }
    simple = simple_queries.get(category, "news")
    url = await find_thumbnail(simple)
    if url:
        return url

    # Fallback to static URL
    return CATEGORY_FALLBACKS.get(category, CATEGORY_FALLBACKS["teknologi"])
