import re
from datetime import datetime
from typing import Dict, Optional, Any
from loguru import logger
from bs4 import BeautifulSoup

from shared.gemini_client import gemini
from shared.database import story_exists, log_failure_audit
from news_app.content_types import determine_content_type, get_content_type_rules
from news_app.fact_extractor import extract_facts
from news_app.validators import validate_extracted_facts, validate_draft
from news_app.prompt_templates import get_drafting_prompt, get_revision_prompt, TemplateKeys
from news_app.dedupe import generate_story_key
from news_app.freshness import is_stale
from news_app.entity_normalizer import enforce_entity_consistency
from news_app.html_sanitizer import sanitize_and_repair_html

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
    source_url = headline.get("source_url", "")
    source = headline.get("source_name", "Unknown")
    
    logger.info(f"🚀 Starting autonomous pipeline for: {title[:60]}... [{category}]")
    
    # 0. Deduplication Check
    story_key = generate_story_key(headline)
    if await story_exists(story_key):
        logger.info(f"⏭️ Skipping duplicate story (key: {story_key})")
        return None
        
    headline["story_key"] = story_key

    # 1. Content Classification with LLM confidence
    content_type, conf_score = await determine_content_type(category, title, headline.get("summary", ""))
    ct_rules = get_content_type_rules(content_type)
    logger.info(f"📋 Classified as {content_type.name} (Confidence: {conf_score:.2f})")
    
    # 2. Freshness Check
    if is_stale(headline, content_type):
        await log_failure_audit(source_url, title, content_type.name, "FRESHNESS_CHECK", "Source article is stale.", 0)
        return None

    for attempt in range(1, MAX_RETRIES + 1):
        logger.info(f"🔄 Generation Attempt {attempt}/{MAX_RETRIES}")
        
        # 3. Fact Extraction
        facts = await extract_facts(headline, content_type, category)
        if not facts:
            logger.warning("Fokus ekstraksi gagal. Melewati ke percobaan berikutnya.")
            if attempt == MAX_RETRIES:
                await log_failure_audit(source_url, title, content_type.name, "FACT_EXTRACTION", "Extraction yielded None.", attempt)
            continue
            
        # 4. Fact Validation
        fact_validation = validate_extracted_facts(facts, content_type)
        if not fact_validation.is_valid:
            logger.warning(f"🚫 Fails fact validation: {fact_validation.reasons}")
            if attempt == MAX_RETRIES:
                await log_failure_audit(source_url, title, content_type.name, "FACT_VALIDATION", ", ".join(fact_validation.reasons), attempt)
            continue # Retry from top
            
        # 5. Drafting
        draft_prompt = get_drafting_prompt(content_type, ct_rules, facts, affiliate_links)
        system_instruction = draft_prompt[TemplateKeys.SYSTEM_INSTRUCTION]
        prompt = draft_prompt[TemplateKeys.USER_PROMPT]
        
        try:
            draft = await gemini.generate_json(prompt, system_instruction=system_instruction)
        except Exception as e:
            logger.error(f"Draft generation failed: {e}")
            if attempt == MAX_RETRIES:
                await log_failure_audit(source_url, title, content_type.name, "LLM_DRAFTING", str(e), attempt)
            continue
            
        if not draft or not draft.get("content"):
            logger.warning("Empty draft returned by LLM.")
            if attempt == MAX_RETRIES:
                await log_failure_audit(source_url, title, content_type.name, "LLM_DRAFTING", "Empty draft returned.", attempt)
            continue
            
        # 6. Entity Consistency Check
        inconsistencies = await enforce_entity_consistency(draft.get("content", ""), facts)
        if inconsistencies:
            logger.warning(f"Entity inconsistencies flagged: {inconsistencies}")
            # If inconsistencies exist, we attempt revision.
            qc_result = type('obj', (object,), {'status': 'NEEDS_REVISION', 'reasons': inconsistencies})
        else:
            # 7. Standard QC Validation (including filler checks)
            qc_result = validate_draft(draft, content_type)
        
        logger.info(f"⚖️ QC Validation: {qc_result.status}")
        
        if qc_result.status == "APPROVED":
            return _finalize_article(draft, headline, category, source_url, source)
            
        elif qc_result.status == "NEEDS_REVISION":
            logger.info("🛠️ Attempting auto-revision...")
            revision_prompt_text = get_revision_prompt(draft.get("content", ""), qc_result.reasons)
            try:
                revised_draft = await gemini.generate_json(revision_prompt_text, system_instruction=system_instruction)
                if revised_draft and revised_draft.get("content"):
                    
                    # Second pass entity validation for revised draft
                    rev_inconsistencies = await enforce_entity_consistency(revised_draft.get("content", ""), facts)
                    if rev_inconsistencies:
                        logger.warning(f"❌ Auto-revision entity inconsistencies: {rev_inconsistencies}")
                        if attempt == MAX_RETRIES:
                            await log_failure_audit(source_url, title, content_type.name, "AUTO_REVISION_ENTITIES", ", ".join(rev_inconsistencies), attempt)
                        continue # fall through to next full loop attempt

                    rev_qc_result = validate_draft(revised_draft, content_type)
                    if rev_qc_result.status == "APPROVED":
                        logger.info("✅ Auto-revision successful!")
                        for key, val in revised_draft.items():
                            if val:
                                draft[key] = val
                        return _finalize_article(draft, headline, category, source_url, source)
                    else:
                        logger.warning(f"❌ Auto-revision failed QC again: {rev_qc_result.reasons}")
                        if attempt == MAX_RETRIES:
                            await log_failure_audit(source_url, title, content_type.name, "AUTO_REVISION_QC", ", ".join(rev_qc_result.reasons), attempt)
                else:
                    logger.warning("Auto-revision returned empty.")
                    if attempt == MAX_RETRIES:
                        await log_failure_audit(source_url, title, content_type.name, "AUTO_REVISION", "Empty revision draft.", attempt)
            except Exception as e:
                logger.error(f"Auto-revision exception: {e}")
                if attempt == MAX_RETRIES:
                    await log_failure_audit(source_url, title, content_type.name, "AUTO_REVISION_EXCEPTION", str(e), attempt)
            
            # If revision falls through, loop continues to next full retry
            
        elif qc_result.status == "BLOCKED":
            logger.warning(f"🚫 Draft blocked: {qc_result.reasons}")
            if attempt == MAX_RETRIES:
                await log_failure_audit(source_url, title, content_type.name, "QC_BLOCKED", ", ".join(qc_result.reasons), attempt)
            # Loop continues to next retry

    # If we exit the loop, retries exhausted
    logger.error(f"🛑 Generation aborted: Exhausted {MAX_RETRIES} retries for '{title}'. Skipping publication.")
    return None

def _finalize_article(draft: Dict[str, Any], headline: Dict[str, Any], category: str, source_url: str, source: str) -> Dict[str, Any]:
    """
    Clean up the valid draft, apply HTML sanitization, and structure it for the database.
    """
    title = draft.get("title") or headline.get("title", "")
    
    # Ensure slug
    if not draft.get("slug"):
        draft["slug"] = re.sub(r"[^a-z0-9]+", "-", title.lower())[:80].strip("-")

    draft["category"] = category
    draft["source_title"] = title
    draft["source_url"] = source_url
    draft["source_name"] = source
    draft["story_key"] = headline.get("story_key", "")
    draft["original_image_url"] = headline.get("original_image_url", "")
    draft["generated_at"] = datetime.utcnow().isoformat()

    # Apply strict HTML Sanitization
    if draft.get("content"):
        safe_html = sanitize_and_repair_html(draft["content"])
        draft["content"] = safe_html

    word_count = draft.get("word_count", len(draft["content"].split()))
    logger.info(f"✅ Article finalized safe: '{title}' (~{word_count} words)")

    return draft
