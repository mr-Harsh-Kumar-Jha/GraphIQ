"""GraphIQ — Groq LLM adapter (secondary provider)."""
from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.exceptions import ProviderError
from app.llm.client import LLMClient

_GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
_GROQ_MODEL = "llama-3.3-70b-versatile"


class GroqAdapter(LLMClient):
    """Adapter for Groq (llama-3.3-70b-versatile)."""

    provider_name = "groq"

    def __init__(self) -> None:
        self._api_key = settings.groq_api_key
        self._client = httpx.AsyncClient(timeout=30.0)

    async def generate_structured(self, prompt: str, schema_description: str = "") -> str:
        full_prompt = prompt + ("\n\n" + schema_description if schema_description else "")
        return await self._call(full_prompt)

    async def generate_text(self, prompt: str) -> str:
        return await self._call(prompt)

    async def _call(self, prompt: str) -> str:
        if not self._api_key:
            raise ProviderError("groq", "GROQ_API_KEY not set")
        payload = {
            "model": _GROQ_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
            "max_tokens": 2048,
        }
        try:
            resp = await self._client.post(
                _GROQ_URL,
                headers={"Authorization": f"Bearer {self._api_key}"},
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as e:
            raise ProviderError("groq", f"HTTP {e.response.status_code}: {e.response.text[:200]}") from e
        except Exception as e:
            raise ProviderError("groq", str(e)) from e

    async def health_check(self) -> bool:
        try:
            result = await self._call("Return the word OK")
            return len(result) > 0
        except Exception:
            return False
