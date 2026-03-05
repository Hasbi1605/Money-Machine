"""Run CikalNews bot in polling mode for local testing."""
import asyncio
import sys
sys.path.insert(0, ".")
from shared.database import init_db
from news_app.telegram_bot import polling_loop, send_message
from shared.config import settings

async def main():
    await init_db()
    await send_message(
        settings.telegram.chat_id,
        "🤖 CikalNews Bot ONLINE!\n\nKetik /start untuk mulai.\nKetik /help untuk daftar perintah."
    )
    print("Bot started in polling mode. Send commands via Telegram...")
    await polling_loop()

asyncio.run(main())
