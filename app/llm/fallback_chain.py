"""GraphIQ — Fallback Chain: provider health registry and selection algorithm.

Implements:
- Per-provider health tracking (consecutive_fails, json_validity_rate)
- Circuit breaker: 3 fails → dead → cooldown (1min doubling to 15min max)
- Selection: filter dead/cooldown → prefer high json_validity → priority order
- Max 3 total attempts across providers per request
"""
from __future__ import annotations

import asyncio
import time
from datetime import datetime, timedelta
from typing import Any

import structlog

from app.core.config import settings
from app.core.exceptions import LLMError, ProviderError
from app.llm.client import LLMClient, ProviderHealth

logger = structlog.get_logger()

_CIRCUIT_BREAKER_THRESHOLD = 3       # Consecutive fails before dead
_COOLDOWN_START_SECONDS = 60         # Initial cooldown in seconds
_COOLDOWN_MAX_SECONDS = 900          # 15 minutes maximum
_MIN_JSON_VALIDITY_FOR_STRUCTURED = 0.6  # Below this → skip for structured calls


class FallbackChain:
    """Manages LLM provider health and selects the best available provider.

    Instantiated once at startup and shared across all requests.
    """

    def __init__(self, adapters: dict[str, LLMClient]) -> None:
        """Initialize with a dict of provider_name → adapter.

        Args:
            adapters: Pre-constructed adapter instances keyed by name.
        """
        self._adapters = adapters
        self._health: dict[str, ProviderHealth] = {
            name: ProviderHealth(name=name) for name in adapters
        }
        self._cooldown_intervals: dict[str, float] = {
            name: _COOLDOWN_START_SECONDS for name in adapters
        }
        self._priority = settings.provider_priority_list

    # ── Public call methods ───────────────────────────────────────────────────

    async def generate_structured(self, prompt: str) -> str:
        """Call the best available provider for structured JSON output.

        Args:
            prompt: Full intent extraction prompt.

        Returns:
            Raw LLM response text for parsing.

        Raises:
            LLMError: If all providers fail after max attempts.
        """
        return await self._call_with_fallback("structured", prompt)

    async def generate_text(self, prompt: str) -> str:
        """Call the best available provider for prose generation.

        Args:
            prompt: Full prose generation prompt.

        Returns:
            Generated prose text.

        Raises:
            LLMError: If all providers fail after max attempts.
        """
        return await self._call_with_fallback("text", prompt)

    # ── Internal machinery ────────────────────────────────────────────────────

    async def _call_with_fallback(self, call_type: str, prompt: str) -> str:
        """Try providers in priority order, max 3 total attempts.

        Args:
            call_type: "structured" or "text"
            prompt: Full prompt string.

        Returns:
            LLM response text.

        Raises:
            LLMError: Exhausted all attempts.
        """
        candidates = self._select_providers(call_type)
        errors: list[str] = []
        attempts = 0

        for provider_name in candidates:
            if attempts >= 3:
                break
            attempts += 1
            adapter = self._adapters[provider_name]
            health = self._health[provider_name]

            start = time.monotonic()
            try:
                if call_type == "structured":
                    result = await adapter.generate_structured(prompt)
                else:
                    result = await adapter.generate_text(prompt)

                elapsed = (time.monotonic() - start) * 1000
                self._record_success(provider_name, elapsed, is_structured=(call_type == "structured"))
                return result

            except ProviderError as e:
                elapsed = (time.monotonic() - start) * 1000
                self._record_failure(provider_name)
                errors.append(f"{provider_name}: {e.message}")
                logger.warning("llm_provider_failed", provider=provider_name, error=str(e))

        raise LLMError(
            f"All LLM providers exhausted after {attempts} attempt(s). "
            + " | ".join(errors)
        )

    def _select_providers(self, call_type: str) -> list[str]:
        """Return ordered list of usable providers for this call type."""
        now = datetime.utcnow()
        available: list[str] = []

        for name in self._priority:
            h = self._health.get(name)
            if h is None:
                continue
            if h.status == "dead":
                if h.cooldown_until and now < h.cooldown_until:
                    continue  # Still in cooldown
                # Try probing (allow one attempt to recover)
            if call_type == "structured" and h.json_validity_rate < _MIN_JSON_VALIDITY_FOR_STRUCTURED:
                continue
            available.append(name)

        # Sort: healthy before degraded/recovering, high json_validity first
        available.sort(
            key=lambda n: (
                self._health[n].status != "healthy",
                -self._health[n].json_validity_rate,
            )
        )
        return available

    def _record_success(self, name: str, latency_ms: float, is_structured: bool) -> None:
        h = self._health[name]
        h.consecutive_fails = 0
        h.status = "healthy"
        h.last_success = datetime.utcnow()
        h.cooldown_until = None
        self._cooldown_intervals[name] = _COOLDOWN_START_SECONDS  # Reset
        # Rolling avg latency (simple EMA)
        if h.avg_latency_ms == 0:
            h.avg_latency_ms = latency_ms
        else:
            h.avg_latency_ms = 0.9 * h.avg_latency_ms + 0.1 * latency_ms
        # JSON validity tracking
        if is_structured:
            h.calls_total += 1
            h.calls_valid_json += 1
            h.json_validity_rate = h.calls_valid_json / h.calls_total

    def _record_failure(self, name: str) -> None:
        h = self._health[name]
        h.consecutive_fails += 1
        if h.consecutive_fails >= _CIRCUIT_BREAKER_THRESHOLD:
            h.status = "dead"
            interval = self._cooldown_intervals[name]
            h.cooldown_until = datetime.utcnow() + timedelta(seconds=interval)
            # Double cooldown for next time, capped at max
            self._cooldown_intervals[name] = min(interval * 2, _COOLDOWN_MAX_SECONDS)
        # Track failed structured call toward json_validity_rate
        h.calls_total = max(h.calls_total, 1)
        h.json_validity_rate = h.calls_valid_json / h.calls_total

    def record_invalid_json(self, provider_name: str) -> None:
        """Call when a provider returned text but not valid JSON.

        Degrades that provider's json_validity_rate without incrementing
        consecutive_fails (provider responded, just not valid JSON).
        """
        h = self._health.get(provider_name)
        if h:
            h.calls_total += 1
            h.json_validity_rate = h.calls_valid_json / h.calls_total

    def get_health_summary(self) -> dict[str, Any]:
        """Return health state for all providers — used by /health endpoint."""
        return {
            name: {
                "status": h.status,
                "consecutive_fails": h.consecutive_fails,
                "avg_latency_ms": round(h.avg_latency_ms, 1),
                "json_validity_rate": round(h.json_validity_rate, 3),
                "cooldown_until": h.cooldown_until.isoformat() if h.cooldown_until else None,
            }
            for name, h in self._health.items()
        }
