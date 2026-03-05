"""
Shared Gemini API client.
Used by all pipelines (blog, video, SaaS).
Handles rate limiting, retries, and structured output.
Uses the new google.genai SDK.
"""

import asyncio
import time
from typing import Optional, Dict, Any, List

from google import genai
from google.genai import types
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type
from loguru import logger

from shared.config import settings


class GeminiClient:
    """Wrapper around Google GenAI SDK with rate limiting."""

    def __init__(self):
        self.client = genai.Client(api_key=settings.gemini.api_key)
        self.model_name = settings.gemini.model_name
        self._last_request_time = 0.0
        self._request_interval = 60.0 / settings.gemini.rpm_limit  # seconds between requests
        self._lock = asyncio.Lock()

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

    @retry(stop=stop_after_attempt(5), wait=wait_exponential(min=10, max=120))
    async def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> str:
        """Generate text from a prompt."""
        await self._rate_limit()

        try:
            config = types.GenerateContentConfig(
                max_output_tokens=settings.gemini.max_output_tokens,
                temperature=temperature if temperature is not None else settings.gemini.temperature,
                system_instruction=system_instruction,
            )

            response = await asyncio.to_thread(
                self.client.models.generate_content,
                model=self.model_name,
                contents=prompt,
                config=config,
            )

            if response and response.text:
                logger.debug(f"Generated {len(response.text)} chars")
                return response.text.strip()
            else:
                logger.warning("Empty response from Gemini")
                return ""

        except Exception as e:
            logger.error(f"Gemini API error: {e}")
            raise

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
