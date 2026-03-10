from enum import Enum
from typing import Dict, Any, Tuple

class ContentType(Enum):
    HARD_NEWS = "HARD_NEWS"
    MATCH_REPORT = "MATCH_REPORT"
    ANALYSIS_EXPLAINER = "ANALYSIS_EXPLAINER"
    RECOMMENDATION_ARTICLE = "RECOMMENDATION_ARTICLE"

from shared.gemini_client import gemini
from loguru import logger
import json

async def determine_content_type(category: str, title: str, summary: str = "") -> Tuple[ContentType, float]:
    """
    Determine the content type with an LLM based on category, title, and summary.
    Returns (ContentType, confidence_score).
    If confidence < 0.6, falls back to HARD_NEWS.
    """
    if category == "rekomendasi":
        return ContentType.RECOMMENDATION_ARTICLE, 1.0
        
    prompt = f"""Tentukan kategori jurnalistik paling tepat untuk berita berikut.
    Judul: {title}
    Ringkasan: {summary}
    Kategori Utama: {category}
    
    Pilih SATU dari Content Type berikut:
    - HARD_NEWS: Berita faktual umum, kejadian singkat, peristiwa, kriminalitas, dll.
    - MATCH_REPORT: Laporan hasil pertandingan olahraga (wajib ada unsur menang/kalah/skor antara dua tim).
    - ANALYSIS_EXPLAINER: Analisis mendalam, opini, ulasan pakar, fakta-dan-data, tips/trik mendalam.
    
    Berikan confidence_score (0.0 - 1.0) seberapa yakin Anda dengan tipe tersebut.
    
    Output JSON STRICT:
    {{"content_type": "HARD_NEWS|MATCH_REPORT|ANALYSIS_EXPLAINER", "confidence_score": 0.9}}
    """
    
    try:
        response = await gemini.generate_json(prompt, system_instruction="Kamu jurnalis senior yang ahli mengklasifikasikan jenis artikel.")
        if response and response.get("content_type") and response.get("confidence_score") is not None:
            c_str = response["content_type"]
            score = float(response["confidence_score"])
            
            ct = ContentType.HARD_NEWS
            try:
                ct = ContentType(c_str)
            except ValueError:
                ct = ContentType.HARD_NEWS
                
            if score < 0.6:
                logger.warning(f"Low classifier confidence ({score}) for {title}. Falling back to HARD_NEWS.")
                return ContentType.HARD_NEWS, score
                
            return ct, score
    except Exception as e:
        logger.error(f"Classification failed for {title}: {e}")
        
    return ContentType.HARD_NEWS, 0.0

def get_content_type_rules(content_type: ContentType) -> Dict[str, Any]:
    """
    Get the editorial rules and validation requirements for a specific content type.
    """
    rules = {
        ContentType.HARD_NEWS: {
            "required_fields": ["who", "what", "when", "where"],
            "description": "Short, factual news reporting.",
            "word_target": "500-800",
        },
        ContentType.MATCH_REPORT: {
            "required_fields": ["team_a", "team_b", "score", "match_context"],
            "description": "Concrete match facts including scores, teams, and key events.",
            "word_target": "600-900",
        },
        ContentType.ANALYSIS_EXPLAINER: {
            "required_fields": ["main_topic", "context", "implications"],
            "description": "Deep dive analysis or explainer with clear labeling.",
            "word_target": "800-1200",
        },
        ContentType.RECOMMENDATION_ARTICLE: {
            "required_fields": ["products", "pros", "cons"],
            "description": "Utility-first, objective comparison or recommendation.",
            "word_target": "1200-1800",
        }
    }
    return rules.get(content_type, rules[ContentType.HARD_NEWS])
