"""
AI News Rewriter — takes headline + summary from scraper,
generates original Indonesian article using Gemini AI.
"""

import re
from datetime import datetime
from typing import Dict, Optional

from loguru import logger

from shared.gemini_client import gemini
from shared.config import settings


# ── Category-specific writing styles ──────────────────────────

CATEGORY_PROMPTS = {
    "bola": {
        "style": "jurnalis sepak bola yang antusias, informatif, dan paham dunia sepak bola",
        "tone": "energetic, passionate, factual",
        "extra": "Fokus HANYA pada sepak bola (football/soccer). Gunakan istilah sepak bola yang tepat (lini belakang, playmaker, clean sheet, hat-trick, dst). Sertakan statistik pertandingan, skor, klasemen, atau data transfer jika relevan. Jangan bahas olahraga lain (badminton, basket, tenis, dll).",
    },
    "teknologi": {
        "style": "tech journalist yang paham teknologi dan gadget",
        "tone": "informative, analytical, forward-looking",
        "extra": "Jelaskan istilah teknis dengan bahasa yang mudah dipahami pembaca umum.",
    },
    "politik": {
        "style": "jurnalis politik internasional yang objektif dan analitis",
        "tone": "serious, balanced, analytical",
        "extra": "Berikan konteks geopolitik. Sajikan dari berbagai sudut pandang secara netral.",
    },
    "ekonomi": {
        "style": "jurnalis ekonomi dan bisnis yang analitis",
        "tone": "professional, data-driven, insightful",
        "extra": "Sertakan data/angka jika relevan. Jelaskan dampak ke masyarakat umum.",
    },
    "rekomendasi": {
        "style": "tech reviewer yang jujur dan membantu pembaca memilih produk",
        "tone": "helpful, comparative, honest",
        "extra": "Buat perbandingan yang objektif. Sebutkan kelebihan dan kekurangan.",
    },
}


async def rewrite_news(
    headline: Dict,
    category: str,
    affiliate_links: str = "",
) -> Optional[Dict]:
    """
    Rewrite a news headline into a full original article in Bahasa Indonesia using autonomous pipeline.

    Args:
        headline: Dict with 'title', 'summary', 'source_url', 'source_name'
        category: Category key (bola, teknologi, politik, ekonomi, rekomendasi)
        affiliate_links: Optional affiliate link HTML to embed (for rekomendasi)

    Returns:
        Dict with article fields or None if blocked/skipped.
    """
    from news_app.editorial_pipeline import run_editorial_pipeline
    
    try:
        return await run_editorial_pipeline(headline, category, affiliate_links)
    except Exception as e:
        logger.error(f"Editorial pipeline failed for '{headline.get('title', '')}': {e}")
        return None



async def generate_recommendation_article(topic: str) -> Optional[Dict]:
    """
    Generate a recommendation/review article for the 'rekomendasi' category.
    This doesn't need a news source — it generates from topic directly.
    """
    # Build affiliate links
    aff_links = []
    shopee_id = settings.affiliate.shopee_id
    alfagift_id = settings.affiliate.alfagift_id

    search_term = topic.replace(" ", "+")
    if shopee_id:
        aff_links.append(
            f'<a href="https://shopee.co.id/search?keyword={search_term}&af_id={shopee_id}" '
            f'target="_blank" rel="nofollow">Cek Harga di Shopee</a>'
        )
    if alfagift_id:
        aff_links.append(
            f'<a href="https://alfagift.id/search/{search_term}?ref={alfagift_id}" '
            f'target="_blank" rel="nofollow">Lihat di Alfagift</a>'
        )

    affiliate_html = " | ".join(aff_links) if aff_links else ""

    headline = {
        "title": topic,
        "summary": f"Artikel rekomendasi dan review tentang {topic}",
        "source_url": "",
        "source_name": "Editorial",
    }

    return await rewrite_news(
        headline=headline,
        category="rekomendasi",
        affiliate_links=affiliate_html,
    )
