"""
Backup LLM clients (Groq + OpenRouter).
Used when Gemini API quota is exhausted.
Both use OpenAI-compatible API format via aiohttp.
"""

import asyncio
import json
import time
from typing import Optional, Dict, Any, List

import aiohttp
from loguru import logger

from shared.config import settings


class BackupLLMClient:
    """OpenAI-compatible API client for Groq and OpenRouter."""

    def __init__(
        self,
        name: str,
        api_key: str,
        base_url: str,
        models: List[str],
        max_tokens: int = 8192,
        rpm_limit: int = 30,
    ):
        self.name = name
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.models = models
        self.max_tokens = max_tokens
        self._last_request_time = 0.0
        self._request_interval = 60.0 / rpm_limit
        self._lock = asyncio.Lock()
        self._exhausted_models: Dict[str, float] = {}

    @property
    def is_configured(self) -> bool:
        """Check if API key is set."""
        return bool(self.api_key and self.api_key.strip())

    async def _rate_limit(self):
        """Enforce rate limiting."""
        async with self._lock:
            now = time.time()
            elapsed = now - self._last_request_time
            if elapsed < self._request_interval:
                wait_time = self._request_interval - elapsed
                await asyncio.sleep(wait_time)
            self._last_request_time = time.time()

    def _is_model_exhausted(self, model: str) -> bool:
        if model not in self._exhausted_models:
            return False
        return time.time() < self._exhausted_models[model]

    async def generate(
        self,
        prompt: str,
        system_instruction: Optional[str] = None,
        temperature: float = 0.7,
    ) -> Optional[str]:
        """Generate text using OpenAI-compatible chat completions API."""
        if not self.is_configured:
            return None

        await self._rate_limit()

        models_to_try = [m for m in self.models if not self._is_model_exhausted(m)]
        if not models_to_try:
            logger.debug(f"[{self.name}] All models exhausted")
            return None

        messages = []
        if system_instruction:
            messages.append({"role": "system", "content": system_instruction})
        messages.append({"role": "user", "content": prompt})

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        # OpenRouter requires these headers
        if self.name == "OpenRouter":
            headers["HTTP-Referer"] = "https://cikalnews.com"
            headers["X-Title"] = "CikalNews"

        for model in models_to_try:
            payload = {
                "model": model,
                "messages": messages,
                "max_tokens": self.max_tokens,
                "temperature": temperature,
            }

            try:
                async with aiohttp.ClientSession() as session:
                    url = f"{self.base_url}/chat/completions"
                    async with session.post(
                        url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=120)
                    ) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            text = data["choices"][0]["message"]["content"]
                            if text:
                                logger.info(f"[{self.name}] Generated {len(text)} chars with {model}")
                                return text.strip()
                            continue

                        elif resp.status == 429:
                            # Rate limited — mark model exhausted
                            body = await resp.text()
                            retry_after = 60  # default
                            try:
                                err_data = json.loads(body)
                                # Groq returns retry-after header
                                if "retry-after" in resp.headers:
                                    retry_after = float(resp.headers["retry-after"])
                            except Exception:
                                pass
                            self._exhausted_models[model] = time.time() + retry_after
                            logger.warning(
                                f"[{self.name}] {model} rate limited (429). "
                                f"Blocked for {retry_after:.0f}s"
                            )
                            continue

                        elif resp.status in (404, 400):
                            body = await resp.text()
                            logger.warning(f"[{self.name}] {model} error {resp.status}: {body[:200]}")
                            self._exhausted_models[model] = time.time() + 86400
                            continue

                        else:
                            body = await resp.text()
                            logger.warning(f"[{self.name}] {model} HTTP {resp.status}: {body[:200]}")
                            continue

            except asyncio.TimeoutError:
                logger.warning(f"[{self.name}] {model} timeout")
                continue
            except Exception as e:
                logger.warning(f"[{self.name}] {model} error: {e}")
                continue

        return None


# --- Singleton Instances ---

groq_client = BackupLLMClient(
    name="Groq",
    api_key=settings.groq.api_key,
    base_url=settings.groq.base_url,
    models=[settings.groq.model_name, settings.groq.fallback_model],
    max_tokens=settings.groq.max_tokens,
    rpm_limit=settings.groq.rpm_limit,
)

openrouter_client = BackupLLMClient(
    name="OpenRouter",
    api_key=settings.openrouter.api_key,
    base_url=settings.openrouter.base_url,
    models=[settings.openrouter.model_name, settings.openrouter.fallback_model],
    max_tokens=settings.openrouter.max_tokens,
    rpm_limit=20,  # OpenRouter free: 20 req/min
)

# Ordered list of backup clients
backup_clients: List[BackupLLMClient] = [groq_client, openrouter_client]
