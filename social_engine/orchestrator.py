"""
Social Engine Orchestrator — runs the full social content pipeline.
Generate → Image → Save → Notify
"""

import asyncio
from datetime import datetime
from typing import Dict, List, Optional

from loguru import logger

from social_engine.content_generator import generate_social_post
from shared.database import log_social_post, log_pipeline_run, finish_pipeline_run
from shared.notifier import notifier
from shared.config import settings


async def run_social_pipeline(
    language: str = "id",
    platforms: Optional[List[str]] = None,
) -> bool:
    """
    Generate one social media post (image + captions).

    Returns True if successful.
    """
    if platforms is None:
        platforms = ["instagram", "tiktok", "whatsapp"]

    pipeline_name = f"Social Engine ({language.upper()})"
    run_id = await log_pipeline_run(pipeline_name)

    try:
        post = await generate_social_post(language=language, platforms=platforms)

        if not post or not post.get("image_path"):
            raise Exception("Social post generation failed")

        title = post.get("title", "Untitled")
        image_path = post.get("image_path", "")

        # Log to database
        await log_social_post(
            title=title,
            language=language,
            niche=post.get("niche", ""),
            platforms=",".join(platforms),
            image_path=image_path,
        )

        await finish_pipeline_run(run_id, items=1)

        # Telegram notification
        platform_str = ", ".join(p.title() for p in platforms)
        caption_preview = ""
        ig_cap = post.get("captions", {}).get("instagram", "")
        if ig_cap:
            caption_preview = ig_cap[:150] + "..." if len(ig_cap) > 150 else ig_cap

        await notifier.send_success(
            pipeline_name,
            f"📸 <b>{title}</b>\n"
            f"🏷 Niche: {post.get('niche', '-')}\n"
            f"📱 Platforms: {platform_str}\n"
            f"🖼 Image: {image_path.split('/')[-1]}\n"
            f"💬 Preview: {caption_preview}"
        )

        logger.info(f"[{pipeline_name}] ✅ Post created: '{title}'")
        return True

    except Exception as e:
        error_msg = str(e)
        logger.error(f"[{pipeline_name}] ❌ Failed: {error_msg}")
        await finish_pipeline_run(run_id, error=error_msg)
        await notifier.send_error(pipeline_name, error_msg)
        return False


async def run_social_cycle():
    """Run one cycle of social content generation for all languages."""
    languages = settings.get_languages()
    logger.info(f"Starting social cycle for: {languages}")

    results = {}
    for lang in languages:
        success = await run_social_pipeline(language=lang)
        results[lang] = success
        await asyncio.sleep(5)

    ok = sum(1 for v in results.values() if v)
    logger.info(f"Social cycle done: {ok}/{len(results)} successful")
    return results


if __name__ == "__main__":
    asyncio.run(run_social_cycle())
