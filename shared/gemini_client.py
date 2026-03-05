"""
Shared Gemini API client.
Used by all pipelines (blog, video, SaaS).
Handles rate limiting, retries, and structured output.
"""

import asyncio
import time
from typing import Optional, Dict, Any, List

import google.generativeai as genai
from tenacity import retry, stop_after_attempt, wait_exponential
from loguru import logger

from shared.config import settings


class GeminiClient:
    """Wrapper around Google Generative AI SDK with rate limiting."""

    def __init__(self):
        genai.configure(api_key=settings.gemini.api_key)
        self.model = genai.GenerativeModel(
            model_name=settings.gemini.model_name,
            generation_config=genai.GenerationConfig(
                max_output_tokens=settings.gemini.max_output_tokens,
                temperature=settings.gemini.temperature,
            ),
        )
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

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(min=4, max=60))
    async def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: Optional[float] = None,
    ) -> str:
        """Generate text from a prompt."""
        await self._rate_limit()

        try:
            model = self.model
            if system_instruction or temperature is not None:
                config = genai.GenerationConfig(
                    max_output_tokens=settings.gemini.max_output_tokens,
                    temperature=temperature or settings.gemini.temperature,
                )
                model = genai.GenerativeModel(
                    model_name=settings.gemini.model_name,
                    generation_config=config,
                    system_instruction=system_instruction,
                )

            response = await asyncio.to_thread(
                model.generate_content, prompt
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
        """Generate and parse JSON response."""
        import json

        json_prompt = f"""{prompt}

IMPORTANT: Respond ONLY with valid JSON. No markdown, no code blocks, no explanation."""

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
            logger.error(f"Failed to parse JSON: {e}\nResponse: {cleaned[:200]}")
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
