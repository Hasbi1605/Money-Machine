"""
Shared Gemini API client.
Used by all pipelines (blog, video, SaaS).
Handles rate limiting, retries, and structured output.
Uses the new google.genai SDK.
Falls back to Groq / OpenRouter when Gemini quota exhausted.
"""

import asyncio
import re
import time
from typing import Optional, Dict, Any, List

from google import genai
from google.genai import types
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from loguru import logger

from shared.config import settings
from shared.backup_llm import backup_clients


class GeminiClient:
    """Wrapper around Google GenAI SDK with rate limiting and model fallback."""

    # Fallback models if primary is unavailable or rate-limited
    # Each model has its own separate daily quota on free tier
    FALLBACK_MODELS = [
        "gemini-2.5-flash-lite",
        "gemini-2.0-flash-001",
    ]

    def __init__(self):
        self.client = genai.Client(api_key=settings.gemini.api_key)
        self.model_name = settings.gemini.model_name
        self._last_request_time = 0.0
        self._request_interval = 60.0 / settings.gemini.rpm_limit  # seconds between requests
        self._lock = asyncio.Lock()
        # Track per-model exhaustion so we skip exhausted models
        self._exhausted_models: Dict[str, float] = {}  # model -> retry_after_timestamp

    async def _rate_limit(self):
        """Enforce rate limiting (RPM)."""
        async with self._lock:
            now = time.time()
            elapsed = now - self._last_request_time
            if elapsed < self._request_interval:
                wait_time = self._request_interval - elapsed
                logger.debug(f"Rate limiting: waiting {wait_time:.1f}s")
                await asyncio.sleep(wait_time)
            self._last_request_time = time.time()

    def _parse_retry_delay(self, err_str: str) -> float:
        """Extract retry delay (seconds) from a 429 error message."""
        # Pattern: "Please retry in 52.112394788s"
        match = re.search(r"retry in (\d+(?:\.\d+)?)s", err_str)
        if match:
            return float(match.group(1))
        return 60.0  # default 60s if can't parse

    def _is_model_exhausted(self, model: str) -> bool:
        """Check if a model's daily quota is exhausted."""
        if model not in self._exhausted_models:
            return False
        return time.time() < self._exhausted_models[model]

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=15, max=120))
    async def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> str:
        """Generate text from a prompt. Tries fallback models on 503 or 429 quota exhaustion."""
        await self._rate_limit()

        # Build list of models to try: primary + fallbacks, skip exhausted ones
        all_models = [self.model_name] + [
            m for m in self.FALLBACK_MODELS if m != self.model_name
        ]
        models_to_try = [m for m in all_models if not self._is_model_exhausted(m)]

        if not models_to_try:
            # All models exhausted — find the one with shortest wait
            soonest_model = min(self._exhausted_models, key=self._exhausted_models.get)
            wait_secs = max(0, self._exhausted_models[soonest_model] - time.time())
            logger.warning(f"All models exhausted. Waiting {wait_secs:.0f}s for {soonest_model}...")
            await asyncio.sleep(wait_secs + 5)
            models_to_try = [soonest_model]

        config = types.GenerateContentConfig(
            max_output_tokens=settings.gemini.max_output_tokens,
            temperature=temperature if temperature is not None else settings.gemini.temperature,
            system_instruction=system_instruction,
        )

        last_error = None
        for model in models_to_try:
            try:
                response = await asyncio.to_thread(
                    self.client.models.generate_content,
                    model=model,
                    contents=prompt,
                    config=config,
                )

                if response and response.text:
                    if model != self.model_name:
                        logger.info(f"Used fallback model: {model}")
                    logger.debug(f"Generated {len(response.text)} chars")
                    return response.text.strip()
                else:
                    logger.warning(f"Empty response from {model}")
                    continue

            except Exception as e:
                err_str = str(e)
                last_error = e

                if "503" in err_str or "UNAVAILABLE" in err_str:
                    logger.warning(f"Model {model} unavailable (503), trying next...")
                    continue

                elif "404" in err_str or "NOT_FOUND" in err_str:
                    logger.warning(f"Model {model} not found (404), trying next...")
                    # Permanently skip this model
                    self._exhausted_models[model] = time.time() + 86400
                    continue

                elif "429" in err_str or "RESOURCE_EXHAUSTED" in err_str:
                    retry_delay = self._parse_retry_delay(err_str)

                    # Check if it's a daily quota limit (not just per-minute)
                    if "PerDay" in err_str or "per_day" in err_str or retry_delay > 30:
                        # Daily quota exhausted — mark model and try fallback
                        self._exhausted_models[model] = time.time() + max(retry_delay, 60)
                        logger.warning(
                            f"Model {model} daily quota exhausted. "
                            f"Blocked for {retry_delay:.0f}s. Trying fallback..."
                        )
                        continue
                    else:
                        # Short rate limit — wait and retry same model
                        logger.info(f"Rate limited on {model}, waiting {retry_delay:.0f}s...")
                        await asyncio.sleep(retry_delay + 2)
                        continue

                else:
                    logger.error(f"Gemini API error ({model}): {e}")
                    raise

        # All Gemini models failed — try backup LLM providers (Groq, OpenRouter)
        for backup in backup_clients:
            if not backup.is_configured:
                continue
            logger.info(f"Trying backup provider: {backup.name}...")
            result = await backup.generate(
                prompt=prompt,
                system_instruction=system_instruction,
                temperature=temperature if temperature is not None else settings.gemini.temperature,
            )
            if result:
                logger.success(f"Backup {backup.name} succeeded ({len(result)} chars)")
                return result

        # All providers failed
        logger.error(f"All providers failed (Gemini + backups): {last_error}")
        raise last_error

    async def generate_json(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Generate and parse JSON response with robust error recovery."""
        import json

        json_prompt = f"""{prompt}

IMPORTANT: Respond ONLY with valid JSON. No markdown, no code blocks, no explanation.
Escape all special characters in strings properly (especially quotes and newlines)."""

        response = await self.generate(
            json_prompt,
            system_instruction=system_instruction,
            temperature=0.3,  # lower temp for structured output
        )

        # Clean response - remove markdown code blocks if present
        cleaned = response.strip()
        if cleaned.startswith("```"):
            lines = cleaned.split("\n")
            # Remove first and last lines (```json and ```)
            lines = [l for l in lines if not l.strip().startswith("```")]
            cleaned = "\n".join(lines)

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse failed, attempting repair: {e}")

            # Repair attempt 1: Fix truncated JSON by closing brackets
            repair = cleaned.rstrip()
            # Count open/close braces and brackets
            open_braces = repair.count('{') - repair.count('}')
            open_brackets = repair.count('[') - repair.count(']')
            # If inside a string value, close it first
            if repair.rstrip().endswith('\\'):
                repair = repair.rstrip()[:-1]
            # Try to detect if we're inside a string
            in_string = False
            last_quote = repair.rfind('"')
            if last_quote > 0:
                # Count unescaped quotes
                quote_count = 0
                i = 0
                while i < len(repair):
                    if repair[i] == '\\':
                        i += 2
                        continue
                    if repair[i] == '"':
                        quote_count += 1
                    i += 1
                if quote_count % 2 == 1:  # odd = unclosed string
                    repair += '"'

            repair += ']' * max(0, open_brackets)
            repair += '}' * max(0, open_braces)

            try:
                return json.loads(repair)
            except json.JSONDecodeError:
                pass

            # Repair attempt 2: Extract first valid JSON object
            brace_start = cleaned.find('{')
            if brace_start >= 0:
                depth = 0
                for i in range(brace_start, len(cleaned)):
                    if cleaned[i] == '{':
                        depth += 1
                    elif cleaned[i] == '}':
                        depth -= 1
                    if depth == 0:
                        try:
                            return json.loads(cleaned[brace_start:i+1])
                        except json.JSONDecodeError:
                            break

            logger.error(f"Failed to parse JSON after repair: {e}\nResponse: {cleaned[:200]}")
            raise

    async def generate_list(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
    ) -> List[str]:
        """Generate a list of items."""
        data = await self.generate_json(
            f"{prompt}\n\nReturn as JSON array of strings.",
            system_instruction=system_instruction,
        )
        if isinstance(data, list):
            return data
        if isinstance(data, dict) and "items" in data:
            return data["items"]
        return list(data.values()) if isinstance(data, dict) else [str(data)]


# Singleton
gemini = GeminiClient()
