"""
Social Content Generator — generates visual posts + captions
for Instagram, TikTok, and WhatsApp Channel.

Uses:
  - Gemini for caption/text generation
  - Pexels for high-quality stock images
  - Pillow for image + text overlay (quote cards / info slides)
"""

import asyncio
import json
import os
import random
import textwrap
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import aiohttp
from loguru import logger
from PIL import Image, ImageDraw, ImageFont, ImageFilter

from shared.config import settings
from shared.gemini_client import gemini


# ── Pexels helper ──────────────────────────────────────────────

async def search_pexels_image(
    query: str,
    orientation: str = "portrait",  # portrait=IG/TikTok, landscape=WA
    per_page: int = 15,
) -> Optional[str]:
    """Return a random image URL from Pexels matching *query*."""
    api_key = settings.pexels.api_key
    if not api_key:
        logger.warning("Pexels API key not set")
        return None

    headers = {"Authorization": api_key}
    params = {"query": query, "per_page": per_page, "orientation": orientation}

    try:
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(
                "https://api.pexels.com/v1/search", params=params
            ) as resp:
                if resp.status != 200:
                    logger.error(f"Pexels API error: {resp.status}")
                    return None
                data = await resp.json()
                photos = data.get("photos", [])
                if not photos:
                    return None
                photo = random.choice(photos)
                # "large" ≈ 940px wide — good enough for social
                return photo.get("src", {}).get("large") or photo["src"]["original"]
    except Exception as e:
        logger.error(f"Pexels search failed: {e}")
        return None


async def download_image(url: str, dest: Path) -> Optional[Path]:
    """Download an image from *url* to *dest*."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as resp:
                if resp.status == 200:
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    with open(dest, "wb") as f:
                        async for chunk in resp.content.iter_chunked(8192):
                            f.write(chunk)
                    return dest
    except Exception as e:
        logger.error(f"Image download failed: {e}")
    return None


# ── Font helpers ───────────────────────────────────────────────

def _find_font(bold: bool = True) -> str:
    """Find a usable system font."""
    import platform

    candidates: list[str] = []
    if platform.system() == "Darwin":
        candidates = [
            "/System/Library/Fonts/Supplemental/Arial Bold.ttf" if bold
            else "/Library/Fonts/Arial.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "/Library/Fonts/Arial.ttf",
        ]
    elif platform.system() == "Linux":
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        ]
    else:
        candidates = ["C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/arial.ttf"]

    for f in candidates:
        if os.path.exists(f):
            return f
    return candidates[0]


FONT_BOLD = _find_font(bold=True)
FONT_REGULAR = _find_font(bold=False)


# ── Image creation ─────────────────────────────────────────────

def create_quote_card(
    text: str,
    bg_image_path: Optional[Path] = None,
    size: Tuple[int, int] = (1080, 1080),
    text_color: str = "white",
    brand: str = "@cikaltutorial",
) -> Image.Image:
    """
    Create a visually attractive quote/info card image.

    - Uses *bg_image_path* as background (blurred overlay), or gradient.
    - Renders *text* centered with word-wrap.
    """
    w, h = size

    if bg_image_path and bg_image_path.exists():
        bg = Image.open(bg_image_path).convert("RGB")
        bg = bg.resize(size, Image.LANCZOS)
        bg = bg.filter(ImageFilter.GaussianBlur(radius=6))
        # Darken overlay
        overlay = Image.new("RGBA", size, (0, 0, 0, 140))
        bg = bg.convert("RGBA")
        bg = Image.alpha_composite(bg, overlay)
        img = bg.convert("RGB")
    else:
        # Gradient background
        img = Image.new("RGB", size, (20, 20, 40))
        draw_grad = ImageDraw.Draw(img)
        for y in range(h):
            ratio = y / h
            r = int(20 + 30 * ratio)
            g = int(20 + 10 * ratio)
            b = int(40 + 60 * ratio)
            draw_grad.line([(0, y), (w, y)], fill=(r, g, b))

    draw = ImageDraw.Draw(img)

    # Main text
    try:
        font_main = ImageFont.truetype(FONT_BOLD, 48)
    except Exception:
        font_main = ImageFont.load_default()

    try:
        font_brand = ImageFont.truetype(FONT_REGULAR, 28)
    except Exception:
        font_brand = ImageFont.load_default()

    # Word-wrap
    max_chars = 28
    lines = textwrap.wrap(text, width=max_chars)
    line_height = 64
    total_text_h = line_height * len(lines)
    y_start = (h - total_text_h) // 2

    for i, line in enumerate(lines):
        bbox = draw.textbbox((0, 0), line, font=font_main)
        tw = bbox[2] - bbox[0]
        x = (w - tw) // 2
        y = y_start + i * line_height

        # Shadow
        draw.text((x + 2, y + 2), line, fill="black", font=font_main)
        draw.text((x, y), line, fill=text_color, font=font_main)

    # Brand watermark bottom-right
    draw.text((w - 250, h - 50), brand, fill=(200, 200, 200, 180), font=font_brand)

    return img


# ── Content niches ─────────────────────────────────────────────

SOCIAL_NICHES = {
    "id": [
        {"niche": "motivasi", "topics": [
            "kata-kata motivasi kerja",
            "quotes semangat hidup",
            "tips sukses anak muda",
            "mindset orang kaya",
        ]},
        {"niche": "teknologi", "topics": [
            "tips smartphone terbaru",
            "aplikasi wajib punya",
            "AI tools gratis terbaik",
            "trik hemat kuota internet",
        ]},
        {"niche": "keuangan", "topics": [
            "tips menabung untuk pemula",
            "cara investasi dari nol",
            "kesalahan keuangan generasi muda",
            "passive income dari HP",
        ]},
        {"niche": "fakta_unik", "topics": [
            "fakta unik yang jarang diketahui",
            "hal aneh di dunia",
            "rekor dunia mengejutkan",
        ]},
        {"niche": "tutorial", "topics": [
            "tutorial editing foto HP",
            "cara buat konten viral",
            "tips jualan online laris",
        ]},
    ],
    "en": [
        {"niche": "motivation", "topics": [
            "success mindset quotes",
            "productivity hacks",
            "morning routine tips",
        ]},
        {"niche": "tech_tips", "topics": [
            "best free AI tools",
            "smartphone hidden features",
            "apps to boost productivity",
        ]},
        {"niche": "finance", "topics": [
            "passive income ideas",
            "money saving tips",
            "investing for beginners",
        ]},
    ],
}


# ── Main generator ─────────────────────────────────────────────

async def generate_social_post(
    language: str = "id",
    niche: Optional[str] = None,
    topic: Optional[str] = None,
    platforms: Optional[List[str]] = None,
) -> Dict:
    """
    Generate a complete social media post:
      - Image (quote card with stock photo background)
      - Caption per platform (IG, TikTok, WA)
      - Hashtags

    Returns dict with keys: title, image_path, captions, hashtags, niche, topic
    """
    if platforms is None:
        platforms = ["instagram", "tiktok", "whatsapp"]

    niches = SOCIAL_NICHES.get(language, SOCIAL_NICHES["id"])
    if not niche:
        sel = random.choice(niches)
        niche = sel["niche"]
    else:
        sel = next((n for n in niches if n["niche"] == niche), random.choice(niches))

    if not topic:
        topic = random.choice(sel["topics"])

    lang_name = "Indonesian (Bahasa Indonesia)" if language == "id" else "English"

    # ── Step 1: Ask Gemini for content ──
    prompt = f"""Buatkan satu konten sosial media viral tentang: "{topic}"

