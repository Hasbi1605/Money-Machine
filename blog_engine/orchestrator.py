"""
Blog Engine Orchestrator - Runs the full article generation pipeline.
Keyword Research → Article Generation → Publishing → Notification
"""

import asyncio
from typing import Optional
from datetime import datetime

from loguru import logger

from blog_engine.keyword_researcher import get_fresh_keyword
from blog_engine.article_generator import generate_article, generate_social_snippets
from blog_engine.publisher import publisher
from shared.database import log_article, log_pipeline_run, finish_pipeline_run
from shared.notifier import notifier
from shared.config import settings


async def run_blog_pipeline(language: str = "en") -> bool:
    """
    Run the full blog generation pipeline for one article.

    Steps:
    1. Research and pick a keyword
    2. Generate SEO article with affiliate links
    3. Publish to all configured platforms
    4. Generate social media snippets
    5. Log to database and notify via Telegram

    Returns True if successful.
    """
    pipeline_name = f"Blog Engine ({language.upper()})"
    run_id = await log_pipeline_run(pipeline_name)

    try:
        # Step 1: Keyword Research
        logger.info(f"[{pipeline_name}] Step 1: Keyword Research")
        keyword_data = await get_fresh_keyword(language)

        if not keyword_data:
            raise Exception("No keyword found - all candidates exhausted")

        keyword = keyword_data.get("keyword", "unknown")
        logger.info(f"[{pipeline_name}] Selected keyword: {keyword}")

        # Step 2: Generate Article
        logger.info(f"[{pipeline_name}] Step 2: Generating Article")
        article = await generate_article(keyword_data, language)

        if not article or not article.get("content"):
            raise Exception(f"Article generation failed for keyword: {keyword}")

        title = article.get("title", "Untitled")
        word_count = article.get("word_count", len(article["content"].split()))
        logger.info(f"[{pipeline_name}] Article ready: '{title}' ({word_count} words)")

        # Step 3: Publish
        logger.info(f"[{pipeline_name}] Step 3: Publishing")
        publish_results = await publisher.publish_all(article)

        published_urls = {k: v for k, v in publish_results.items() if v}
        platform_list = ", ".join(published_urls.keys()) if published_urls else "none (saved locally)"

        # Step 4: Generate Social Snippets (non-blocking, save for later use)
        logger.info(f"[{pipeline_name}] Step 4: Social Snippets")
        social = await generate_social_snippets(article)

        # Step 5: Log to Database
        for platform, url in published_urls.items():
            await log_article(
                title=title,
                keyword=keyword,
                language=language,
                platform=platform,
                platform_url=url or "",
                word_count=word_count,
            )

        # If nothing was published to any platform, still log locally
        if not published_urls:
            await log_article(
                title=title,
                keyword=keyword,
                language=language,
                platform="local",
                platform_url="",
                word_count=word_count,
            )

        # Step 6: Notify
        await finish_pipeline_run(run_id, items=1)
        await notifier.send_success(
            pipeline_name,
            f"📝 <b>{title}</b>\n"
            f"🔑 Keyword: {keyword}\n"
            f"📊 Words: {word_count}\n"
            f"🌐 Published: {platform_list}\n"
            f"🔗 Links: {article.get('affiliate_links', 0)} affiliate links"
        )

        logger.info(f"[{pipeline_name}] ✅ Pipeline completed successfully")
        return True

    except Exception as e:
        error_msg = str(e)
        logger.error(f"[{pipeline_name}] ❌ Pipeline failed: {error_msg}")
        await finish_pipeline_run(run_id, error=error_msg)
        await notifier.send_error(pipeline_name, error_msg)
        return False


async def run_blog_cycle():
    """
    Run one full cycle of blog generation.
    Generates articles for all configured languages.
    """
    languages = settings.get_languages()
    logger.info(f"Starting blog cycle for languages: {languages}")

    results = {}
    for lang in languages:
        success = await run_blog_pipeline(lang)
        results[lang] = success
        # Small delay between languages to respect rate limits
        await asyncio.sleep(5)

    success_count = sum(1 for v in results.values() if v)
    total = len(results)
    logger.info(f"Blog cycle completed: {success_count}/{total} successful")

    return results


if __name__ == "__main__":
    asyncio.run(run_blog_cycle())
