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

async def fetch_og_image(url: str) -> str:
    from bs4 import BeautifulSoup
    import aiohttp
    
    if not url:
        return ""
        
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"}
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    html = await resp.text()
                    soup = BeautifulSoup(html, 'html.parser')
                    og_image = soup.find('meta', property='og:image')
                    if og_image and og_image.get('content'):
                        return og_image['content']
    except Exception as e:
        logger.warning(f"Failed to fetch og:image for {url}: {e}")
    return ""


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

                # Get thumbnail (use AI prompt for hybrid image strategy)
                thumbnail_query = article.get("thumbnail_query", topic)
                ai_prompt = article.get("thumbnail_query", "")  # Use as AI image prompt too
                original_img = article.get("original_image_url", "")
                thumbnail = await get_article_thumbnail(
                    thumbnail_query, "rekomendasi", ai_prompt=ai_prompt, original_image_url=original_img
                )
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

                # Get thumbnail (use AI prompt for hybrid image strategy)
                thumbnail_query = article.get("thumbnail_query", headline["title"])
                ai_prompt = article.get("thumbnail_query", "")  # Use as AI image prompt too
                
                # Fetch high-quality og:image from the source URL instead of relying on low-res RSS thumbnails
                original_img = await fetch_og_image(headline.get("source_url", ""))
                if not original_img:
                    original_img = article.get("original_image_url", "")
                    
                thumbnail = await get_article_thumbnail(
                    thumbnail_query, category, ai_prompt=ai_prompt, original_image_url=original_img
                )
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
    - Newsletter: every 24 hours (morning)
    """
    from news_app.newsletter import send_newsletter
    from news_app.social_generator import generate_carousel, generate_caption
    from shared.notifier import notifier
    from shared.database import get_news_articles

    logger.info("📅 News scheduler started")

    # Skip initial auto-generate on startup to avoid crash on Render free tier.
    # Use /tulis via Telegram bot to generate manually, or wait for first cycle.
    logger.info("⏳ First auto-generate in 6 hours. Use /tulis for manual trigger.")

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

            # Newsletter & Instagram Recap every 4 cycles (24 hours)
            if cycle % 4 == 0:
                try:
                    sent = await send_newsletter()
                    logger.info(f"📬 Newsletter cycle complete: {sent} emails")
                except Exception as e:
                    logger.error(f"Newsletter failed: {e}")

                try:
                    logger.info("📸 Starting daily Instagram Auto-Carousel generation...")
                    articles = await get_news_articles(limit=5)
                    if articles:
                        slides = await generate_carousel(articles)
                        caption = await generate_caption(articles)
                        success = await notifier.send_media_group(slides, caption)
                        if success:
                            logger.info("✅ Daily Instagram Recap sent to Telegram.")
                        else:
                            logger.error("❌ Failed to send Daily Instagram Recap.")
                except Exception as e:
                    logger.error(f"Instagram Auto-Carousel generation failed: {e}")

        except Exception as e:
            logger.error(f"Scheduler cycle {cycle} failed: {e}")
            await asyncio.sleep(60)
