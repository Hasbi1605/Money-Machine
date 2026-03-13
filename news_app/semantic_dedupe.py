import json
from datetime import datetime, timedelta
from typing import Dict, Any, Tuple, Optional
from shared.gemini_client import gemini
from shared.database import get_recent_article_titles
from loguru import logger
from news_app.schema_validation import validate_nested_schema, format_schema_retry_prompt
import re

async def evaluate_semantic_duplicate(headline: Dict[str, Any], category: str) -> Tuple[str, Optional[str]]:
    """
    Checks if the incoming headline is a semantic duplicate or material update of a recent published story.
    Returns: (Action, canonical_story_key)
    Actions: "NEW_STORY", "EXACT_DUPLICATE_SKIP", "MATERIAL_UPDATE"
    """
    # 1. Fetch recent articles (last 3 days) in the same category
    recent_articles = await get_recent_article_titles(category, days=3)
    if not recent_articles:
        return "NEW_STORY", None

    # We only care about title and source for the zero-shot dedupe to save tokens
    recent_simplified = [
        {
            "title": art["title"],
            "canonical_story_key": art["canonical_story_key"],
            "source_name": art.get("source_name", "Unknown")
        }
        for art in recent_articles
    ]

    system_instruction = "You are a senior newsroom deduplicator. Your job is to determine if a new incoming headline is about the EXACT SAME event as any recently published stories."

    prompt = f"""
We want to publish a new article based on the following incoming news:

**INCOMING STORY:**
Title: {headline.get('title')}
Source: {headline.get('source_name', 'Unknown')}
Summary Snippet: {headline.get('summary', '')[:300]}

**RECENTLY PUBLISHED STORIES (Last 3 Days):**
```json
{json.dumps(recent_simplified, indent=2, ensure_ascii=False)}
```

**TASK:**
Compare the INCOMING STORY to the RECENTLY PUBLISHED STORIES.
1. Action "NEW_STORY": This is a distinctly new, separate event.
2. Action "EXACT_DUPLICATE_SKIP": This is the exact same story/event, and there is NO significant material update (e.g., just another wire covering the same match result or same press conference). Skip it.
3. Action "MATERIAL_UPDATE": It's the same base story, BUT the incoming story contains a verified, significant update (e.g., score changed, casualty count rose significantly, official verdict released). 

If Action is not NEW_STORY, you MUST provide the `canonical_story_key` of the matched recently published story.

**REQUIRED JSON SCHEMA:**
{{
    "action": "NEW_STORY" | "EXACT_DUPLICATE_SKIP" | "MATERIAL_UPDATE",
    "matched_canonical_story_key": "string or null",
    "reasoning": "Brief explanation of your decision"
}}
"""

    schema = {
        "action": str,
        "reasoning": str
    }

    try:
        response_data = await gemini.generate_json(prompt, system_instruction=system_instruction)
        
        # Schema validation
        is_valid, errors = validate_nested_schema(response_data, schema)
        if not is_valid:
            logger.warning(f"Semantic dedupe schema failed: {errors}")
            retry_prompt = format_schema_retry_prompt(prompt, errors, response_data)
            response_data = await gemini.generate_json(retry_prompt, system_instruction=system_instruction)
            is_valid, _ = validate_nested_schema(response_data, schema)
            if not is_valid:
                logger.error("Deduper schema failed twice. Defaulting to NEW_STORY.")
                return "NEW_STORY", None

    except Exception as e:
        logger.error(f"Semantic deduplicator LLM call failed: {e}")
        return "NEW_STORY", None

    action = response_data.get("action", "NEW_STORY")
    matched_key = response_data.get("matched_canonical_story_key", None)
    
    if action in ["EXACT_DUPLICATE_SKIP", "MATERIAL_UPDATE"] and matched_key:
        logger.info(f"🧬 Semantic Dedupe Match: {action} on key {matched_key}. Reason: {response_data.get('reasoning')}")
        return action, matched_key
        
    return "NEW_STORY", None

def generate_canonical_story_key(headline: Dict[str, Any]) -> str:
    """
    Fallback deterministic canonical key generator for new distinct stories.
    Uses normalized title tokens.
    """
    title = headline.get("title", "").lower()
    # Remove punctuation
    title = re.sub(r"[^\w\s]", "", title)
    # Get top 5 longest words (usually entities/subjects)
    words = sorted(title.split(), key=len, reverse=True)[:5]
    merged = "_".join(sorted(words))
    return f"can_story_{merged}"[:100]
