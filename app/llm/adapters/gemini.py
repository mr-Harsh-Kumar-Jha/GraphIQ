"""GraphIQ — Gemini LLM adapter (primary provider)."""
from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.exceptions import ProviderError
from app.llm.client import LLMClient

_GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent"


class GeminiAdapter(LLMClient):
    """Adapter for Google Gemini (gemini-2.0-flash)."""

    provider_name = "gemini"

    def __init__(self) -> None:
        self._api_key = settings.gemini_api_key
        self._client = httpx.AsyncClient(timeout=30.0)

    async def generate_structured(self, prompt: str, schema_description: str = "") -> str:
        """Call Gemini and return raw response text for JSON extraction."""
        full_prompt = prompt + ("\n\n" + schema_description if schema_description else "")
        return await self._call(full_prompt)

    async def generate_text(self, prompt: str) -> str:
        return await self._call(prompt)

    async def _call(self, prompt: str) -> str:
        if not self._api_key:
            raise ProviderError("gemini", "GEMINI_API_KEY not set")
        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.1, "maxOutputTokens": 2048},
        }
        try:
            resp = await self._client.post(
                _GEMINI_URL,
                params={"key": self._api_key},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            candidates = data.get("candidates", [])
            if not candidates:
                raise ProviderError("gemini", "Empty candidates in response")
            text = candidates[0]["content"]["parts"][0]["text"]
            return text
        except httpx.HTTPStatusError as e:
            raise ProviderError("gemini", f"HTTP {e.response.status_code}: {e.response.text[:200]}") from e
        except Exception as e:
            raise ProviderError("gemini", str(e)) from e

    async def health_check(self) -> bool:
        try:
            result = await self._call("Return the word OK")
            return len(result) > 0
        except Exception:
            return False
