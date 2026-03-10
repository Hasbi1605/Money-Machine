import hashlib
import re
from typing import Dict, Any

def generate_story_key(headline: Dict[str, Any]) -> str:
    """
    Generate a canonical story key to prevent duplicate articles.
    Prefers the original source URL for uniqueness.
    If no source URL, falls back to hashing a normalized version of the title.
    """
    source_url = headline.get("source_url", "")
    if source_url and source_url.startswith("http"):
        # Strip query params like ?utm_source, etc from standard news URLs
        base_url = source_url.split("?")[0].strip("/")
        return hashlib.md5(base_url.encode("utf-8")).hexdigest()
        
    title = headline.get("title", "")
    if title:
        # Normalize title: lower, remove punctuation, extract just alphanumeric
        normalized_title = re.sub(r"[^\w\s]", "", title.lower())
        normalized_title = re.sub(r"\s+", " ", normalized_title).strip()
        return hashlib.md5(normalized_title.encode("utf-8")).hexdigest()
        
    return hashlib.md5(str(headline).encode("utf-8")).hexdigest()
