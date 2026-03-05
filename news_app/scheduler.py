"""
CikalNews Scheduler — auto-generates news articles on a schedule.
Runs as a background task inside the FastAPI app.
"""

import asyncio
import random
from datetime import datetime
from typing import List

from loguru import logger

from news_app.scraper import get_trending_topics
from news_app.rewriter import rewrite_news, generate_recommendation_article
from news_app.image_finder import get_article_thumbnail
from shared.database import save_news_article


# ── Recommendation topics pool ───────────────────────────────

REKOMENDASI_TOPICS = [
    "HP Terbaik 2025 di Bawah 3 Juta",
    "Smartwatch Terbaik untuk Olahraga 2025",
    "Laptop Gaming Terbaik Harga 10 Jutaan",
    "Earbuds TWS Terbaik di Bawah 500 Ribu",
    "Tablet Terbaik untuk Pelajar dan Mahasiswa",
    "Kamera Mirrorless Terbaik untuk Pemula",
    "Mouse Gaming Terbaik 2025",
    "Keyboard Mechanical Terbaik untuk Kerja",
    "Monitor Terbaik untuk Desainer Grafis",
    "Router WiFi 6 Terbaik untuk Rumah",
    "Power Bank Terbaik 2025 Fast Charging",
    "Speaker Bluetooth Terbaik di Bawah 1 Juta",
    "SSD Terbaik untuk Upgrade Laptop",
    "Webcam Terbaik untuk Meeting dan Streaming",
    "Smartphone Flagship Terbaik 2025",
    "Headphone ANC Terbaik untuk Commuting",
    "Smart TV Terbaik 43 Inch Terjangkau",
    "Drone Terbaik untuk Pemula 2025",
    "Fitness Tracker Terbaik Harga Terjangkau",
    "Projector Mini Terbaik untuk Rumah",
]


async def generate_article_for_category(category: str, max_articles: int = 3) -> int:
    """
    Generate articles for a single category.
    Returns count of successfully generated articles.
    """
    generated = 0

    if category == "rekomendasi":
        # Pick random topics
        topics = random.sample(REKOMENDASI_TOPICS, min(max_articles, len(REKOMENDASI_TOPICS)))
        for topic in topics:
            try:
                logger.info(f"[rekomendasi] Generating: {topic}")

                article = await generate_recommendation_article(topic)
                if not article:
                    continue

                # Get thumbnail
                thumbnail_query = article.get("thumbnail_query", topic)
                thumbnail = await get_article_thumbnail(thumbnail_query, "rekomendasi")
                article["thumbnail_url"] = thumbnail

                # Save to DB
                article_id = await save_news_article(article)
                if article_id:
                    generated += 1
                    logger.info(f"[rekomendasi] ✅ Saved: {article['title']}")

                # Wait between articles to respect rate limits (3 models × 20 req/day = 60 total)
                await asyncio.sleep(15)

            except Exception as e:
                logger.error(f"[rekomendasi] Failed '{topic}': {e}")
                await asyncio.sleep(20)
    else:
        # Get trending topics from RSS + Google News
        headlines = await get_trending_topics(category, count=max_articles * 2)

        if not headlines:
            logger.warning(f"[{category}] No headlines found")
            return 0

        for headline in headlines[:max_articles]:
            try:
                logger.info(f"[{category}] Rewriting: {headline['title'][:60]}...")

                article = await rewrite_news(headline, category)
                if not article:
                    continue

                # Get thumbnail
                thumbnail_query = article.get("thumbnail_query", headline["title"])
                thumbnail = await get_article_thumbnail(thumbnail_query, category)
                article["thumbnail_url"] = thumbnail

                # Save to DB
                article_id = await save_news_article(article)
                if article_id:
                    generated += 1
                    logger.info(f"[{category}] ✅ Saved: {article['title']}")

                # Wait between articles
                await asyncio.sleep(15)

            except Exception as e:
                logger.error(f"[{category}] Failed: {e}")
                await asyncio.sleep(20)

    logger.info(f"[{category}] Generated {generated} articles")
    return generated


async def run_news_pipeline(categories: List[str] = None, articles_per_cat: int = 3):
    """
    Run the full news generation pipeline.
    Generates articles for specified categories (or all).
    """
    if categories is None:
        categories = ["bola", "teknologi", "politik", "ekonomi", "rekomendasi"]

    logger.info(f"📰 Starting news pipeline: {categories}")
    start = datetime.utcnow()
    total = 0

    for cat in categories:
        count = articles_per_cat
        if cat == "rekomendasi":
            count = min(2, articles_per_cat)  # Fewer rekomendasi articles

        generated = await generate_article_for_category(cat, max_articles=count)
        total += generated

        # Pause between categories to spread out API usage
        if cat != categories[-1]:
            logger.info(f"⏳ Waiting 30s before next category...")
            await asyncio.sleep(30)

    elapsed = (datetime.utcnow() - start).total_seconds()
    logger.info(f"✅ Pipeline complete! Generated {total} articles in {elapsed:.0f}s")
    return total


async def scheduler_loop():
    """
    Background scheduler that runs the pipeline periodically.
    - News categories (bola, teknologi, politik, ekonomi): every 6 hours
    - Rekomendasi: every 12 hours
    """
    logger.info("📅 News scheduler started")

    # Initial run on startup (1 article per category as warm-up)
    await asyncio.sleep(10)  # Wait for app to fully start
    try:
        await run_news_pipeline(articles_per_cat=2)
    except Exception as e:
        logger.error(f"Initial pipeline failed: {e}")

    cycle = 0
    while True:
        try:
            # Wait 6 hours
            await asyncio.sleep(6 * 3600)
            cycle += 1

            # News categories every cycle (6 hours)
            news_cats = ["bola", "teknologi", "politik", "ekonomi"]
            await run_news_pipeline(categories=news_cats, articles_per_cat=3)

            # Rekomendasi every 2 cycles (12 hours)
            if cycle % 2 == 0:
                await run_news_pipeline(categories=["rekomendasi"], articles_per_cat=2)

        except Exception as e:
            logger.error(f"Scheduler cycle {cycle} failed: {e}")
            await asyncio.sleep(60)
