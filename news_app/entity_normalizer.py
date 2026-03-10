import re
import json
from typing import Dict, Any, List

def normalize_text(text: str) -> str:
    """
    Basic deterministic normalizer for common entity variations.
    """
    if not text:
        return text
        
    replacements = {
        r"\bMan Utd\b": "Manchester United",
        r"\bMan United\b": "Manchester United",
        r"\bMU\b": "Manchester United",
        r"\bSpurs\b": "Tottenham Hotspur"
    }
    
    normalized = text
    for pattern, replacement in replacements.items():
        normalized = re.sub(pattern, replacement, normalized, flags=re.IGNORECASE)
        
    return normalized

async def enforce_entity_consistency(draft_content: str, extracted_facts: Dict[str, Any]) -> List[str]:
    """
    Check if the draft's entities strictly match the extracted facts' entities.
    Returns a list of validation errors (inconsistencies), empty if valid.
    Uses LLM to detect contradictions.
    """
    from shared.gemini_client import gemini
    
    prompt = f"""Kamu adalah validator fakta jurnalistik.
Bandingkan FAKTA EKSTRAKSI dengan DRAFT ARTIKEL.
Apakah ada entitas (Nama, Tanggal, Angka/Skor, Lokasi) di dalam DRAFT yang *bertentangan* atau *tidak konsisten* dengan FAKTA EKSTRAKSI?
Misalnya: Fakta bilang skor 2-0, Draft bilang skor 2-1. Fakta bilang MU menang, Draft bilang MU seri. 

FAKTA EKSTRAKSI:
{json.dumps(extracted_facts, indent=2)}

DRAFT ARTIKEL (HTML):
{draft_content}

Output JSON HANYA daftar inkonsistensi (jika ada). Jika semua konsisten, berikan array kosong.
{{
  "inconsistencies": ["Penjelasan inkonsistensi 1"] // atau [] jika aman
}}
"""
    try:
        res = await gemini.generate_json(prompt, system_instruction="Deteksi kontradiksi fakta antara draft dan fact sheet secara ketat. Abaikan perbedaan gaya bahasa.")
        if res and isinstance(res.get("inconsistencies"), list):
            return res["inconsistencies"]
    except Exception as e:
        from loguru import logger
        logger.error(f"Entity consistency check failed: {e}")
    return []
