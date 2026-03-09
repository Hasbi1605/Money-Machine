"""
CikalNews Telegram Bot — Control news automation via Telegram.
Supports webhook mode for Render deployment.

Commands:
  /start      - Welcome & bot info
  /tulis      - Generate all categories
  /tulis_X    - Generate specific category (bola/teknologi/politik/ekonomi/rekomendasi)
  /rekap      - Generate Instagram carousel & caption
  /status     - System stats
  /artikel    - Latest articles
  /help       - Command list
"""

import asyncio
import traceback
from datetime import datetime
from typing import Optional

import aiohttp
from loguru import logger

from shared.config import settings
from shared.database import get_news_count, get_news_articles, get_stats

# ── Telegram API ──────────────────────────────────────────────

BOT_TOKEN = settings.telegram.bot_token
CHAT_ID = settings.telegram.chat_id
API_BASE = f"https://api.telegram.org/bot{BOT_TOKEN}"

VALID_CATEGORIES = ["bola", "teknologi", "politik", "ekonomi", "rekomendasi"]
CATEGORY_ICONS = {
    "bola": "⚽",
    "teknologi": "💻",
    "politik": "🌍",
    "ekonomi": "📊",
    "rekomendasi": "⭐",
}

# Track running tasks to prevent duplicates
_running_tasks: dict = {}


async def send_message(chat_id: str, text: str, parse_mode: str = "HTML") -> bool:
    """Send a Telegram message."""
    if not BOT_TOKEN:
        logger.warning("TELEGRAM_BOT_TOKEN not set, skipping message")
        return False

    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "chat_id": chat_id,
                "text": text,
                "parse_mode": parse_mode,
                "disable_web_page_preview": True,
            }
            async with session.post(f"{API_BASE}/sendMessage", json=payload) as resp:
                if resp.status == 200:
                    return True
                else:
                    body = await resp.text()
                    logger.warning(f"Telegram send failed ({resp.status}): {body[:200]}")
                    return False
    except Exception as e:
        logger.error(f"Telegram send error: {e}")
        return False


async def set_webhook(url: str) -> bool:
    """Register Telegram webhook URL."""
    if not BOT_TOKEN:
        return False

    webhook_url = f"{url.rstrip('/')}/api/telegram"
    try:
        async with aiohttp.ClientSession() as session:
            payload = {
                "url": webhook_url,
                "allowed_updates": ["message"],
                "drop_pending_updates": True,
            }
            async with session.post(f"{API_BASE}/setWebhook", json=payload) as resp:
                data = await resp.json()
                if data.get("ok"):
                    logger.info(f"✅ Telegram webhook set: {webhook_url}")
                    return True
                else:
                    logger.error(f"Webhook setup failed: {data}")
                    return False
    except Exception as e:
        logger.error(f"Webhook setup error: {e}")
        return False


async def delete_webhook() -> bool:
    """Remove Telegram webhook (for switching to polling)."""
    if not BOT_TOKEN:
        return False
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(f"{API_BASE}/deleteWebhook") as resp:
                return (await resp.json()).get("ok", False)
    except Exception:
        return False


# ── Command Handlers ──────────────────────────────────────────


async def cmd_start(chat_id: str):
    """Handle /start command."""
    text = """🤖 <b>CikalNews Bot</b>

Selamat datang! Bot ini mengontrol otomasi portal berita <b>CikalNews</b>.

✅ Chat ID Anda telah disimpan otomatis!
Chat ID: <code>{chat_id}</code>

<b>Commands:</b>
/tulis - 📝 Generate berita semua kategori
/tulis_bola - ⚽ Generate berita bola
/tulis_teknologi - 💻 Generate berita teknologi
/tulis_politik - 🌍 Generate berita politik
/tulis_ekonomi - 📊 Generate berita ekonomi
/tulis_rekomendasi - ⭐ Generate artikel rekomendasi
/rekap - 📸 Generate Carousel Instagram
/status - 📊 Status sistem & statistik
/artikel - 📰 Artikel terbaru
/help - ❓ Bantuan

🤖 <i>Bot akan otomatis generate berita setiap 6 jam.</i>""".format(chat_id=chat_id)

    await send_message(chat_id, text)


