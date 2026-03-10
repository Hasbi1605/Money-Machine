import json
from typing import Dict, Any, Optional
from loguru import logger
from shared.gemini_client import gemini
from news_app.content_types import ContentType

async def extract_facts(headline: Dict, content_type: ContentType, category: str = "") -> Optional[Dict[str, Any]]:
    """
    Extract structured facts from the headline and any related sources.
    This runs before drafting, allowing us to validate if we have enough facts.
    """
    title = headline.get("title", "")
    summary = headline.get("summary", "")
    source = headline.get("source_name", "Unknown Source")
    
    sources_text = f"**Source 1 ({source}):**\\nTitle: {title}\\nSummary: {summary}\\n"
    source_count = 1
    
    related_sources = headline.get("related_sources", [])
    if related_sources:
        for i, rs in enumerate(related_sources, start=2):
            source_count += 1
            sources_text += f"---\\n**Source {i} ({rs.get('source_name', 'Unknown')}):**\\nTitle: {rs.get('title', '')}\\nSummary: {rs.get('summary', '')}\\n"

    system_instruction = """Kamu adalah Asisten Ekstraktor Fakta Jurnalistik yang sangat teliti.
Tugasmu adalah membaca teks berita mentah dan mengekstrak SEMUA fakta kunci dalam format JSON terstruktur.
SANGAT PENTING:
1. Jangan RANGKUM atau MENGARANG fakta. Hanya ektrak apa yang secara eksplisit ada di teks.
2. Setiap fakta WAJIB menyebutkan sumbernya (dari source mana fakta itu berasal).
3. Jika berupa kutipan (quote), PASTIKAN kutipan itu benar-benar ada di teks asli. Jika tidak ada, kosongkan.
4. Jika suatu data/fakta tidak ada, kosongkan (jangan mengarang)."""

    prompt = f"""Ekstrak fakta-fakta penting dari sumber-sumber berita berikut:

{sources_text}

**Tipe Konten:** {content_type.name}

Hasilkan JSON dengan format yang SANGAT KETAT sesuai panduan berikut:
{{
  "core_facts": [
    {{"fact": "Fakta utama", "sources": ["Nama Sumber 1", "Nama Sumber 2"]}}
  ],
  "entities": {{
    "people": ["Nama tokoh yang disebut"],
    "organizations": ["Nama instansi/perusahaan"],
    "locations": ["Nama tempat/negara"]
  }},
  "numbers_and_stats": [
    {{"stat": "Angka 1: konteks angka", "sources": ["Nama Sumber"]}}
  ],
  "quotes": [
    {{"speaker": "Nama tokoh", "quote": "Kutipan valid dari teks", "sources": ["Nama Sumber"]}}
  ],
  "content_type_specific": {{
     // Untuk HARD_NEWS: "what", "who", "when", "where", "why"
     // Untuk MATCH_REPORT: "team_a", "team_b", "score", "key_events" (misal pencetak gol)
     // Untuk ANALYSIS_EXPLAINER: "main_topic", "context", "implications"
     // Untuk RECOMMENDATION_ARTICLE: "products" (list of name), "pros", "cons"
  }}
}}
"""
    try:
        result = await gemini.generate_json(prompt, system_instruction=system_instruction)
        if not result:
            logger.error(f"Failed to extract facts for: {title}")
            return None
        
        # Inject metadata into result for the validators
        result["_metadata"] = {
            "source_count": source_count,
            "category": category
        }
        
        return result
    except Exception as e:
        logger.error(f"Exception during fact extraction: {e}")
        return None
