"""
Telegram notification bot for monitoring.
"""

import asyncio
from typing import Optional

import aiohttp
from loguru import logger

from shared.config import settings


class TelegramNotifier:
    """Send notifications to Telegram."""

    def __init__(self):
        self.token = settings.telegram.bot_token
        self.chat_id = settings.telegram.chat_id
        self.enabled = bool(self.token and self.chat_id)
        self.base_url = f"https://api.telegram.org/bot{self.token}"

    async def send(self, message: str, parse_mode: str = "HTML"):
        """Send a message to Telegram."""
        if not self.enabled:
            logger.debug(f"Telegram disabled. Message: {message[:100]}")
            return

        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "chat_id": self.chat_id,
                    "text": message,
                    "parse_mode": parse_mode,
                }
                async with session.post(
                    f"{self.base_url}/sendMessage", json=payload
                ) as resp:
                    if resp.status != 200:
                        logger.error(f"Telegram send failed: {await resp.text()}")
                    else:
                        logger.debug("Telegram notification sent")
        except Exception as e:
            logger.error(f"Telegram error: {e}")

    async def send_media_group(self, media_list: list, caption: str = "") -> bool:
        """
        Send a media group (album of images) to Telegram.
        media_list: List of io.BytesIO objects
        caption: Caption for the first image
        """
        if not self.enabled or not media_list:
            logger.debug("Telegram disabled or empty media list.")
            return False

        try:
            data = aiohttp.FormData()
            data.add_field("chat_id", self.chat_id)
            
            media_json = []
            for i, bio in enumerate(media_list):
                # We need to attach the file content using aiohttp
                field_name = f"photo_{i}"
                data.add_field(field_name, bio.getvalue(), filename=bio.name, content_type="image/png")
                
                # Build the media object for the JSON payload
                media_item = {
                    "type": "photo",
                    "media": f"attach://{field_name}",
                }
                if i == 0 and caption:
                    media_item["caption"] = caption
                    media_item["parse_mode"] = "HTML"
                media_json.append(media_item)

            import json
            data.add_field("media", json.dumps(media_json))

            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{self.base_url}/sendMediaGroup", data=data
                ) as resp:
                    if resp.status != 200:
                        logger.error(f"Telegram sendMediaGroup failed: {await resp.text()}")
                        return False
                    else:
                        logger.info(f"Telegram media group sent ({len(media_list)} items)")
                        return True
                        
        except Exception as e:
            logger.error(f"Telegram media group error: {e}")
            return False

    async def send_success(self, pipeline: str, details: str):
        """Send a success notification."""
        msg = f"✅ <b>{pipeline}</b>\n{details}"
        await self.send(msg)

    async def send_error(self, pipeline: str, error: str):
        """Send an error notification."""
        msg = f"❌ <b>{pipeline} ERROR</b>\n<code>{error[:500]}</code>"
        await self.send(msg)

    async def send_daily_report(self, stats: dict):
        """Send daily stats report."""
        msg = (
            f"📊 <b>Daily Report</b>\n"
            f"━━━━━━━━━━━━━━━━\n"
            f"📝 Articles: {stats.get('total_articles', 0)}\n"
            f"🎬 Videos: {stats.get('total_videos', 0)}\n"
            f"🔄 Runs today: {stats.get('runs_today', 0)}\n"
            f"⚠️ Errors today: {stats.get('errors_today', 0)}\n"
        )
        await self.send(msg)


# Singleton
notifier = TelegramNotifier()
