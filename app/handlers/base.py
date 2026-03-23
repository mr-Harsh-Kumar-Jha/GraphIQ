"""GraphIQ — BaseHandler abstract class and HandlerResult model."""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

from pydantic import BaseModel


class HandlerResult(BaseModel):
    """Standardized result from any intent handler."""

    prose_context: str       # Compact summary for the prose LLM
    raw_data: list[dict[str, Any]]
    row_count: int
    truncated: bool
    store_used: str          # "pg" or "neo4j" or "none"
    query_ms: int
    node_ids: list[str] = []  # Graph node IDs for frontend highlight
    edge_sequence: list[str] = []  # Ordered node IDs for FlowTrace animation

    model_config = {"arbitrary_types_allowed": True}


class BaseHandler(ABC):
    """Abstract base for all intent handlers.

    Handlers are stateless — instantiated once at startup and called
    concurrently. All dependencies are injected via constructor.
    """

    store_type: str = "pg"

    def __init__(self, pg_store: Any, neo4j_store: Any, registry: Any) -> None:
        self.pg_store = pg_store
        self.neo4j_store = neo4j_store
        self.registry = registry

    async def handle(self, intent: Any, context: Any) -> HandlerResult:
        """Execute the full handler lifecycle: build → execute → shape.

        Args:
            intent: Resolved and validated intent object.
            context: RequestContext for event emission.

        Returns:
            HandlerResult with prose context, raw data, and metadata.
        """
        start = time.monotonic()
        query, params = self.build_query(intent)
        raw_data = await self.execute(query, params)
        elapsed_ms = int((time.monotonic() - start) * 1000)
        prose_context = self.shape_result(raw_data, intent)

        has_limit = hasattr(intent, "limit") and intent.limit is not None
        truncated = has_limit and len(raw_data) >= intent.limit

        return HandlerResult(
            prose_context=prose_context,
            raw_data=raw_data,
            row_count=len(raw_data),
            truncated=truncated,
            store_used=self.store_type,
            query_ms=elapsed_ms,
        )

    @abstractmethod
    def build_query(self, intent: Any) -> tuple[Any, Any]:
        """Build the query (SQL string + params, or Cypher + params dict)."""
        ...

    @abstractmethod
    async def execute(self, query: Any, params: Any) -> list[dict[str, Any]]:
        """Execute the built query and return rows as list of dicts."""
        ...

    @abstractmethod
    def shape_result(self, raw_data: list[dict[str, Any]], intent: Any) -> str:
        """Produce a compact prose context string for the LLM."""
        ...
