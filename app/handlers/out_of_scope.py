"""GraphIQ — OutOfScopeHandler: returns rejection without any DB query."""
from __future__ import annotations

import time
from typing import Any

from app.core.dsl.intents import OutOfScopeIntent
from app.handlers.base import BaseHandler, HandlerResult


class OutOfScopeHandler(BaseHandler):
    """Handles OutOfScopeIntent — no query execution, returns rejection message."""

    store_type = "none"

    def build_query(self, intent: Any) -> tuple[None, None]:
        return None, None

    async def execute(self, query: Any, params: Any) -> list[dict[str, Any]]:
        return []

    def shape_result(self, raw_data: list[dict[str, Any]], intent: OutOfScopeIntent) -> str:  # type: ignore[override]
        msg = (
            "This system is designed only for O2C dataset queries. "
            "Try asking about orders, deliveries, billing, or payments."
        )
        if intent.suggestion:
            msg += f" Suggestion: {intent.suggestion}"
        return msg

    async def handle(self, intent: OutOfScopeIntent, context: Any) -> HandlerResult:  # type: ignore[override]
        prose_ctx = self.shape_result([], intent)
        return HandlerResult(
            prose_context=prose_ctx,
            raw_data=[],
            row_count=0,
            truncated=False,
            store_used="none",
            query_ms=0,
        )
