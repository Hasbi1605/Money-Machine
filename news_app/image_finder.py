"""
Image Finder — Hybrid strategy: Pollinations AI + Pexels fallback.
Generates relevant images for news articles using AI or stock photos.
"""

import random
import urllib.parse
from typing import Optional

import aiohttp
from loguru import logger

from shared.config import settings


def generate_pollinations_url(prompt: str, width: int = 1200, height: int = 630) -> str:
    """Generate AI image URL via Pollinations (free, no API key needed)."""
    encoded = urllib.parse.quote(prompt)
    return f"https://image.pollinations.ai/prompt/{encoded}?width={width}&height={height}&nologo=true"


async def find_thumbnail_pexels(
    query: str,
    orientation: str = "landscape",
    per_page: int = 10,
) -> Optional[str]:
    """
    Search Pexels for a relevant thumbnail image.
    Returns the image URL (direct link) or None.
    """
    api_key = settings.pexels.api_key
    if not api_key:
        logger.warning("Pexels API key not set — skipping Pexels")
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


async def get_article_thumbnail(query: str, category: str, ai_prompt: str = "", original_image_url: str = "") -> str:
    """
    Multi-source thumbnail strategy:
    1. Original Image (most accurate)
    2. Pollinations AI (Nano Banana - high quality photorealistic)
    3. Pexels stock photo (fallback)
    4. Category-specific default (final fallback)
    """
    # Strategy 1: Original Image
    if original_image_url and original_image_url.startswith("http"):
        logger.info(f"Using original image from source.")
        return original_image_url

    # Strategy 2: AI Generated via Pollinations (highly specific)
    if ai_prompt and ai_prompt.strip():
        # Clean the prompt to ensure it's photorealistic and relevant
        prompt = f"High quality photorealistic news editorial photography of: {ai_prompt}"
        logger.info(f"Using Pollinations AI: {prompt[:50]}...")
        return generate_pollinations_url(prompt)

    # Strategy 3: Pexels fallback (less specific, generic stock)
    url = await find_thumbnail_pexels(query)
    if url:
        logger.info(f"Using Pexels fallback: {query}")
        return url

    # Strategy 4: Fallback to static URL
    logger.info(f"Using static category fallback for: {category}")
    return CATEGORY_FALLBACKS.get(category, CATEGORY_FALLBACKS["teknologi"])


