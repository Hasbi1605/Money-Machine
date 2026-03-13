import re
from typing import Dict, Any
from loguru import logger

# Boilerplate that often clutters articles and confuses the extractor/LLM
BOILERPLATE_PATTERNS = [
    r"(?i)click here to read more",
    r"(?i)subscribe to our newsletter",
    r"(?i)follow us on (twitter|facebook|instagram|tiktok|youtube|x)",
    r"(?i)download our app",
    r"(?i)sign up for free",
    r"(?i)all rights reserved",
    r"(?i)copyright \d{4}",
    r"(?i)read also:",
    r"(?i)baca juga[:]",
    r"(?i)simak selengkapnya",
    r"(?i)jangan lewatkan",
]

# Injection patterns attempting to override instructions
INJECTION_PATTERNS = [
    r"(?i)ignore previous instructions?",
    r"(?i)disregard previous prompt",
    r"(?i)forget all instructions?",
    r"(?i)you are now a",
    r"(?i)system prompt override",
]

def clean_source_text(text: str) -> str:
    """
    Remove boilerplate ad text and neutralize prompt-injection patterns.
    """
    if not text:
        return ""

    original_length = len(text)
    
    # 1. Remove boilerplate
    for pattern in BOILERPLATE_PATTERNS:
        # We replace the matched string with an empty string
        text = re.sub(pattern, "", text)

    # 2. Sanitize and neutralize injection attacks
    # Instead of deleting, we might want to just break the command so it's not parsed as an instruction
    for pattern in INJECTION_PATTERNS:
        # Masking the instruction
        text = re.sub(pattern, "[REDACTED ATTEMPT]", text)
        
    # 3. Clean up excessive whitespace created by removals
    text = re.sub(r'\n{3,}', '\n\n', text)
    text = text.strip()
    
    if len(text) < original_length:
        logger.debug(f"Source cleaner removed {original_length - len(text)} bytes of boilerplate/injection risk.")
        
    return text

def preprocess_headline_sources(headline: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply source cleaner to the primary content and all related source content.
    """
    # Clean main summary/content
    if headline.get("summary"):
        headline["summary"] = clean_source_text(headline["summary"])
        
    if headline.get("content"):
        headline["content"] = clean_source_text(headline["content"])
        
    # Clean related sources if they exist
    if "related_sources" in headline and isinstance(headline["related_sources"], list):
        for rs in headline["related_sources"]:
            if rs.get("summary"):
                rs["summary"] = clean_source_text(rs["summary"])
            if rs.get("content"):
                rs["content"] = clean_source_text(rs["content"])
                
    return headline
