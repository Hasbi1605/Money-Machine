import re
from typing import Dict, Any, Tuple
from loguru import logger
from news_app.content_types import ContentType

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
    Runs BEFORE drafting.
    If blocked, the pipeline will skip generation.
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
            
    if content_type == ContentType.HARD_NEWS:
        what = ct_specific.get("what")
        who = ct_specific.get("who")
        if not what or not who:
            reasons.append("HARD_NEWS is missing critical facts: who or what.")
            
    if reasons:
        return ValidationResult(False, "BLOCKED", reasons)
        
    return ValidationResult(True, "APPROVED", [])

def validate_draft(draft: Dict[str, Any], content_type: ContentType) -> ValidationResult:
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
    # Must have paragraphs
    if "<p>" not in content:
        reasons_blocked.append("Missing required HTML structure: <p>")
        
    # Must have headings
    if "<h2>" not in content and content_type != ContentType.HARD_NEWS:
        reasons_revision.append("Missing required HTML structure: <h2>")
        
    # 3. Content Type specific validations
    if content_type == ContentType.MATCH_REPORT:
        # Check if score format like "1-0", "2-2", etc. exists
        if not re.search(r"\d+\s*-\s*\d+", content):
            reasons_revision.append("MATCH_REPORT draft seems to be missing score format (e.g. 1-0).")
            
    if content_type == ContentType.ANALYSIS_EXPLAINER:
        if len(content.split()) < 300:
            reasons_revision.append("ANALYSIS_EXPLAINER is too short.")
            
    if content_type == ContentType.HARD_NEWS:
        if len(content.split()) > 1000:
            reasons_revision.append("HARD_NEWS is too long.")
            
    if reasons_blocked:
        return ValidationResult(False, "BLOCKED", reasons_blocked)
        
    if reasons_revision:
        return ValidationResult(False, "NEEDS_REVISION", reasons_revision)
        
    return ValidationResult(True, "APPROVED", [])
