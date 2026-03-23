"""GraphIQ — Structured Output Parser: 4-stage LLM response pipeline.

Stage 1: JSON extraction (strip markdown fences, find { to })
Stage 2: JSON parse (json.loads)
Stage 3: Pydantic validation (discriminated union Intent)
Stage 4: Alias resolution check (resolved later by AliasResolver)

Retry logic per instruction.md:
- Stage 1-2 fail → retry with "Return ONLY valid JSON" instruction
- Stage 3 fail → retry with pydantic error feedback injected
- Stage 4 fail → retry with unknown alias + suggestions in feedback
"""
from __future__ import annotations

import json
import re
from typing import Any

import structlog
from pydantic import TypeAdapter, ValidationError

from app.core.dsl.intents import Intent
from app.core.exceptions import ParseError

logger = structlog.get_logger()

_INTENT_ADAPTER: TypeAdapter[Any] = TypeAdapter(Intent)

# Regex to find the outermost JSON object in a string
_JSON_OBJECT_RE = re.compile(r"\{.*\}", re.DOTALL)


class StructuredOutputParser:
    """Parses raw LLM text into a validated Intent object.

    The parser is stateless — call parse() per LLM response.
    Retry logic is coordinated by the caller (FallbackChain /
    QueryService) which re-calls generate_structured with the
    error feedback prompt before calling parse() again.
    """

    # ── Public API ────────────────────────────────────────────────────────────

    def parse(self, raw_text: str) -> tuple[Any, str | None]:
        """Run the 4-stage pipeline on raw LLM output.

        Args:
            raw_text: Raw text returned by the LLM adapter.

        Returns:
            (intent_object, error_feedback) where error_feedback is None
            on success, or a prompt string to inject for retry on failure.
        """
        # Stage 1: JSON extraction
        json_str = self._extract_json(raw_text)
        if json_str is None:
            return None, (
                "Your previous response could not be parsed as JSON. "
                "Return ONLY a valid JSON object. No markdown, no code fences, "
                "no explanation. Start your response with '{' and end with '}'."
            )

        # Stage 2: JSON parse
        parsed = self._parse_json(json_str)
        if parsed is None:
            return None, (
                "Your previous response was not valid JSON. "
                "Return ONLY a valid JSON object. No trailing commas, no comments. "
                f"Problematic snippet: {json_str[:100]!r}"
            )

        # Stage 3: Pydantic validation
        intent, pydantic_error = self._validate_pydantic(parsed)
        if intent is None:
            return None, (
                f"Your previous JSON was structurally invalid: {pydantic_error}. "
                "Fix only the listed issues and return the corrected JSON object."
            )

        return intent, None

    def build_parse_retry_prompt(self, original_prompt: str, feedback: str) -> str:
        """Inject error feedback into the prompt for a retry call.

        Args:
            original_prompt: The original intent extraction prompt.
            feedback: The error feedback string from parse().

        Returns:
            New prompt string with feedback appended.
        """
        return (
            original_prompt
            + f"\n\n--- PREVIOUS RESPONSE WAS INVALID ---\n{feedback}\n"
            "--- Correct the above issue and return a valid JSON object. ---"
        )

    # ── Private helpers ───────────────────────────────────────────────────────

    def _extract_json(self, text: str) -> str | None:
        """Stage 1: Strip markdown fences and extract raw JSON string."""
        # Remove ```json ... ``` or ``` ... ``` fences
        stripped = re.sub(r"```(?:json)?\s*", "", text)
        stripped = re.sub(r"```", "", stripped).strip()

        # Find first { to last }
        match = _JSON_OBJECT_RE.search(stripped)
        if match:
            return match.group(0)

        # Handle trailing commas (common LLM mistake)
        cleaned = re.sub(r",\s*([}\]])", r"\1", stripped)
        match2 = _JSON_OBJECT_RE.search(cleaned)
        return match2.group(0) if match2 else None

    def _parse_json(self, json_str: str) -> dict[str, Any] | None:
        """Stage 2: Parse JSON string to dict."""
        try:
            result = json.loads(json_str)
            if isinstance(result, dict):
                return result
            return None
        except json.JSONDecodeError:
            # Attempt to fix trailing commas
            try:
                cleaned = re.sub(r",\s*([}\]])", r"\1", json_str)
                return json.loads(cleaned)
            except json.JSONDecodeError:
                return None

    def _validate_pydantic(self, data: dict[str, Any]) -> tuple[Any, str | None]:
        """Stage 3: Validate dict against the Intent discriminated union."""
        try:
            intent = _INTENT_ADAPTER.validate_python(data)
            return intent, None
        except ValidationError as e:
            # Return concise error for feedback
            errors = e.errors(include_url=False)
            messages = [
                f"field '{'.'.join(str(loc) for loc in err['loc'])}': {err['msg']}"
                for err in errors[:3]
            ]
            return None, "; ".join(messages)