async def cmd_help(chat_id: str):
    """Handle /help command."""
    text = """❓ <b>Bantuan CikalNews Bot</b>

<b>Generate Berita:</b>
/tulis — Generate 2-3 berita per kategori (semua)
/tulis_[kategori] — Generate 1 kategori spesifik
  Kategori: bola, teknologi, politik, ekonomi, rekomendasi
/rekap — Generate Carousel Instagram (5 Berita Terpopuler)

<b>Monitor:</b>
/status — Lihat statistik artikel & sistem
/artikel — Lihat 5 artikel terbaru

<b>Otomasi:</b>
🤖 Bot auto-generate setiap 6 jam (berita) & 12 jam (rekomendasi)
💡 Gunakan /tulis kapan saja untuk generate manual

<b>Fallback AI:</b>
Gemini → Groq → GitHub GPT-4.1 → OpenRouter
Total kapasitas: ~1.200+ request/hari"""

    await send_message(chat_id, text)


async def cmd_status(chat_id: str):
    """Handle /status command."""
    try:
        stats = await get_stats()

        # Per-category counts
        cat_lines = []
        for cat in VALID_CATEGORIES:
            count = await get_news_count(category=cat)
            icon = CATEGORY_ICONS.get(cat, "📄")
            cat_lines.append(f"  {icon} {cat.capitalize()}: <b>{count}</b>")

        total_news = stats.get("total_news", 0)
        is_generating = bool(_running_tasks)

        text = f"""📊 <b>Status CikalNews</b>

📰 <b>Total Artikel:</b> {total_news}
{chr(10).join(cat_lines)}

⚙️ Status: {'🔄 Sedang generate...' if is_generating else '✅ Idle'}
🕐 Waktu: {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC
🤖 AI: ✅ Active (Gemini + 3 backup)"""

        await send_message(chat_id, text)

    except Exception as e:
        await send_message(chat_id, f"❌ Error getting status: {e}")


async def cmd_artikel(chat_id: str):
    """Handle /artikel - show latest articles."""
    try:
        articles = await get_news_articles(limit=5)

        if not articles:
            await send_message(chat_id, "📭 Belum ada artikel. Gunakan /tulis untuk generate.")
            return

        lines = ["📰 <b>5 Artikel Terbaru:</b>\n"]
        for i, art in enumerate(articles, 1):
            icon = CATEGORY_ICONS.get(art["category"], "📄")
            title = art["title"][:60]
            cat = art["category"]
            lines.append(f"{i}. {icon} <b>{title}</b>\n   [{cat}] — {art.get('created_at', '')[:16]}")

        await send_message(chat_id, "\n".join(lines))

    except Exception as e:
        await send_message(chat_id, f"❌ Error: {e}")


async def cmd_tulis(chat_id: str, category: Optional[str] = None):
    """Handle /tulis — trigger article generation."""
    # Lazy import to avoid circular imports
    from news_app.scheduler import run_news_pipeline

    task_key = category or "all"

    # Check if already running
    if task_key in _running_tasks:
        await send_message(chat_id, "⏳ Generate sudah berjalan, mohon tunggu...")
        return

    # Determine categories and message
    if category:
        if category not in VALID_CATEGORIES:
            await send_message(
                chat_id,
                f"❌ Kategori tidak valid: {category}\n"
                f"Gunakan: {', '.join(VALID_CATEGORIES)}",
            )
            return
        categories = [category]
        icon = CATEGORY_ICONS.get(category, "📝")
        await send_message(
            chat_id,
            f"{icon} Memulai generate berita <b>{category}</b>...\n"
            f"⏳ Mohon tunggu 2-5 menit.",
        )
    else:
        categories = None  # all
        await send_message(
            chat_id,
            "📝 Memulai generate berita <b>semua kategori</b>...\n"
            "⏳ Mohon tunggu 5-15 menit.",
        )

    # Run in background
    _running_tasks[task_key] = True

    try:
        count = 3 if category else 2
        total = await run_news_pipeline(categories=categories, articles_per_cat=count)

        # Report results
        result_text = f"""✅ <b>Generate Selesai!</b>

📰 Artikel dibuat: <b>{total}</b>
📂 Kategori: {category or 'semua'}
🕐 Selesai: {datetime.utcnow().strftime('%H:%M:%S')} UTC

Buka website untuk melihat hasilnya."""

        await send_message(chat_id, result_text)

    except Exception as e:
        logger.error(f"Generate failed: {traceback.format_exc()}")
        await send_message(
            chat_id,
            f"❌ <b>Generate gagal:</b>\n<code>{str(e)[:200]}</code>\n\n"
            f"Coba lagi dengan /tulis",
        )
    finally:
        _running_tasks.pop(task_key, None)


