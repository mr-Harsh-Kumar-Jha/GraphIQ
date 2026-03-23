"""GraphIQ — RequestContext: per-request state carrier."""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from app.supervision.event_bus import EventBus


class RequestContext:
    """Carries all state for a single query lifecycle.

    Passed to every component in the pipeline. Components emit events
    through this object, which routes to the shared EventBus.
    """

    def __init__(self, question: str, event_bus: EventBus) -> None:
        self.request_id: str = str(uuid.uuid4())
        self.question: str = question
        self.timestamp: datetime = datetime.utcnow()
        self.event_bus: EventBus = event_bus
        # State accumulated during processing
        self.intent_raw: str | None = None
        self.intent_validated: Any = None
        self.corrections_applied: list[dict[str, Any]] = []
        self.guardrail_result: str | None = None
        self.guardrail_detail: str | None = None
        self.query_generated: str | None = None
        self.query_params: Any = None
        self.store_used: str | None = None
        self.query_ms: int = 0
        self.result_row_count: int = 0
        self.result_truncated: bool = False
        self.prose_answer: str | None = None
        self.llm_provider_used: str | None = None
        self.total_latency_ms: int = 0
        self.error_type: str | None = None
        self.error_detail: str | None = None

    async def emit(self, event_type: str, payload: dict[str, Any] | None = None) -> None:
        """Emit an event on the shared bus.

        Args:
            event_type: Event name.
            payload: Optional event data.
        """
        base = {"request_id": self.request_id, "event": event_type}
        full_payload = {**base, **(payload or {})}
        await self.event_bus.emit(event_type, full_payload)
