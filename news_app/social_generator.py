"""
Social Media Generator — Auto-generates Instagram carousels and captions.
Uses Pillow to composite images and Gemini for creative copywriting.
"""

import io
import os
import textwrap
from datetime import datetime
from typing import List, Dict, Optional
import aiohttp
from PIL import Image, ImageDraw, ImageFont
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

# Brand Colors
BRAND_BG = (30, 58, 138)  # Navy Blue #1E3A8A
BRAND_TEXT = (255, 255, 255)  # White


async def fetch_image(url: str) -> Optional[Image.Image]:
    """Download an image from a URL and load it into Pillow."""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.read()
                    return Image.open(io.BytesIO(data)).convert("RGBA")
    except Exception as e:
        logger.error(f"Failed to fetch image {url}: {e}")
    return None


def wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> List[str]:
    """Wrap text to fit within a specific pixel width."""
    lines = []
    # A rough estimate for initial wrapping based on average character width
    # We refine it below
    words = text.split()
    current_line = []
    
    for word in words:
        current_line.append(word)
        # Check width of current line
        w, _ = font.getsize_multiline(" ".join(current_line)) if hasattr(font, 'getsize_multiline') else font.getbbox(" ".join(current_line))[2:]
        w = w if isinstance(w, int) else w[0]
        
        if w > max_width:
            # Word made it too long, push it to next line
            current_line.pop()
            if current_line:
                lines.append(" ".join(current_line))
            current_line = [word]

    if current_line:
        lines.append(" ".join(current_line))
    return lines


def generate_slide_image(article: Dict, index: int) -> io.BytesIO:
    """
    Generate a single Instagram 1080x1080 slide for an article.
    """
    # 1. Create Base Canvas
    img = Image.new("RGB", (1080, 1080), color=BRAND_BG)
    draw = ImageDraw.Draw(img)

    # Load Fonts
    try:
        title_font = ImageFont.truetype(FONT_BOLD, size=75)
        badge_font = ImageFont.truetype(FONT_BOLD, size=35)
        footer_font = ImageFont.truetype(FONT_REGULAR, size=25)
    except IOError:
        logger.error(f"Fonts not found in {FONTS_DIR}. Using default bitmap.")
        title_font = badge_font = footer_font = ImageFont.load_default()

    # 2. Draw "CikalNews" Badge (Top Left)
    badge_text = "CikalNews"
    draw.rectangle([60, 60, 320, 120], fill=(255, 255, 255))
    draw.text((80, 72), badge_text, font=badge_font, fill=BRAND_BG)

    # 3. Draw Category Tag
    cat_label = article.get("category", "Berita Utama").upper()
    draw.text((60, 150), cat_label, font=footer_font, fill=(200, 200, 200))

    # 4. Draw Headline Text
    title = article.get("title", "Berita Terbaru Hari Ini")
    
    # Simple text wrapping logic if PIL doesn't support getbbox well in this version
    try:
        wrapped_title = textwrap.fill(title, width=28)
    except:
        wrapped_title = title
        
    draw.multiline_text((60, 220), wrapped_title, font=title_font, fill=BRAND_TEXT, spacing=15)

    # 5. Draw Footer (Source)
    source = article.get("source_name", "Editorial")
    footer_text = f"sumber: {source} | Slide {index}"
    draw.text((60, 1020), footer_text, font=footer_font, fill=(200, 200, 200))

    return img


async def add_image_to_slide(base_img: Image.Image, image_url: str) -> None:
     # Download the article image
    if image_url:
        article_pic = await fetch_image(image_url)
        if article_pic:
             # Resize and crop to fill the bottom half (1080x540)
            target_width = 1080
            target_height = 540
            
            # Simple resize (ignoring aspect ratio cropping for simplicity in v1)
            article_pic = article_pic.resize((target_width, target_height), Image.Resampling.LANCZOS)
            
            # Paste it at the bottom
            base_img.paste(article_pic, (0, 540))

async def generate_carousel(articles: List[Dict]) -> List[io.BytesIO]:
    """Generate a list of images (slides) for the carousel."""
    slides = []
    
    # Take up to 5 articles
    for i, article in enumerate(articles[:5]):
        # Generate base slide with text
        img = generate_slide_image(article, i + 1)
        
        # Add actual image at the bottom
        img_url = article.get("thumbnail_url") or article.get("original_image_url")
        await add_image_to_slide(img, img_url)

        # Save to BytesIO for sending over Telegram
        bio = io.BytesIO()
        img.save(bio, format="PNG")
        bio.seek(0)
        bio.name = f"slide_{i+1}.png"
        slides.append(bio)

    return slides


async def generate_caption(articles: List[Dict]) -> str:
    """Use Gemini to generate a catchy Instagram caption."""
    
    summaries = []
    for i, a in enumerate(articles[:5]):
        summaries.append(f"{i+1}. {a['title']} (Sumber: {a.get('source_name', 'Editorial')})")
        
    articles_text = "\n".join(summaries)
    
    prompt = f"""Kamu adalah Social Media Manager untuk portal berita CikalNews.
Buatkan caption Instagram yang sangat menarik, interaktif, dan rapi untuk sebuah post Carousel berisi berita-berita berikut:

{articles_text}

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

