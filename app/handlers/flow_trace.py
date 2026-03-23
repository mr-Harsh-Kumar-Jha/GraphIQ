"""GraphIQ — FlowTraceHandler: O2C path traversal via Neo4j."""
from __future__ import annotations

from typing import Any

from app.core.dsl.intents import FlowTraceIntent
from app.handlers.base import BaseHandler, HandlerResult


class FlowTraceHandler(BaseHandler):
    """Handles FlowTraceIntent — variable-length O2C path traversal."""

    store_type = "neo4j"

    def __init__(self, cypher_builder: Any, pg_store: Any, neo4j_store: Any, registry: Any) -> None:
        super().__init__(pg_store, neo4j_store, registry)
        self.cypher_builder = cypher_builder

    def build_query(self, intent: FlowTraceIntent) -> tuple[str, dict[str, Any]]:  # type: ignore[override]
        return self.cypher_builder.build_flow_trace(intent)

    async def execute(self, query: str, params: dict[str, Any]) -> list[dict[str, Any]]:  # type: ignore[override]
        return await self.neo4j_store.run_query(query, params)

    def shape_result(self, raw_data: list[dict[str, Any]], intent: FlowTraceIntent) -> str:  # type: ignore[override]
        if not raw_data:
            return (
                f"No flow path found from {intent.start_entity} '{intent.start_id}' "
                f"to {intent.target_entity or 'any downstream entity'}."
            )
        path_count = len(raw_data)
        # Build a linearized description of the first path
        first = raw_data[0]
        nodes = first.get("nodes", [])
        labels_chain = " → ".join(
            (n.get("labels", ["?"])[0] if isinstance(n, dict) else "?") for n in nodes
        )
        return (
            f"Found {path_count} flow path(s) from {intent.start_entity} '{intent.start_id}'. "
            f"Primary path: {labels_chain}. "
            + (f"Showing {path_count} path(s). " if path_count > 1 else "")
        )

    async def handle(self, intent: FlowTraceIntent, context: Any) -> HandlerResult:  # type: ignore[override]
        result = await super().handle(intent, context)
        # Extract ordered node IDs for frontend edge animation
        edge_seq: list[str] = []
        node_ids: list[str] = []
        for path in result.raw_data:
            for node in path.get("nodes", []):
                nid = str(node.get("id") or node.get("properties", {}).get("id", ""))
                if nid and nid not in node_ids:
                    node_ids.append(nid)
        edge_seq = node_ids  # Same order for sequential animation
        return result.model_copy(update={"node_ids": node_ids, "edge_sequence": edge_seq})
