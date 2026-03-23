"""GraphIQ — Abstract LLM Client interface and ProviderHealth model."""
from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime
from typing import Literal

from pydantic import BaseModel


class ProviderHealth(BaseModel):
    """Tracks runtime health of a single LLM provider."""

    name: str
    status: Literal["healthy", "degraded", "dead"] = "healthy"
    consecutive_fails: int = 0
    avg_latency_ms: float = 0.0
    last_success: datetime | None = None
    json_validity_rate: float = 1.0   # 0.0-1.0, rolling over last 100 calls
    cooldown_until: datetime | None = None
    calls_total: int = 0
    calls_valid_json: int = 0         # For rolling json_validity_rate


class LLMClient(ABC):
    """Abstract interface for all LLM provider adapters.

    Each adapter (Gemini, Groq, OpenRouter) implements this interface,
    hiding SDK differences, auth, and response parsing.
    """

    provider_name: str = "unknown"

    @abstractmethod
    async def generate_structured(
        self, prompt: str, schema_description: str = ""
    ) -> str:
        """Call the LLM and return raw text for structured JSON extraction.

        Args:
            prompt: Full prompt including system context and user query.
            schema_description: Additional schema context appended to prompt.

        Returns:
            Raw LLM response text (to be parsed by StructuredOutputParser).

        Raises:
            ProviderError: If the API call fails.
        """
        ...

    @abstractmethod
    async def generate_text(self, prompt: str) -> str:
        """Call the LLM and return free-form prose.

        Args:
            prompt: Full prompt for prose generation.

        Returns:
            The generated prose string.

        Raises:
            ProviderError: If the API call fails.
        """
        ...

    @abstractmethod
    async def health_check(self) -> bool:
        """Return True if the provider is reachable."""
        ...
