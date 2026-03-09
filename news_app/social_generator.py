"""
Social Media Generator — Auto-generates Instagram carousels and captions.
Uses Pillow to composite images with cinematic editorial design.
Design modeled after professional news media Instagram accounts.
"""

import io
import os
from datetime import datetime
from typing import List, Dict, Optional
import aiohttp
from PIL import Image, ImageDraw, ImageFont, ImageEnhance
from loguru import logger

from shared.gemini_client import gemini
from shared.notifier import notifier
from shared.database import get_news_articles

# Paths
BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ASSETS_DIR = os.path.join(BASE_DIR, "news_app", "assets")
FONTS_DIR = os.path.join(ASSETS_DIR, "fonts")
FONT_BOLD = os.path.join(FONTS_DIR, "Inter-Bold.ttf")
FONT_REGULAR = os.path.join(FONTS_DIR, "Inter-Regular.ttf")

# Design
CANVAS = 1080
PAD = 70
CAT_COLORS = {
    "bola": (34, 197, 94),
    "teknologi": (59, 130, 246),
    "politik": (168, 85, 247),
    "ekonomi": (245, 158, 11),
    "rekomendasi": (236, 72, 153),
}


async def fetch_image(url: str) -> Optional[Image.Image]:
    """Download an image from a URL."""
    if not url:
        return None
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7)"}
        async with aiohttp.ClientSession(headers=headers) as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=15)) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    return Image.open(io.BytesIO(data)).convert("RGBA")
    except Exception as e:
        logger.error(f"Failed to fetch image {url}: {e}")
    return None


def _load_fonts():
    """Load font files."""
    try:
        return {
            "logo": ImageFont.truetype(FONT_BOLD, 52),
            "cat": ImageFont.truetype(FONT_BOLD, 20),
            "headline": ImageFont.truetype(FONT_BOLD, 62),
            "swipe": ImageFont.truetype(FONT_REGULAR, 22),
            "cover_logo": ImageFont.truetype(FONT_BOLD, 80),
            "cover_sub": ImageFont.truetype(FONT_REGULAR, 30),
            "cover_item": ImageFont.truetype(FONT_REGULAR, 22),
            "cover_num": ImageFont.truetype(FONT_BOLD, 30),
        }
    except IOError:
        d = ImageFont.load_default()
        return {k: d for k in ["logo", "cat", "headline", "swipe",
                                "cover_logo", "cover_sub", "cover_item", "cover_num"]}


def _wrap(text: str, font, max_w: int) -> List[str]:
    """Wrap text to fit pixel width."""
    words, lines, cur = text.split(), [], []
    for w in words:
        test = " ".join(cur + [w])
        bb = font.getbbox(test)
        if (bb[2] - bb[0]) > max_w and cur:
            lines.append(" ".join(cur))
            cur = [w]
        else:
            cur.append(w)
    if cur:
        lines.append(" ".join(cur))
    return lines


def _gradient(size: int, top_a: int = 0, bot_a: int = 240) -> Image.Image:
    """Create vertical gradient efficiently via 1px column."""
    col = Image.new("RGBA", (1, size))
    for y in range(size):
        t = y / size
        a = int(top_a + (bot_a - top_a) * t)
        col.putpixel((0, y), (0, 0, 0, a))
    return col.resize((size, size), Image.Resampling.NEAREST)


def _dark_bg(size: int) -> Image.Image:
    """Dark gradient background for cover / fallback."""
    col = Image.new("RGBA", (1, size))
    for y in range(size):
        t = y / size
        r = int(18 + 8 * t)
        g = int(18 + 12 * t)
        b = int(24 + 30 * t)
        col.putpixel((0, y), (r, g, b, 255))
    return col.resize((size, size), Image.Resampling.NEAREST)


# ── Cover Slide ───────────────────────────────────────────────

