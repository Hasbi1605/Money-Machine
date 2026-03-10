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
        "style": "jurnalis sepak bola yang antusias, informatif, dan paham dunia sepak bola",
        "tone": "energetic, passionate, factual",
        "extra": "Fokus HANYA pada sepak bola (football/soccer). Gunakan istilah sepak bola yang tepat (lini belakang, playmaker, clean sheet, hat-trick, dst). Sertakan statistik pertandingan, skor, klasemen, atau data transfer jika relevan. Jangan bahas olahraga lain (badminton, basket, tenis, dll).",
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

    sources_text = f"**Sumber Utama:** {source}\\n**Headline Utama:** {title}\\n**Ringkasan Utama:** {summary}\\n"
    
    related_sources = headline.get("related_sources", [])
    if related_sources:
        sources_text += "\\n**Sumber Tambahan (Fakta Tambahan dari topik yang sama):**\\n"
        for i, rs in enumerate(related_sources, start=1):
            sources_text += f"- Sumber {i} ({rs['source_name']}): {rs['title']} | Ringkasan: {rs['summary']}\\n"
            
    all_source_names = [source] + [rs['source_name'] for rs in related_sources]
    source_attribution = "Dilansir dari berbagai sumber: " + ", ".join(list(dict.fromkeys(all_source_names))) 

    prompt = f"""Berdasarkan sekumpulan headline dan ringkasan berita dari berbagai sumber yang membahas topik yang sama di bawah ini, tulis artikel berita ORIGINAL, MENDALAM, dan bernilai tambah dalam Bahasa Indonesia.

{sources_text}
**Kategori:** {category}
**Target kata:** {word_target} kata

**PROSES BERPIKIR SEBELUM MENULIS (Tuliskan ini singkat di field `thought_process`):**
1. Ambil fakta-fakta kunci eksplisit dari SEMUA sumber secara holistik.
2. Identifikasi benang merah (gabungkan fakta dari 2-4 sumber yang tersedia jika ada).
3. Buat outline fakta.
4. Tentukan sudut pandang (angle) redaksi sendiri yang lebih kaya, jangan hanya memparafrase satu media.

**STANDAR JURNALISME PROFESIONAL — WAJIB DIIKUTI:**

1. JANGAN PLAGIAT:
    - JANGAN menyalin headline, lead, atau paragraf pertama dari media sumber mana pun.
    - JANGAN menyalin kutipan panjang atau analisis opini khas media asal secara plek-ketiplek.
    - REPACKAGING TOTAL: Ceritakan ulang dengan susunan alur yang benar-benar baru dan mandiri.

2. NILAI TAMBAH (VALUE ADDED) — WAJIB ADA:
    - Ringkasan Konteks: Berikan latar belakang mengapa kejadian ini terjadi sekarang, apa kaitannya.
    - Timeline/Kronologi: Jika ini peristiwa berlanjut, berikan jejak kronologi singkat.
    - Data Pembanding: Jika ada angka/statistik, berikan skala atau perbandingan yang mudah dicerna pembaca.
    - Implikasi: Beri tahu pembaca implikasi atau dampak berita ini (What's Next?) untuk mereka atau industri.

3. STRUKTUR INVERTED PYRAMID & ATRIBUSI:
    - Paragraf 1 (Lede): Jawab 5W1H secara lugas.
    - Sebutkan sumber secara alamiah atau gabungan: "Dihimpun dari berbagai sumber," atau "Berdasarkan laporan [B] dan [C]...".
    - Sertakan kutipan langsung dari tokoh terkait (wajib gunakan tag <blockquote>).

4. FORMAT HTML WAJIB (JANGAN GANGGU STRUKTUR INI):
    - <blockquote> untuk kutipan langsung narasumber
    - <strong> untuk penekanan fakta/data krusial
    - <h2> untuk subjudul (3-5 per artikel) untuk memecah teks panjang
    - <ul>/<li> untuk daftar poin terstruktur (seperti timeline atau komparasi angka)
    - <p> untuk setiap paragraf (JANGAN digabung jadi teks panjang tanpa pemisah)
    - JANGAN menggunakan teks <h1> (karena judul page otomatis berukuran h1)
    - WAJIB Tambahkan atribusi ini di paragraf paling terakhir (copy-paste literal html teks ini): <p class="source-attribution">{source_attribution}</p>

5. AI SUMMARY:
    - Buat 3 poin ringkasan utama dan paling ringkas (masing-masing 1 kalimat) untuk "Baca 30 Detik".

6. INFOGRAPHIC:
    - Jika artikel mengandung data numerik/statistik/komparatif, buat bayangan prompt (deskriptif dalam Bahasa Inggris) untuk image generator membangun infografis.
    - Jika tidak ada data relevan, kosongkan field ini.
{affiliate_instruction}

**Output format JSON:**
{{
  "thought_process": "1. Fakta: ... 2. Outline: ... 3. Sudut pandang: ...",
  "title": "Judul artikel orisinal hasil sudut pandang redaksi baru yang menarik",
  "slug": "judul-artikel-url-friendly",
  "content": "<h2>...</h2><p>...</p><blockquote>...</blockquote>...",
  "excerpt": "Ringkasan 2-3 kalimat menarik untuk preview card",
  "meta_description": "Meta description SEO 150-160 chars",
  "tags": ["tag1", "tag2"],
  "thumbnail_query": "english search query for relevant cover image",
  "ai_summary": ["Poin penting ringkasan 1", "Poin penting ringkasan 2", "Peringatan poin ringkasan 3"],
  "infographic_prompt": "A clean minimalist infographic showing... (atau blank)",
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
        result["original_image_url"] = headline.get("original_image_url", "")
        result["generated_at"] = datetime.utcnow().isoformat()

        # Sanitize HTML to prevent broken layout (unclosed tags, missing quotes)
        from bs4 import BeautifulSoup
        if result.get("content"):
            soup = BeautifulSoup(result["content"], "html.parser")
            result["content"] = str(soup)

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
