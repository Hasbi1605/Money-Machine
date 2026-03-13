import re
from typing import Dict, Any
from bs4 import BeautifulSoup
from loguru import logger

def generate_seo_slug(title: str, max_length: int = 80) -> str:
    """Generate a clean, SEO-friendly URL slug from a title."""
    if not title:
        return "terkini"
    
    # Lowercase and replace non-alphanumeric with hyphens
    slug = re.sub(r"[^a-z0-9]+", "-", title.lower())
    # Strip leading/trailing hyphens and trim to max length safely without cutting middle of words if possible
    slug = slug.strip("-")
    
    if len(slug) > max_length:
        slug = slug[:max_length].rsplit('-', 1)[0]
        
    return slug

def format_title_case(title: str) -> str:
    """
    Format title using standard Title Case capitalization rules for Indonesian/English.
    Keeps acronyms uppercase.
    """
    if not title:
        return title
        
    lowercase_words = {"dan", "atau", "di", "ke", "dari", "pada", "dalam", "untuk", "dengan", "yang", "of", "the", "in"}
    
    words = title.split()
    formatted_words = []
    
    for i, word in enumerate(words):
        # Always capitalize first or last word
        if i == 0 or i == len(words) - 1:
            formatted_words.append(word.capitalize() if not word.isupper() else word)
        # If it's an acronym (all caps), keep it
        elif word.isupper():
            formatted_words.append(word)
        # If it's a conjunction/preposition, lowercase
        elif word.lower() in lowercase_words:
            formatted_words.append(word.lower())
        # Otherwise capitalize
        else:
            formatted_words.append(word.capitalize())
            
    return " ".join(formatted_words)

def generate_excerpt(content_html: str, max_chars: int = 150) -> str:
    """
    Generate a clean text excerpt from HTML content.
    Returns the first paragraph or truncated text up to max_chars.
    """
    if not content_html:
        return ""
        
    soup = BeautifulSoup(content_html, "html.parser")
    
    # Try to get the very first paragraph
    first_p = soup.find('p')
    if first_p:
        text = first_p.get_text(separator=' ').strip()
    else:
        # Fallback to whole text
        text = soup.get_text(separator=' ').strip()
        
    if len(text) <= max_chars:
        return text
        
    # Truncate cleanly at a word boundary
    truncated = text[:max_chars].rsplit(' ', 1)[0]
    return f"{truncated}..."

def enforce_metadata_quality(draft: Dict[str, Any]) -> Dict[str, Any]:
    """
    Apply title, slug, and excerpt formatting to a drafted article.
    """
    original_title = draft.get("title", "")
    
    clean_title = format_title_case(original_title)
    draft["title"] = clean_title
    
    draft["slug"] = generate_seo_slug(clean_title)
    
    if "content" in draft:
        draft["excerpt"] = generate_excerpt(draft["content"])
        
    return draft
