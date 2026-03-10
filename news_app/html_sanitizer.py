from bs4 import BeautifulSoup
from loguru import logger

def sanitize_and_repair_html(html_content: str) -> str:
    """
    Whitelist-based HTML sanitization and repair.
    Removes dangerous or unsupported tags and attributes.
    Repairs missing closing tags using BeautifulSoup.
    """
    if not html_content:
        return ""
        
    soup = BeautifulSoup(html_content, "html.parser")
    allowed_tags = {"p", "h2", "h3", "strong", "em", "ul", "ol", "li", "blockquote", "a", "br", "span"}
    allowed_attrs = {"a": ["href", "title", "target", "rel"], "p": ["class"]}
    
    for tag in soup.find_all(True):
        if tag.name not in allowed_tags:
            # Replace tag with its contents (strip the tag itself)
            tag.unwrap()
        else:
            # Clean attributes
            attrs_to_keep = allowed_attrs.get(tag.name, [])
            for attr in list(tag.attrs.keys()):
                if attr not in attrs_to_keep:
                    del tag[attr]
                    
    # Force string parsing to fix any unclosed tags
    return str(soup)
