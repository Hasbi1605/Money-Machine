"""Set Telegram bot commands menu."""
import asyncio
import aiohttp
import sys
sys.path.insert(0, ".")
from shared.config import settings

API = f"https://api.telegram.org/bot{settings.telegram.bot_token}"

async def main():
    commands = [
        {"command": "start", "description": "Mulai & info bot"},
        {"command": "tulis", "description": "Generate berita semua kategori"},
        {"command": "tulis_bola", "description": "Generate berita bola"},
        {"command": "tulis_teknologi", "description": "Generate berita teknologi"},
        {"command": "tulis_politik", "description": "Generate berita politik"},
        {"command": "tulis_ekonomi", "description": "Generate berita ekonomi"},
        {"command": "tulis_rekomendasi", "description": "Generate artikel rekomendasi"},
        {"command": "status", "description": "Status sistem & statistik"},
        {"command": "artikel", "description": "Artikel terbaru"},
        {"command": "help", "description": "Daftar perintah"},
    ]
    async with aiohttp.ClientSession() as s:
        async with s.post(f"{API}/setMyCommands", json={"commands": commands}) as r:
            data = await r.json()
            print(f"setMyCommands: {data}")

asyncio.run(main())
