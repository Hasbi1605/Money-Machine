import json
from enum import Enum
from typing import Dict, Any
from news_app.content_types import ContentType

class TemplateKeys(Enum):
    SYSTEM_INSTRUCTION = "SYSTEM_INSTRUCTION"
    USER_PROMPT = "USER_PROMPT"

def get_drafting_prompt(content_type: ContentType, category_style: Dict[str, str], extracted_facts: Dict[str, Any], affiliate_links: str = "") -> Dict[TemplateKeys, str]:
    """
    Generate the prompt for drafting an article based on the content type and extracted facts.
    """
    system_instruction = f"""Kamu adalah {category_style['style']}.
Kamu menulis dalam Bahasa Indonesia yang baik dan benar.
Tone: {category_style['tone']}.
{category_style['extra']}"""

    word_target = "800-1200" if content_type != ContentType.RECOMMENDATION_ARTICLE else "1200-1800"
    
    affiliate_instruction = ""
    if affiliate_links and content_type == ContentType.RECOMMENDATION_ARTICLE:
        affiliate_instruction = f"""
**Integrasi Affiliate:**
Sisipkan link affiliate berikut secara natural di dalam artikel sebagai rekomendasi produk:
{affiliate_links}

Jangan terkesan memaksa/sales pitch. Berikan review yang jujur dan natural."""

    user_prompt = f"""Berdasarkan sekumpulan FAKTA yang telah diekstrak di bawah ini, tulis artikel berita ORIGINAL, MENDALAM, dan bernilai tambah dalam Bahasa Indonesia.
    
**FAKTA YANG TERSEDIA:**
{json.dumps(extracted_facts, indent=2, ensure_ascii=False)}

**Tipe Konten:** {content_type.name}
**Target kata:** {word_target} kata

**PROSES BERPIKIR SEBELUM MENULIS (Tuliskan ini singkat di field `thought_process`):**
1. Review semua fakta.
2. Identifikasi benang merah.
3. Buat outline fakta.
4. Tentukan sudut pandang (angle) redaksi sendiri yang lebih kaya.

**STANDAR JURNALISME PROFESIONAL — WAJIB DIIKUTI:**

1. JANGAN PLAGIAT:
    - JANGAN menyalin headline, lead, atau paragraf pertama dari media sumber mana pun.
    - REPACKAGING TOTAL: Ceritakan ulang dengan susunan alur yang benar-benar baru dan mandiri.

2. NILAI TAMBAH (VALUE ADDED) — WAJIB ADA:
    - Ringkasan Konteks: Berikan latar belakang mengapa kejadian ini terjadi sekarang, apa kaitannya.
    - Timeline/Kronologi: Jika ini peristiwa berlanjut, berikan jejak kronologi singkat.
    - Data Pembanding: Jika ada angka/statistik, berikan skala atau perbandingan yang mudah dicerna pembaca.
    - Implikasi: Beri tahu pembaca implikasi atau dampak berita ini (What's Next?) untuk mereka atau industri.

3. STRUKTUR INVERTED PYRAMID & ATRIBUSI:
    - Paragraf 1 (Lede): Jawab 5W1H secara lugas.
    - Sebutkan sumber secara alamiah atau gabungan: "Dihimpun dari berbagai sumber,".
    - Sertakan kutipan langsung dari tokoh terkait (wajib gunakan tag <blockquote>).

4. FORMAT HTML WAJIB (JANGAN GANGGU STRUKTUR INI):
    - <blockquote> untuk kutipan langsung narasumber
    - <strong> untuk penekanan fakta/data krusial
    - <h2> untuk subjudul (3-5 per artikel) untuk memecah teks panjang
    - <ul>/<li> untuk daftar poin terstruktur (seperti timeline atau komparasi angka)
    - <p> untuk setiap paragraf (JANGAN digabung jadi teks panjang tanpa pemisah)
    - JANGAN menggunakan teks <h1> (karena judul page otomatis berukuran h1)
    - WAJIB Tambahkan atribusi ini di paragraf paling terakhir: <p class="source-attribution">Dihimpun dari berbagai sumber peliputan utama.</p>

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

    return {
        TemplateKeys.SYSTEM_INSTRUCTION: system_instruction,
        TemplateKeys.USER_PROMPT: user_prompt
    }

def get_revision_prompt(previous_draft: str, validation_reasons: list[str]) -> str:
    """
    Generate the prompt for revising a draft that failed QC.
    """
    reasons_str = "\\n- ".join(validation_reasons)
    prompt = f"""Draft artikel sebelumnya belum memenuhi standar kualitas redaksional.
    
**DRAFT SEBELUMNYA:**
{previous_draft}

**ALASAN PENOLAKAN / KEKURANGAN YANG HARUS DIPERBAIKI:**
- {reasons_str}

Tolong perbaiki draft tersebut agar memenuhi SEMUA standar kualiatas, terutama memperbaiki masalah-masalah di atas.
Pastikan tidak ada placeholder (seperti [Nama], XXX, dll).
Pastikan format HTML utuh (<p>, <h2>, <blockquote>, dll).

Kembalikan menggunakan format JSON yang sama seperti draft aslinya.
"""
    return prompt