async def cmd_rekap(chat_id: str):
    """Handle /rekap — trigger Instagram carousel generation."""
    task_key = "rekap"
    if task_key in _running_tasks:
        await send_message(chat_id, "⏳ Generate Rekap IG sedang berjalan...")
        return

    _running_tasks[task_key] = True

    try:
        from news_app.social_generator import generate_carousel, generate_caption
        from shared.notifier import notifier
        
        await send_message(chat_id, "📸 Memulai generate Carousel Instagram...\n⏳ Mohon tunggu (proses gambar & AI copywriting).")

        articles = await get_news_articles(limit=5)
        if not articles:
            await send_message(chat_id, "📭 Belum ada artikel untuk direkap.")
            return

        slides = await generate_carousel(articles)
        caption = await generate_caption(articles)
        
        success = await notifier.send_media_group(slides, caption)
        if success:
            await send_message(chat_id, "✅ Rekap Instagram berhasil dikirim! Silakan post ke IG Anda.")
        else:
            await send_message(chat_id, "❌ Gagal mengirim gambar rekap ke Telegram.")

    except Exception as e:
        logger.error(f"Generate rekap failed: {traceback.format_exc()}")
        await send_message(chat_id, f"❌ <b>Generate Rekap gagal:</b>\n<code>{str(e)[:300]}</code>")
    finally:
        _running_tasks.pop(task_key, None)


# ── Update Handler ────────────────────────────────────────────


async def handle_update(update: dict):
    """Process incoming Telegram update (webhook)."""
    message = update.get("message")
    if not message:
        return

    chat_id = str(message.get("chat", {}).get("id", ""))
    text = (message.get("text") or "").strip()

    if not chat_id or not text:
        return

    # Only respond to authorized chat
    if CHAT_ID and chat_id != CHAT_ID:
        logger.warning(f"Unauthorized chat_id: {chat_id} (expected {CHAT_ID})")
        await send_message(chat_id, "⛔ Anda tidak memiliki akses ke bot ini.")
        return

    logger.info(f"Telegram command: {text} (from {chat_id})")

    # Route commands
    cmd = text.lower().split()[0] if text.startswith("/") else ""

    if cmd == "/start":
        await cmd_start(chat_id)

    elif cmd == "/help":
        await cmd_help(chat_id)

    elif cmd == "/status":
        await cmd_status(chat_id)

    elif cmd == "/artikel":
        await cmd_artikel(chat_id)

    elif cmd == "/rekap":
        asyncio.create_task(cmd_rekap(chat_id))

    elif cmd == "/tulis":
        # /tulis without category = all
        asyncio.create_task(cmd_tulis(chat_id, category=None))

    elif cmd.startswith("/tulis_"):
        # /tulis_bola, /tulis_teknologi, etc.
        category = cmd.replace("/tulis_", "")
        asyncio.create_task(cmd_tulis(chat_id, category=category))

    else:
        await send_message(
            chat_id,
            "🤔 Perintah tidak dikenali. Ketik /help untuk bantuan.",
        )


# ── Polling Mode (for local testing) ─────────────────────────


async def polling_loop():
    """
    Long-polling mode for local development.
    Use this instead of webhooks when testing locally.
    """
    logger.info("🔄 Telegram polling mode started")
    await delete_webhook()  # Remove webhook so polling works

    offset = 0
    while True:
        try:
            async with aiohttp.ClientSession() as session:
                params = {"offset": offset, "timeout": 30}
                async with session.get(
                    f"{API_BASE}/getUpdates", params=params,
                    timeout=aiohttp.ClientTimeout(total=35),
                ) as resp:
                    data = await resp.json()
                    updates = data.get("result", [])

                    for update in updates:
                        offset = update["update_id"] + 1
                        try:
                            await handle_update(update)
                        except Exception as e:
                            logger.error(f"Update handler error: {e}")

        except asyncio.TimeoutError:
            continue
        except asyncio.CancelledError:
            break
        except Exception as e:
            logger.error(f"Polling error: {e}")
            await asyncio.sleep(5)
