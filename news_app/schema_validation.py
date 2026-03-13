from typing import Dict, List, Any, Tuple
from loguru import logger
import json

def validate_schema(data: Dict[str, Any], required_keys: List[str]) -> Tuple[bool, List[str]]:
    """
    Validate that the provided dictionary contains all required keys.
    Returns (is_valid, list_of_missing_keys).
    """
    if not isinstance(data, dict):
        return False, ["ROOT_IS_NOT_DICT"]
        
    missing_keys = [key for key in required_keys if key not in data]
    return len(missing_keys) == 0, missing_keys

def validate_nested_schema(data: Dict[str, Any], schema: Dict[str, type]) -> Tuple[bool, List[str]]:
    """
    Validate keys AND types based on a schema dict.
    Example schema: {'title': str, 'quotes': list, 'score': dict}
    Returns (is_valid, reasons_for_failure).
    """
    if not isinstance(data, dict):
        return False, ["Object is not a dictionary"]
        
    errors = []
    for key, expected_type in schema.items():
        if key not in data:
            errors.append(f"Missing required key: '{key}'")
        elif data[key] is not None and not isinstance(data[key], expected_type):
            errors.append(f"Key '{key}' should be type {expected_type.__name__}, got {type(data[key]).__name__}")
            
    return len(errors) == 0, errors

def format_schema_retry_prompt(original_prompt: str, errors: List[str], previous_broken_output: Any) -> str:
    """
    If the LLM fails to return the required structured schema, 
    generate an aggressive retry prompt specifically pointing out its mistakes.
    """
    try:
        if isinstance(previous_broken_output, (dict, list)):
            broken_str = json.dumps(previous_broken_output, indent=2, ensure_ascii=False)
        else:
            broken_str = str(previous_broken_output)
    except Exception:
        broken_str = "Unparseable generated output."

    error_bullet_points = "\n".join([f"- {err}" for err in errors])
    
    retry_prompt = f"""
{original_prompt}

==================================================
CRITICAL SYSTEM ERROR FROM YOUR PREVIOUS ATTEMPT
==================================================
Your previous generation FAILED our strict schema validation logic for the following reasons:
{error_bullet_points}

This is the broken output you generated previously:
```json
{broken_str}
```

You MUST fix these schema errors immediately. Do not omit required fields. 
Return exactly requested JSON schema.
"""
    return retry_prompt
