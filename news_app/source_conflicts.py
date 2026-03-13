import json
from enum import IntEnum
from typing import Dict, Any, Tuple, List
from shared.gemini_client import gemini
from loguru import logger
from news_app.schema_validation import validate_nested_schema, format_schema_retry_prompt

class SourceTier(IntEnum):
    OFFICIAL = 4      # Primary source (Gov, Police, Direct Club Official)
    MAJOR_WIRE = 3    # High-trust (Reuters, AP, AFP, BBC, CNN)
    MAINSTREAM = 2    # Standard national news (Detik, Kompas, etc.)
    SECONDARY = 1     # Aggregators, lower-tier blogs, unverified social media

def assign_source_tier(source_name: str, source_url: str) -> SourceTier:
    """Assigns a trust tier to a given source."""
    s_lower = source_name.lower()
    u_lower = source_url.lower()
    
    # Official / Primary
    if any(x in s_lower for x in ["police", "polri", "pemerintah", "official", "kpk", "kemen"]):
        return SourceTier.OFFICIAL
    if any(x in u_lower for x in ["go.id", "gov.", "police.uk"]):
        return SourceTier.OFFICIAL
        
    # Major Wire
    if any(x in s_lower for x in ["reuters", "ap ", "associated press", "afp", "bbc", "cnn", "bloomberg"]):
        return SourceTier.MAJOR_WIRE
        
    # Mainstream Indonesian / Global
    if any(x in s_lower for x in ["kompas", "detik", "tribun", "tempo", "cnbc", "cnn indonesia", "goal", "espn", "skysports"]):
        return SourceTier.MAINSTREAM
        
    return SourceTier.SECONDARY

async def detect_and_resolve_conflicts(facts: Dict[str, Any], sources_metadata: List[Dict[str, str]]) -> Tuple[Dict[str, Any], bool, Dict[str, Any]]:
    """
    Analyzes extracted facts for contradictions (e.g., different scores, dates, casualty counts).
    Uses SourceTier logic to auto-resolve if possible.
    Returns: (Resolved Facts, has_unresolvable_conflict, conflict_logs)
    """
    
    # Provide the LLM with the extracted facts and the trust tiers of the available sources.
    tiers_str = "\n".join([f"- {s.get('name', 'Unknown')}: Tier {assign_source_tier(s.get('name', 'Unknown'), s.get('url', '')).name}" for s in sources_metadata])
    
    system_instruction = "You are a senior investigative editor. Your job is to resolve contradicting facts from multiple sources."
    
    prompt = f"""
We have extracted the following facts from multiple sources.

**EXTRACTED FACTS:**
```json
{json.dumps(facts, indent=2, ensure_ascii=False)}
```

**AVAILABLE SOURCES & TRUST TIERS:**
{tiers_str}

**TRUST TIER HIERARCHY:**
OFFICIAL (Best) > MAJOR_WIRE > MAINSTREAM > SECONDARY (Worst)

**TASK:**
1. Check if there are any CRITICAL contradictions between sources (e.g., Team A won 2-0 vs Team A won 2-1, or 5 dead vs 10 dead).
2. If there are contradictions, attempt to resolve them by favoring the higher Trust Tier source.
3. If the contradiction is between two sources of the SAME trust tier, or there is no clear resolution, mark it as UNRESOLVABLE.
4. If there are no contradictions, return the original facts unaltered.

**REQUIRED JSON SCHEMA:**
{{
    "conflicts_detected": false,
    "unresolvable_conflict": false,
    "conflict_details": ["Describe conflicts here if any"],
    "resolved_facts": {{ ... updated facts dict here, drop the false claims ... }}
}}
"""
    
    schema = {
        "conflicts_detected": bool,
        "unresolvable_conflict": bool,
        "conflict_details": list,
        "resolved_facts": dict
    }

    try:
        response_data = await gemini.generate_json(prompt, system_instruction=system_instruction)
        
        # Schema validation
        is_valid, errors = validate_nested_schema(response_data, schema)
        if not is_valid:
            logger.warning(f"Conflict resolver initial schema failed: {errors}")
            retry_prompt = format_schema_retry_prompt(prompt, errors, response_data)
            response_data = await gemini.generate_json(retry_prompt, system_instruction=system_instruction)
            is_valid, errors = validate_nested_schema(response_data, schema)
            if not is_valid:
                logger.error("Conflict resolver schema failed twice. Assuming unresolvable.")
                return facts, True, {"error": "Schema failure during conflict resolution"}

    except Exception as e:
        logger.error(f"Conflict resolution LLM call failed: {e}")
        return facts, False, {"error": str(e)}

    unresolvable = response_data.get("unresolvable_conflict", False)
    resolved_facts = response_data.get("resolved_facts", facts)
    
    if response_data.get("conflicts_detected"):
        logger.info(f"⚖️ Conflicts detected & processed. Unresolvable={unresolvable}")
        
    return resolved_facts, unresolvable, response_data
