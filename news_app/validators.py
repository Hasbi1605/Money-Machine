import re
from typing import Dict, Any, Tuple
from loguru import logger
from news_app.content_types import ContentType
from news_app.quote_policy import enforce_quote_integrity

class ValidationResult:
    def __init__(self, is_valid: bool, status: str, reasons: list[str]):
        """
        status: APPROVED, NEEDS_REVISION, BLOCKED
        """
        self.is_valid = is_valid
        self.status = status
        self.reasons = reasons

def validate_extracted_facts(facts: Dict[str, Any], content_type: ContentType) -> ValidationResult:
    """
    Validate that the extracted facts are sufficient to write an article.
    Enforces strict hard gates per ContentType.
    """
    reasons = []
    
    if not facts:
        return ValidationResult(False, "BLOCKED", ["Missing facts extraction entirely."])
        
    core_facts = facts.get("core_facts", [])
    if not core_facts or len(core_facts) == 0:
        reasons.append("No core facts extracted from sources.")
        
    ct_specific = facts.get("content_type_specific", {})
    
    if content_type == ContentType.MATCH_REPORT:
        team_a = ct_specific.get("team_a")
        team_b = ct_specific.get("team_b")
        score = ct_specific.get("score")
        if not team_a or not team_b or not score:
            reasons.append("MATCH_REPORT is missing critical facts: team_a, team_b, or score.")
            
    elif content_type == ContentType.HARD_NEWS:
        what = ct_specific.get("what")
        who = ct_specific.get("who")
        when = ct_specific.get("when", "")
        if not what or not who or not when:
            reasons.append("HARD_NEWS is missing minimum viable facts: who, what, or when.")
            
    elif content_type == ContentType.ANALYSIS_EXPLAINER:
        analysis_points = ct_specific.get("analysis_points", [])
        if not analysis_points:
            reasons.append("ANALYSIS_EXPLAINER missing clear analysis_points.")
            
    elif content_type == ContentType.RECOMMENDATION_ARTICLE:
        products = ct_specific.get("products", [])
        if not products:
            reasons.append("RECOMMENDATION_ARTICLE missing product identities/specs.")
            
    if reasons:
        return ValidationResult(False, "BLOCKED", reasons)
        
    return ValidationResult(True, "APPROVED", [])

def check_filler_and_repetition(content: str) -> list[str]:
    """
    Heuristic checks for LLM filler, repetition, and low-information text.
    Includes paragraph-level fact density checks.
    """
    from bs4 import BeautifulSoup
    reasons = []
    content_lower = content.lower()
    
    # Common LLM platitudes
    filler_phrases = [
        "kesimpulannya", "pada akhirnya", "dalam lanskap modern",
        "tidak dapat dipungkiri bahwa", "di era digital ini",
        "seperti yang kita ketahui bersama", "merupakan hal yang penting",
        "menjadi sorotan", "tidak bisa dipungkiri"
    ]
    
    count_fillers = sum(1 for p in filler_phrases if p in content_lower)
    if count_fillers > 2:
        reasons.append("Too many generic filler phrases detected (e.g. 'di era digital ini').")
        
    # Check for paragraph repetition and Fact-Density
    soup = BeautifulSoup(content, "html.parser")
    paragraphs = soup.find_all('p')
    
    seen_sentences = set()
    low_density_paragraphs = 0
    
    for p in paragraphs:
        text = p.get_text(separator=' ').strip()
        if not text:
            continue
            
        # Repetition check
        sentences = re.split(r'(?<=[.!?]) +', text.lower())
        for s in sentences:
            s_clean = s.strip()
            if len(s_clean.split()) > 5:
                if s_clean in seen_sentences:
                    reasons.append("Repetitive sentence detected.")
                    break
                seen_sentences.add(s_clean)
                
        # Density check: Count numbers and capitalized words (rough entity heuristic)
        words = text.split()
        if len(words) > 15:
            # entities: Starts with upper case, or is a digit
            entities = [w for w in words if w[0].isupper() or any(c.isdigit() for c in w)]
            density = len(entities) / len(words)
            if density < 0.08: # less than 8% entities in a long paragraph -> likely fluff
                low_density_paragraphs += 1

    if len(paragraphs) > 2 and low_density_paragraphs > len(paragraphs) * 0.4:
        reasons.append("Fact density is too low. High amount of fluff/filler paragraphs detected. Please compress and stick to facts.")
                
    return reasons

def validate_draft(draft: Dict[str, Any], content_type: ContentType, facts: Dict[str, Any] = None) -> ValidationResult:
    """
    Validate the generated draft against strict editorial rules.
    Runs AFTER drafting.
    Returns APPROVED, NEEDS_REVISION, or BLOCKED.
    """
    reasons_blocked = []
    reasons_revision = []
    
    if not draft or not draft.get("content"):
        return ValidationResult(False, "BLOCKED", ["Draft content is empty."])
        
    content = draft.get("content", "")
    content_lower = content.lower()
    
    # 1. Hard Block on Placeholders
    placeholders = [r"\[nama\]", r"\[tanggal\]", r"\[jumlah\]", r"\btbd\b", r"\bxxx\b", r"lorem ipsum"]
    for ph in placeholders:
        if re.search(ph, content_lower):
            reasons_blocked.append(f"Contains placeholder: {ph}")
            break
            
    # 2. Hard Block on structure
    if "<p>" not in content:
        reasons_blocked.append("Missing required HTML structure: <p>")
        
    if "<h2>" not in content and content_type != ContentType.HARD_NEWS:
        reasons_revision.append("Missing required HTML structure: <h2>")
        
    # 3. Content Type specific validations
    if content_type == ContentType.MATCH_REPORT:
        if not re.search(r"\d+\s*-\s*\d+", content):
            reasons_revision.append("MATCH_REPORT draft seems to be missing score format (e.g. 1-0).")
            
    if content_type == ContentType.ANALYSIS_EXPLAINER:
        if len(content.split()) < 300:
            reasons_revision.append("ANALYSIS_EXPLAINER is too short.")
            
    if content_type == ContentType.HARD_NEWS:
        if len(content.split()) > 1000:
            reasons_revision.append("HARD_NEWS is too long.")
            
    # 4. Anti-filler checks
    filler_reasons = check_filler_and_repetition(content)
    if filler_reasons:
        reasons_revision.extend(filler_reasons)
        
    # 5. Quote Integrity Check
    if facts:
        quote_errors = enforce_quote_integrity(content, facts)
        if quote_errors:
            reasons_revision.extend(quote_errors)
            
    if reasons_blocked:
        return ValidationResult(False, "BLOCKED", reasons_blocked)
        
    if reasons_revision:
        return ValidationResult(False, "NEEDS_REVISION", reasons_revision)
        
    return ValidationResult(True, "APPROVED", [])

