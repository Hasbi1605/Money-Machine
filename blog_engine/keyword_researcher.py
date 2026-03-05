"""
Keyword Researcher - Finds profitable keywords using Google Suggest + Gemini analysis.
Works for both English and Indonesian content.
"""

import asyncio
import json
import re
from typing import List, Dict, Optional
from pathlib import Path

import aiohttp
from loguru import logger

from shared.gemini_client import gemini
from shared.config import settings


# Profitable niches for affiliate content
NICHES = {
    "en": [
        "best budget laptop", "best wireless earbuds", "best robot vacuum",
        "best air purifier", "best standing desk", "best protein powder",
        "best VPN service", "best web hosting", "best online course platform",
        "how to make money online", "best side hustles", "passive income ideas",
        "best productivity apps", "best AI tools", "best smart home devices",
        "best fitness tracker", "best portable charger", "best monitor for work",
        "best mechanical keyboard", "best ergonomic chair",
        "best coffee maker", "best air fryer", "best instant pot recipes",
        "best travel backpack", "how to start a blog",
    ],
    "id": [
        "laptop murah terbaik", "earbuds wireless terbaik",
        "robot vacuum terbaik", "air purifier terbaik indonesia",
        "cara menghasilkan uang dari internet", "ide bisnis online",
        "aplikasi penghasil uang", "investasi untuk pemula",
        "gadget murah berkualitas", "HP terbaik harga 2 jutaan",
        "HP terbaik harga 3 jutaan", "smartwatch murah terbaik",
        "alat masak terbaik", "rice cooker terbaik",
        "skincare terbaik untuk pemula", "sunscreen terbaik indonesia",
        "kamera mirrorless murah", "tips hemat belanja online",
        "rekomendasi laptop untuk mahasiswa", "cara memulai bisnis online",
    ],
}


async def get_google_suggestions(query: str, language: str = "en") -> List[str]:
    """Get Google autocomplete suggestions for a query."""
    hl = "id" if language == "id" else "en"
    gl = "id" if language == "id" else "us"

    url = "https://suggestqueries.google.com/complete/search"
    params = {
        "client": "firefox",
        "q": query,
        "hl": hl,
        "gl": gl,
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, params=params, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json(content_type=None)
                    if isinstance(data, list) and len(data) > 1:
                        return data[1][:10]
    except Exception as e:
        logger.warning(f"Google suggest failed for '{query}': {e}")

    return []


async def expand_keyword(seed: str, language: str = "en") -> List[str]:
    """Expand a seed keyword into long-tail variations."""
    suggestions = await get_google_suggestions(seed, language)

    # Also try with prefixes for more variations
    prefixes = ["best", "top", "how to", "why"] if language == "en" else [
        "cara", "rekomendasi", "tips", "kenapa"
    ]

    for prefix in prefixes[:2]:  # Limit to avoid rate limiting
        extra = await get_google_suggestions(f"{prefix} {seed}", language)
        suggestions.extend(extra)
        await asyncio.sleep(0.5)  # Be nice to Google

    # Remove duplicates while preserving order
    seen = set()
    unique = []
    for s in suggestions:
        if s.lower() not in seen:
            seen.add(s.lower())
            unique.append(s)

    return unique


async def analyze_keywords(keywords: List[str], language: str = "en") -> List[Dict]:
    """Use Gemini to analyze and rank keywords by monetization potential."""

    prompt = f"""Analyze these keywords for SEO blog content potential. 
Language: {"Indonesian" if language == "id" else "English"}

Keywords:
{json.dumps(keywords, indent=2)}

For each keyword, evaluate:
1. Search intent (informational, commercial, transactional)
2. Monetization potential (1-10): can affiliate links be naturally included?
3. Competition estimate (low, medium, high)
4. Recommended article type (listicle, how-to, review, comparison, guide)

Return a JSON array of objects with these fields:
- keyword: the keyword
- intent: search intent type
- monetization_score: 1-10
- competition: low/medium/high
- article_type: recommended type
- suggested_title: a click-worthy SEO title
- reason: brief explanation

Sort by monetization_score DESC. Return only the top 5 most profitable keywords."""

    try:
        results = await gemini.generate_json(prompt)
        if isinstance(results, dict) and "keywords" in results:
            results = results["keywords"]
        if isinstance(results, list):
            return results[:5]
    except Exception as e:
        logger.error(f"Keyword analysis failed: {e}")

    # Fallback: return keywords as-is with default scores
    return [
        {"keyword": kw, "monetization_score": 5, "article_type": "listicle",
         "suggested_title": kw.title(), "intent": "commercial", "competition": "medium"}
        for kw in keywords[:5]
    ]


async def research_keywords(language: str = "en", count: int = 3) -> List[Dict]:
    """
    Full keyword research pipeline:
    1. Pick seed keywords from niches
    2. Expand with Google Suggest
    3. Analyze with Gemini
    4. Return top keywords ready for article generation
    """
    import random

    logger.info(f"Starting keyword research for language: {language}")

    seeds = NICHES.get(language, NICHES["en"])
    selected_seeds = random.sample(seeds, min(5, len(seeds)))

    all_keywords = []
    for seed in selected_seeds:
        expanded = await expand_keyword(seed, language)
        all_keywords.extend(expanded)
        all_keywords.append(seed)  # Include the seed itself
        await asyncio.sleep(1)  # Rate limiting

    # Remove duplicates
    all_keywords = list(set(all_keywords))
    logger.info(f"Found {len(all_keywords)} keyword candidates")

    if not all_keywords:
        # Fallback to seeds if suggestions fail
        all_keywords = selected_seeds

    # Analyze with Gemini
    analyzed = await analyze_keywords(all_keywords[:30], language)  # Limit to 30

    # Return top results
    top = sorted(analyzed, key=lambda x: x.get("monetization_score", 0), reverse=True)
    result = top[:count]

    logger.info(f"Top keywords: {[k.get('keyword', '') for k in result]}")
    return result


# Track used keywords to avoid repetition
USED_KEYWORDS_FILE = settings.data_dir / "used_keywords.json"


def load_used_keywords() -> set:
    """Load previously used keywords."""
    if USED_KEYWORDS_FILE.exists():
        with open(USED_KEYWORDS_FILE) as f:
            return set(json.load(f))
    return set()


def save_used_keyword(keyword: str):
    """Save a keyword as used."""
    used = load_used_keywords()
    used.add(keyword.lower())
    with open(USED_KEYWORDS_FILE, "w") as f:
        json.dump(list(used), f)


async def get_fresh_keyword(language: str = "en") -> Optional[Dict]:
    """Get a keyword that hasn't been used before."""
    used = load_used_keywords()
    candidates = await research_keywords(language, count=5)

    for candidate in candidates:
        kw = candidate.get("keyword", "").lower()
        if kw and kw not in used:
            save_used_keyword(kw)
            return candidate

    # If all candidates are used, force the best one anyway (content can differ)
    if candidates:
        save_used_keyword(candidates[0].get("keyword", ""))
        return candidates[0]

    return None
