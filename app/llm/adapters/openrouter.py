"""GraphIQ — OpenRouter LLM adapter (tertiary provider)."""
from __future__ import annotations

import httpx

from app.core.config import settings
from app.core.exceptions import ProviderError
from app.llm.client import LLMClient

_OPENROUTER_URL = "https://openrouter.ai/api/v1/chat/completions"
_OPENROUTER_MODEL = "arcee-ai/trinity-large-preview:free"


class OpenRouterAdapter(LLMClient):
    """Adapter for OpenRouter (free tier — arcee-ai/trinity-large-preview)."""

    provider_name = "openrouter"

    def __init__(self) -> None:
        self._api_key = settings.openrouter_api_key
        self._client = httpx.AsyncClient(timeout=45.0)

    async def generate_structured(self, prompt: str, schema_description: str = "") -> str:
        full_prompt = prompt + ("\n\n" + schema_description if schema_description else "")
        return await self._call(full_prompt)

    async def generate_text(self, prompt: str) -> str:
        return await self._call(prompt)

    async def _call(self, prompt: str) -> str:
        if not self._api_key:
            raise ProviderError("openrouter", "OPENROUTER_API_KEY not set")
        payload = {
            "model": _OPENROUTER_MODEL,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.1,
        }
        try:
            resp = await self._client.post(
                _OPENROUTER_URL,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "HTTP-Referer": "https://graphiq.app",
                },
                json=payload,
            )
            resp.raise_for_status()
            data = resp.json()
            return data["choices"][0]["message"]["content"]
        except httpx.HTTPStatusError as e:
            raise ProviderError("openrouter", f"HTTP {e.response.status_code}: {e.response.text[:200]}") from e
        except Exception as e:
            raise ProviderError("openrouter", str(e)) from e

    async def health_check(self) -> bool:
        try:
            result = await self._call("Return the word OK")
            return len(result) > 0
        except Exception:
            return False