def generate_cover_slide(articles: List[Dict], fonts: dict) -> Image.Image:
    """Cover slide: branding + article list."""
    img = _dark_bg(CANVAS)
    draw = ImageDraw.Draw(img)

    # Top accent bar
    draw.rectangle([0, 0, CANVAS, 5], fill=(220, 38, 38))

    # Big logo
    logo = "CikalNews."
    bb = fonts["cover_logo"].getbbox(logo)
    draw.text((PAD, CANVAS // 2 - 200), logo, font=fonts["cover_logo"], fill=(255, 255, 255))

    # Subtitle with date
    today = datetime.now().strftime("%d %B %Y")
    draw.text((PAD, CANVAS // 2 - 95), f"Rekap Berita — {today}",
              font=fonts["cover_sub"], fill=(160, 160, 175))

    # Separator
    draw.line([(PAD, CANVAS // 2 - 40), (CANVAS - PAD, CANVAS // 2 - 40)],
              fill=(50, 50, 65), width=2)

    # Article list
    y = CANVAS // 2 - 10
    for i, a in enumerate(articles[:5]):
        t = a.get("title", "")
        if len(t) > 52:
            t = t[:49] + "..."
        cat = a.get("category", "")
        cc = CAT_COLORS.get(cat, (120, 120, 140))
        draw.text((PAD, y), f"0{i+1}", font=fonts["cover_num"], fill=cc)
        draw.text((PAD + 55, y + 5), t, font=fonts["cover_item"], fill=(200, 200, 215))
        y += 55

    # CTA
    draw.text((PAD, CANVAS - PAD - 35), "Swipe untuk baca headline →",
              font=fonts["swipe"], fill=(100, 100, 120))

    return img.convert("RGB")


# ── Article Slide ─────────────────────────────────────────────

def generate_article_slide(article: Dict, bg_image: Optional[Image.Image],
                           index: int, total: int, fonts: dict) -> Image.Image:
    """Single article slide: full-bleed photo + gradient + headline."""
    cat = article.get("category", "berita")

    # Background
    if bg_image:
        bg = bg_image.convert("RGBA")
        w, h = bg.size
        scale = max(CANVAS / w, CANVAS / h)
        bg = bg.resize((int(w * scale), int(h * scale)), Image.Resampling.LANCZOS)
        nw, nh = bg.size
        bg = bg.crop(((nw - CANVAS) // 2, (nh - CANVAS) // 2,
                      (nw + CANVAS) // 2, (nh + CANVAS) // 2))
        bg = ImageEnhance.Brightness(bg).enhance(0.7)
        img = bg.copy()
    else:
        img = _dark_bg(CANVAS)

    # Strong cinematic gradient
    grad = _gradient(CANVAS, top_a=0, bot_a=245)
    img = Image.alpha_composite(img.convert("RGBA"), grad)
    draw = ImageDraw.Draw(img)

    # ── Logo (top-left, large bold text, no background pill) ──
    logo = "CikalNews."
    draw.text((PAD, PAD - 10), logo, font=fonts["logo"], fill=(255, 255, 255))

    # ── Category pill (outline style, below logo) ──
    cat_label = cat.upper()
    bb = fonts["cat"].getbbox(cat_label)
    tw, th = bb[2] - bb[0], bb[3] - bb[1]
    px, py = 18, 10
    pill_x, pill_y = PAD, PAD + 70
    draw.rounded_rectangle(
        [pill_x, pill_y, pill_x + tw + px * 2, pill_y + th + py * 2],
        radius=20,
        outline=(255, 255, 255, 200),
        width=2,
    )
    draw.text((pill_x + px, pill_y + py), cat_label,
              font=fonts["cat"], fill=(255, 255, 255))

    # ── Headline (bottom, big bold white text) ──
    title = article.get("title", "Berita Terbaru")
    max_w = CANVAS - PAD * 2
    lines = _wrap(title, fonts["headline"], max_w)
    if len(lines) > 4:
        lines = lines[:4]
        lines[-1] = lines[-1][:-3] + "..."

    line_h = 78
    # Position from bottom: swipe text area + gap + text block
    text_block_h = len(lines) * line_h
    ty = CANVAS - PAD - 80 - text_block_h

    for ln in lines:
        draw.text((PAD, ty), ln, font=fonts["headline"], fill=(255, 255, 255))
        ty += line_h

    # ── Thin separator line ──
    sep_y = CANVAS - PAD - 55
    draw.line([(PAD, sep_y), (PAD + 280, sep_y)], fill=(255, 255, 255, 100), width=1)

    # ── Swipe CTA (bottom-left) ──
    draw.text((PAD, CANVAS - PAD - 38),
              "Swipe untuk headline selanjutnya →",
              font=fonts["swipe"], fill=(160, 160, 175))

    # ── Small star accent (bottom-right) ──
    star_x, star_y = CANVAS - PAD - 15, CANVAS - PAD - 30
    draw.text((star_x, star_y), "✦", font=fonts["swipe"], fill=(255, 255, 255, 180))

    return img.convert("RGB")


# ── Pipeline ──────────────────────────────────────────────────

async def generate_carousel(articles: List[Dict]) -> List[io.BytesIO]:
    """Generate carousel slides."""
    fonts = _load_fonts()
    slides = []
    arts = articles[:5]
    total = len(arts)

    # Cover
    cover = generate_cover_slide(arts, fonts)
    bio = io.BytesIO()
    cover.save(bio, format="PNG")
    bio.seek(0)
    bio.name = "slide_cover.png"
    slides.append(bio)

    # Article slides
    for i, a in enumerate(arts):
        url = a.get("thumbnail_url") or a.get("original_image_url")
        bg = await fetch_image(url) if url else None
        img = generate_article_slide(a, bg, i + 1, total, fonts)
        bio = io.BytesIO()
        img.save(bio, format="PNG")
        bio.seek(0)
        bio.name = f"slide_{i+1}.png"
        slides.append(bio)

    return slides


async def generate_caption(articles: List[Dict]) -> str:
    """Use Gemini to generate Instagram caption."""
    summaries = [f"{i+1}. {a['title']} (Sumber: {a.get('source_name', 'Editorial')})"
                 for i, a in enumerate(articles[:5])]

    prompt = f"""Kamu adalah Social Media Manager untuk portal berita CikalNews.
Buatkan caption Instagram yang sangat menarik, interaktif, dan rapi untuk sebuah post Carousel berisi berita-berita berikut:

{chr(10).join(summaries)}

Aturan Caption:
1. Mulai dengan kalimat pembuka sapaan sore/malam atau "Rekap Berita Hari Ini".
2. Sebutkan ke-5 berita di atas secara singkat & padat (gunakan bullet points/emoji).
3. Tambahkan Call-to-Action (CTA) mengajak audiens baca lengkapnya di cikalnews.com atau kasih pendapat di kolom komentar.
4. Sertakan sumber (gabungan dari sumber-sumber di atas).
5. Tambahkan 5-8 hashtag populer dan relevan (#BeritaTerkini #CikalNews dll).
6. Gunakan gaya bahasa yang santai tapi profesional ala ShiftMedia/Folkative.

Output langsung captionnya saja."""

    try:
        caption = await gemini.generate_text(prompt)
        return caption if caption else "Rekap Berita CikalNews hari ini! Baca selengkapnya di website. #CikalNews"
    except Exception as e:
        logger.error(f"Failed to generate caption: {e}")
        return "Rekap Berita CikalNews hari ini! Baca selengkapnya di website. #CikalNews"
