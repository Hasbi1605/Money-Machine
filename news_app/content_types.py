from enum import Enum
from typing import Dict, Any

class ContentType(Enum):
    HARD_NEWS = "HARD_NEWS"
    MATCH_REPORT = "MATCH_REPORT"
    ANALYSIS_EXPLAINER = "ANALYSIS_EXPLAINER"
    RECOMMENDATION_ARTICLE = "RECOMMENDATION_ARTICLE"

def determine_content_type(category: str, title: str) -> ContentType:
    """
    Determine the content type based on category and title keywords.
    """
    title_lower = title.lower()
    
    if category == "rekomendasi":
        return ContentType.RECOMMENDATION_ARTICLE
        
    if category == "bola":
        match_keywords = ["vs", "menang", "kalah", "imbang", "skor", "hasil pertandingan", "tekuk", "libas", "hajar", "tumbang"]
        if any(kw in title_lower for kw in match_keywords):
            return ContentType.MATCH_REPORT
            
    analysis_keywords = ["alasan", "mengapa", "fakta", "analisis", "penyebab", "dampak", "cara", "tips"]
    if any(kw in title_lower for kw in analysis_keywords):
        return ContentType.ANALYSIS_EXPLAINER
        
    return ContentType.HARD_NEWS

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
