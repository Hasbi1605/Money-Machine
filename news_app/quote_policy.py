from typing import Dict, Any, List
from bs4 import BeautifulSoup
from loguru import logger
import re

def normalize_for_comparison(text: str) -> str:
    """Strip punctuation and lowercase for fuzzy quote comparison."""
    if not text:
        return ""
    text = text.lower()
    text = re.sub(r'[^a-z0-9\s]', '', text)
    return " ".join(text.split())

def enforce_quote_integrity(draft_html: str, extracted_facts: Dict[str, Any]) -> List[str]:
    """
    Validates that any direct quote in the draft exists in the extracted source quotes.
    Prevents LLM hallucinated quotes.
    Returns a list of validation errors (empty if passed).
    """
    errors = []
    
    if not draft_html:
        return errors

    # Collect valid quotes from extracted facts
    valid_quotes = []
    
    # Standard format: { "quotes": [ {"quote": "...", "speaker": "..."} ] }
    if "quotes" in extracted_facts and isinstance(extracted_facts["quotes"], list):
        for q in extracted_facts["quotes"]:
            val = q.get("quote") if isinstance(q, dict) else str(q)
            if val:
                valid_quotes.append(normalize_for_comparison(val))
                
    # Also grab quotes from related sources just in case
    for source in extracted_facts.get("related_sources", []):
        if "quotes" in source and isinstance(source["quotes"], list):
            for q in source["quotes"]:
                val = q.get("quote") if isinstance(q, dict) else str(q)
                if val:
                    valid_quotes.append(normalize_for_comparison(val))

    # Parse draft to find blockquotes or inline quotes
    soup = BeautifulSoup(draft_html, "html.parser")
    draft_quotes = soup.find_all("blockquote")
    
    # We can also search for exact quoted sentences using regex if we want to be stricter,
    # but the LLM is instructed to use <blockquote> tags for direct quotes.
    
    for dq in draft_quotes:
        draft_text = dq.get_text().strip()
        if not draft_text:
            continue
            
        draft_norm = normalize_for_comparison(draft_text)
        
        # Check if the draft quote is a substring of, or closely matches, any valid quote
        # We allow substrings because the LLM might quote only part of a sentence.
        is_supported = False
        for vq in valid_quotes:
            if draft_norm in vq or vq in draft_norm:
                is_supported = True
                break
                
        if not is_supported:
            logger.warning(f"Unsupported quote detected: '{draft_text[:50]}...'")
            errors.append(f"UNSUPPORTED QUOTE: '{draft_text[:50]}...' cannot be found verbatim in the source facts. Remove or paraphrase it.")

    return errors
