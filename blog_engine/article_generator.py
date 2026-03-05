"""
Article Generator - Creates SEO-optimized articles with affiliate links.
Powered by Gemini API.
"""

import json
import re
import random
from typing import Dict, Optional, List
from pathlib import Path
from datetime import datetime

from loguru import logger

from shared.gemini_client import gemini
from shared.config import settings


# Load affiliate config
AFFILIATE_CONFIG_PATH = Path(__file__).parent / "affiliate_config.json"
with open(AFFILIATE_CONFIG_PATH) as f:
    AFFILIATE_CONFIG = json.load(f)

# Override affiliate tags from .env (so they don't need to be hardcoded in JSON)
_tag_map = {
    "amazon": settings.affiliate.amazon_tag,
    "tokopedia": settings.affiliate.tokopedia_id,
    "shopee": settings.affiliate.shopee_id,
    "alfagift": settings.affiliate.alfagift_id,
}
for prog_key, tag_value in _tag_map.items():
    if tag_value and prog_key in AFFILIATE_CONFIG["programs"]:
        AFFILIATE_CONFIG["programs"][prog_key]["tag"] = tag_value


def get_affiliate_links(keyword: str, language: str = "en") -> List[Dict]:
    """Generate affiliate link placeholders based on keyword and language."""
    programs = AFFILIATE_CONFIG["default_programs"].get(language, ["amazon"])
    links = []

    for prog_key in programs:
        prog = AFFILIATE_CONFIG["programs"].get(prog_key, {})
        if not prog:
            continue

        # Build link
        search_term = keyword.replace(" ", "+")
        base = prog["base_url"]
        tag = prog.get("tag", "")
        param = prog.get("tag_param", "tag")

        url = f"{base}{search_term}"
        if tag:
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}{param}={tag}"

        # Pick CTA templates
        cta_key = f"cta_templates_{language}" if f"cta_templates_{language}" in prog else "cta_templates_en"
        ctas = prog.get(cta_key, prog.get("cta_templates_en", ["Check price"]))

        links.append({
            "program": prog["name"],
            "url": url,
            "cta": random.choice(ctas),
        })

    return links


def get_disclosure(language: str = "en") -> str:
    """Get affiliate disclosure text."""
    return AFFILIATE_CONFIG["disclosure"].get(language, AFFILIATE_CONFIG["disclosure"]["en"])


async def generate_article(
    keyword_data: Dict,
    language: str = "en",
) -> Dict:
    """
    Generate a full SEO-optimized article.

    Args:
        keyword_data: Dict with 'keyword', 'article_type', 'suggested_title', etc.
        language: 'en' or 'id'

    Returns:
        Dict with 'title', 'content', 'meta_description', 'tags', 'slug'
    """
    keyword = keyword_data.get("keyword", "")
    article_type = keyword_data.get("article_type", "listicle")
    suggested_title = keyword_data.get("suggested_title", keyword.title())

    # Get affiliate links
    aff_links = get_affiliate_links(keyword, language)
    affiliate_section = ""
    if aff_links:
        affiliate_section = "\n".join([
            f"- [{link['cta']}]({link['url']}) ({link['program']})"
            for link in aff_links
        ])

    disclosure = get_disclosure(language)

    lang_name = "Indonesian (Bahasa Indonesia)" if language == "id" else "English"

    system_instruction = f"""You are an expert SEO content writer and product reviewer.
You write in {lang_name}.
You create engaging, well-researched, and helpful content that ranks well on Google.
Your articles naturally include product recommendations with affiliate links.
You use proper HTML heading structure (h2, h3) for SEO.
You write in a conversational but authoritative tone."""

    prompt = f"""Write a comprehensive {article_type} article about: "{keyword}"

**Language:** {lang_name}
**Suggested Title:** {suggested_title}
**Target Word Count:** 1800-2500 words

**Structure Requirements:**
1. Start with an engaging introduction (hook the reader in first 2 sentences)
2. Use H2 and H3 headings with keyword variations
3. Include a table of contents at the top
4. Write at least 5-7 main sections
5. Include practical tips, pros/cons, or comparisons where relevant
6. End with a conclusion and FAQ section (3-5 FAQs with answers)

**SEO Requirements:**
- Include the main keyword naturally 5-8 times throughout the article
- Use LSI (related) keywords naturally
- Write a compelling meta description (150-160 chars)
- Suggest 5-8 relevant tags

**Affiliate Integration:**
Naturally incorporate these affiliate links where relevant in the content:
{affiliate_section}

Use them as product recommendations, "where to buy" sections, or comparison links.
DO NOT make the article feel like a sales pitch. Provide genuine value first.

**Disclosure:**
Include this disclosure near the top of the article (after the introduction):
{disclosure}

**Output Format:**
Return the article as a JSON object with these fields:
- title: SEO-optimized article title (with main keyword)
- slug: URL-friendly slug  
- meta_description: 150-160 char meta description
- content: Full article in Markdown format with proper headings
- tags: array of 5-8 relevant tags
- word_count: approximate word count
- excerpt: 2-3 sentence excerpt for social sharing"""

    logger.info(f"Generating article for keyword: {keyword} ({language})")

    try:
        result = await gemini.generate_json(prompt, system_instruction=system_instruction)

        # Validate required fields
        required = ["title", "content"]
        for field in required:
            if field not in result:
                logger.error(f"Missing field '{field}' in generated article")
                return {}

        # Add metadata
        result["keyword"] = keyword
        result["language"] = language
        result["generated_at"] = datetime.utcnow().isoformat()
        result["affiliate_links"] = len(aff_links)

        # Ensure slug exists
        if "slug" not in result or not result["slug"]:
            result["slug"] = re.sub(r'[^a-z0-9]+', '-', keyword.lower()).strip('-')

        # Save to file
        output_path = settings.output_dir / "articles" / f"{result['slug']}_{language}.json"
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)

        word_count = result.get("word_count", len(result["content"].split()))
        logger.info(f"Article generated: '{result['title']}' (~{word_count} words)")

        return result

    except Exception as e:
        logger.error(f"Article generation failed for '{keyword}': {e}")
        return {}


async def generate_social_snippets(article: Dict) -> Dict:
    """Generate social media snippets for promoting the article."""
    if not article:
        return {}

    prompt = f"""Based on this article, create social media promotional content:

Title: {article.get('title', '')}
Excerpt: {article.get('excerpt', '')}
Language: {article.get('language', 'en')}

Create:
1. A Twitter/X post (max 280 chars, with hashtags)
2. A LinkedIn post (2-3 paragraphs, professional tone)
3. A Facebook post (casual, engaging with emoji)
4. An Instagram caption (with hashtags)

Return as JSON with keys: twitter, linkedin, facebook, instagram"""

    try:
        return await gemini.generate_json(prompt)
    except Exception as e:
        logger.warning(f"Social snippet generation failed: {e}")
        return {}
