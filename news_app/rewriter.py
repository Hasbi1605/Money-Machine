"""
AI News Rewriter — takes headline + summary from scraper,
generates original Indonesian article using Gemini AI.
"""

import re
from datetime import datetime
from typing import Dict, Optional

from loguru import logger

from shared.gemini_client import gemini
from shared.config import settings


# ── Category-specific writing styles ──────────────────────────

CATEGORY_PROMPTS = {
    "bola": {
        "style": "jurnalis olahraga yang antusias dan informatif",
        "tone": "energetic, passionate, factual",
        "extra": "Gunakan istilah sepak bola yang tepat. Sertakan statistik jika relevan.",
    },
    "teknologi": {
        "style": "tech journalist yang paham teknologi dan gadget",
        "tone": "informative, analytical, forward-looking",
        "extra": "Jelaskan istilah teknis dengan bahasa yang mudah dipahami pembaca umum.",
    },
    "politik": {
        "style": "jurnalis politik internasional yang objektif dan analitis",
        "tone": "serious, balanced, analytical",
        "extra": "Berikan konteks geopolitik. Sajikan dari berbagai sudut pandang secara netral.",
    },
    "ekonomi": {
        "style": "jurnalis ekonomi dan bisnis yang analitis",
        "tone": "professional, data-driven, insightful",
        "extra": "Sertakan data/angka jika relevan. Jelaskan dampak ke masyarakat umum.",
    },
    "rekomendasi": {
        "style": "tech reviewer yang jujur dan membantu pembaca memilih produk",
        "tone": "helpful, comparative, honest",
        "extra": "Buat perbandingan yang objektif. Sebutkan kelebihan dan kekurangan.",
    },
}


async def rewrite_news(
    headline: Dict,
    category: str,
    affiliate_links: str = "",
) -> Optional[Dict]:
    """
    Rewrite a news headline into a full original article in Bahasa Indonesia.

    Args:
        headline: Dict with 'title', 'summary', 'source_url', 'source_name'
        category: Category key (bola, teknologi, politik, ekonomi, rekomendasi)
        affiliate_links: Optional affiliate link HTML to embed (for rekomendasi)

    Returns:
        Dict with 'title', 'slug', 'content' (HTML), 'excerpt', 'meta_description',
        'tags', 'category', 'thumbnail_query'
    """
    title = headline.get("title", "")
    summary = headline.get("summary", "")
    source = headline.get("source_name", "")

    cat_config = CATEGORY_PROMPTS.get(category, CATEGORY_PROMPTS["teknologi"])

    word_target = "800-1200" if category != "rekomendasi" else "1200-1800"

    affiliate_instruction = ""
    if affiliate_links and category == "rekomendasi":
        affiliate_instruction = f"""
**Integrasi Affiliate:**
Sisipkan link affiliate berikut secara natural di dalam artikel sebagai rekomendasi produk:
{affiliate_links}

Jangan terkesan memaksa/sales pitch. Berikan review yang jujur dan natural."""

    system_instruction = f"""Kamu adalah {cat_config['style']}.
Kamu menulis dalam Bahasa Indonesia yang baik dan benar.
Tone: {cat_config['tone']}.
{cat_config['extra']}"""

    prompt = f"""Berdasarkan headline berita berikut, tulis artikel berita ORIGINAL dan LENGKAP dalam Bahasa Indonesia:

**Headline:** {title}
**Ringkasan:** {summary}
**Sumber:** {source}
**Kategori:** {category}
**Target kata:** {word_target} kata

**Instruksi:**
1. JANGAN copy paste dari sumber. Tulis ulang dengan kata-kata sendiri yang ORIGINAL.
2. Buat judul yang menarik dan click-worthy (boleh berbeda dari headline asli).
3. Tulis artikel lengkap dengan:
   - Paragraf pembuka yang menarik perhatian
   - 3-5 subjudul (H2) untuk membagi konten
   - Fakta dan konteks yang relevan
   - Paragraf penutup/kesimpulan
4. Gunakan format HTML untuk konten (h2, p, strong, ul/li, blockquote).
5. JANGAN gunakan H1 (judul sudah ditangani template).
6. Tulis meta description 150-160 karakter.
7. Suggest 4-6 tags yang relevan.
8. Suggest search query untuk mencari gambar thumbnail yang relevan (dalam bahasa Inggris, untuk Pexels).
{affiliate_instruction}

**Output format JSON:**
{{
  "title": "Judul artikel yang menarik",
  "slug": "judul-artikel-url-friendly",
  "content": "<h2>...</h2><p>...</p>...",
  "excerpt": "Ringkasan 2-3 kalimat untuk preview",
  "meta_description": "Meta description 150-160 chars",
  "tags": ["tag1", "tag2", ...],
  "thumbnail_query": "english search query for relevant image",
  "word_count": 1000
}}"""

    logger.info(f"Rewriting: {title[:60]}... [{category}]")

    try:
        result = await gemini.generate_json(prompt, system_instruction=system_instruction)

        if not result or not result.get("content"):
            logger.error(f"Empty rewrite result for: {title}")
            return None

        # Ensure slug
        if not result.get("slug"):
            result["slug"] = re.sub(r"[^a-z0-9]+", "-", title.lower())[:80].strip("-")

        # Add metadata
        result["category"] = category
        result["source_title"] = title
        result["source_url"] = headline.get("source_url", "")
        result["source_name"] = source
        result["generated_at"] = datetime.utcnow().isoformat()

        word_count = result.get("word_count", len(result["content"].split()))
        logger.info(f"Article ready: '{result['title']}' (~{word_count} words)")

        return result

    except Exception as e:
        logger.error(f"Rewrite failed for '{title}': {e}")
        return None


async def generate_recommendation_article(topic: str) -> Optional[Dict]:
    """
    Generate a recommendation/review article for the 'rekomendasi' category.
    This doesn't need a news source — it generates from topic directly.
    """
    # Build affiliate links
    aff_links = []
    shopee_id = settings.affiliate.shopee_id
    alfagift_id = settings.affiliate.alfagift_id

    search_term = topic.replace(" ", "+")
    if shopee_id:
        aff_links.append(
            f'<a href="https://shopee.co.id/search?keyword={search_term}&af_id={shopee_id}" '
            f'target="_blank" rel="nofollow">Cek Harga di Shopee</a>'
        )
    if alfagift_id:
        aff_links.append(
            f'<a href="https://alfagift.id/search/{search_term}?ref={alfagift_id}" '
            f'target="_blank" rel="nofollow">Lihat di Alfagift</a>'
        )

    affiliate_html = " | ".join(aff_links) if aff_links else ""

    headline = {
        "title": topic,
        "summary": f"Artikel rekomendasi dan review tentang {topic}",
        "source_url": "",
        "source_name": "Editorial",
    }

    return await rewrite_news(
        headline=headline,
        category="rekomendasi",
        affiliate_links=affiliate_html,
    )
