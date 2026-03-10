import re
from datetime import datetime
from typing import Dict, Optional, Any
from loguru import logger
from bs4 import BeautifulSoup

from shared.gemini_client import gemini
from news_app.content_types import determine_content_type, get_content_type_rules
from news_app.fact_extractor import extract_facts
from news_app.validators import validate_extracted_facts, validate_draft
from news_app.prompt_templates import get_drafting_prompt, get_revision_prompt, TemplateKeys

MAX_RETRIES = 2

async def run_editorial_pipeline(
    headline: Dict[str, Any],
    category: str,
    affiliate_links: str = ""
) -> Optional[Dict[str, Any]]:
    """
    Run the strict autonomous editorial pipeline.
    Returns the article dictionary if successful, or None if skipped/aborted.
    """
    title = headline.get("title", "")
    source = headline.get("source_name", "Unknown")
    
    logger.info(f"🚀 Starting autonomous pipeline for: {title[:60]}... [{category}]")
    
    # 1. Content Classification
    content_type = determine_content_type(category, title)
    ct_rules = get_content_type_rules(content_type)
    logger.info(f"📋 Classified as {content_type.name}")

    for attempt in range(1, MAX_RETRIES + 1):
        logger.info(f"🔄 Generation Attempt {attempt}/{MAX_RETRIES}")
        
        # 2. Fact Extraction
        facts = await extract_facts(headline, content_type)
        if not facts:
            logger.warning("Fokus ekstraksi gagal. Melewati ke percobaan berikutnya.")
            continue
            
        # 3. Fact Validation
        fact_validation = validate_extracted_facts(facts, content_type)
        if not fact_validation.is_valid:
            logger.warning(f"🚫 Fails fact validation: {fact_validation.reasons}")
            continue # Retry from top
            
        # 4. Drafting
        draft_prompt = get_drafting_prompt(content_type, ct_rules, facts, affiliate_links)
        
        system_instruction = draft_prompt[TemplateKeys.SYSTEM_INSTRUCTION]
        prompt = draft_prompt[TemplateKeys.USER_PROMPT]
        
        try:
            draft = await gemini.generate_json(prompt, system_instruction=system_instruction)
        except Exception as e:
            logger.error(f"Draft generation failed: {e}")
            continue
            
        if not draft or not draft.get("content"):
            logger.warning("Empty draft returned by LLM.")
            continue
            
        # 5. QC Validation
        qc_result = validate_draft(draft, content_type)
        logger.info(f"⚖️ QC Validation: {qc_result.status}")
        
        if qc_result.status == "APPROVED":
            return _finalize_article(draft, headline, category, source)
            
        elif qc_result.status == "NEEDS_REVISION":
            logger.info("🛠️ Attempting auto-revision...")
            revision_prompt_text = get_revision_prompt(draft.get("content", ""), qc_result.reasons)
            try:
                revised_draft = await gemini.generate_json(revision_prompt_text, system_instruction=system_instruction)
                if revised_draft and revised_draft.get("content"):
                    rev_qc_result = validate_draft(revised_draft, content_type)
                    if rev_qc_result.status == "APPROVED":
                        logger.info("✅ Auto-revision successful!")
                        # Copy the revised content back into the main draft wrapper 
                        # just in case it returned fewer fields, but usually they return all.
                        for key, val in revised_draft.items():
                            if val:
                                draft[key] = val
                        return _finalize_article(draft, headline, category, source)
                    else:
                        logger.warning(f"❌ Auto-revision failed QC again: {rev_qc_result.reasons}")
                else:
                    logger.warning("Auto-revision returned empty.")
            except Exception as e:
                logger.error(f"Auto-revision exception: {e}")
            
            # If revision falls through, the loop continues to the next full retry
            
        elif qc_result.status == "BLOCKED":
            logger.warning(f"🚫 Draft blocked: {qc_result.reasons}")
            # Loop continues to next retry

    # If we exit the loop, retries exhausted
    logger.error(f"🛑 Generation aborted: Exhausted {MAX_RETRIES} retries for '{title}'. Skipping publication.")
    return None

def _finalize_article(draft: Dict[str, Any], headline: Dict[str, Any], category: str, source: str) -> Dict[str, Any]:
    """
    Clean up the valid draft and structure the dictionary for the database.
    """
    title = draft.get("title") or headline.get("title", "")
    
    # Ensure slug
    if not draft.get("slug"):
        draft["slug"] = re.sub(r"[^a-z0-9]+", "-", title.lower())[:80].strip("-")

    draft["category"] = category
    draft["source_title"] = title
    draft["source_url"] = headline.get("source_url", "")
    draft["source_name"] = source
    draft["original_image_url"] = headline.get("original_image_url", "")
    draft["generated_at"] = datetime.utcnow().isoformat()

    # Sanitize HTML
    if draft.get("content"):
        soup = BeautifulSoup(draft["content"], "html.parser")
        draft["content"] = str(soup)

    word_count = draft.get("word_count", len(draft["content"].split()))
    logger.info(f"✅ Article ready: '{title}' (~{word_count} words)")

    return draft
