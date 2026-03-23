"""GraphIQ — custom exception hierarchy.

All exceptions inherit from O2CBaseError so callers can catch at
any granularity they need.
"""
from __future__ import annotations


class O2CBaseError(Exception):
    """Root exception for all GraphIQ errors."""

    def __init__(self, message: str, *, detail: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail


# ── LLM errors ───────────────────────────────────────────────────────────────

class LLMError(O2CBaseError):
    """All LLM-related failures."""


class ProviderError(LLMError):
    """A specific LLM provider failed."""

    def __init__(self, provider: str, message: str, *, detail: str | None = None) -> None:
        super().__init__(f"[{provider}] {message}", detail=detail)
        self.provider = provider


class ParseError(LLMError):
    """Structured output could not be parsed after retries."""


# ── Query errors ─────────────────────────────────────────────────────────────

class QueryBuildError(O2CBaseError):
    """SQL or Cypher assembly failed."""


class StoreError(O2CBaseError):
    """Database execution failed."""


# ── Validation / guardrail errors ────────────────────────────────────────────

class GuardrailError(O2CBaseError):
    """Guardrail chain rejected the intent.

    Note: this is expected business logic, not a system failure.
    """

    def __init__(
        self,
        guard_name: str,
        user_message: str,
        *,
        suggestions: list[str] | None = None,
    ) -> None:
        super().__init__(user_message)
        self.guard_name = guard_name
        self.user_message = user_message
        self.suggestions = suggestions or []


class ValidationError(O2CBaseError):
    """DSL / alias validation failure."""