Bahasa: {lang_name}
Niche: {niche}

Hasilkan dalam JSON dengan field berikut:
- headline: teks utama yang pendek & impactful untuk ditampilkan di gambar (max 60 karakter)
- image_query: kata kunci pencarian gambar stock/Pexels yang relevan (English)
- captions: object {{
    "instagram": caption panjang 150-300 kata, storytelling, CTA, 15-20 hashtag populer di akhir,
    "tiktok": caption pendek max 150 karakter + 5-7 hashtag viral,
    "whatsapp": teks informatif 100-200 kata cocok untuk broadcast/saluran WA, tanpa hashtag
  }}
- tags: array 10 hashtag relevan tanpa '#'
- cta: call-to-action singkat (e.g. "Save & Share!")
"""

    logger.info(f"Generating social post: '{topic}' ({language})")
    content = await gemini.generate_json(prompt)

    if not content or not content.get("headline"):
        logger.error("Content generation returned empty")
        return {}

    headline = content.get("headline", topic)
    image_query = content.get("image_query", topic)

    # ── Step 2: Get background image from Pexels ──
    img_url = await search_pexels_image(image_query, orientation="portrait")
    bg_path: Optional[Path] = None
    if img_url:
        bg_path = settings.output_dir / "social" / "temp_bg.jpg"
        bg_path = await download_image(img_url, bg_path)

    # ── Step 3: Create quote card image ──
    card = create_quote_card(
        text=headline,
        bg_image_path=bg_path,
        size=(1080, 1080),  # Square — works for IG, TikTok, WA
    )

    ts = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    slug = headline.lower().replace(" ", "_")[:30]
    image_name = f"{slug}_{language}_{ts}.png"
    image_dir = settings.output_dir / "social"
    image_dir.mkdir(parents=True, exist_ok=True)
    image_path = image_dir / image_name
    card.save(str(image_path), "PNG", quality=95)
    logger.info(f"Quote card saved: {image_path}")

    # Cleanup temp bg
    if bg_path and bg_path.exists() and bg_path.name == "temp_bg.jpg":
        bg_path.unlink(missing_ok=True)

    captions = content.get("captions", {})
    tags = content.get("tags", [])

    result = {
        "title": headline,
        "topic": topic,
        "niche": niche,
        "language": language,
        "image_path": str(image_path),
        "captions": captions,
        "hashtags": tags,
        "cta": content.get("cta", ""),
    }

    # ── Step 4: Save caption files alongside image ──
    for platform in platforms:
        cap = captions.get(platform, "")
        if cap:
            cap_path = image_dir / f"{slug}_{language}_{ts}_{platform}.txt"
            cap_path.write_text(cap, encoding="utf-8")

    logger.info(
        f"Social post ready: '{headline}' → {len(platforms)} platforms, "
        f"image {image_path.stat().st_size / 1024:.0f} KB"
    )
    return result
