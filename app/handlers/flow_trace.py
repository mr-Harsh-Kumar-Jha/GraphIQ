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
                f"No record found for {intent.start_entity} '{intent.start_id}' in the graph. "
                "Ensure the document exists and Neo4j sync has been run."
            )
        
        # We now always return at least the start node if it exists.
        # Check the longest path found.
        first = raw_data[0]
        nodes = first.get("nodes", [])
        labels = [n.get("labels", ["?"])[0] for n in nodes if isinstance(n, dict)]
        labels_chain = " → ".join(labels)
        
        target_reached = False
        if intent.target_entity:
            # Check if any node in the path matches the target label
            target_label = self.cypher_builder._safe_label(intent.target_entity)
            target_reached = any(target_label in n.get("labels", []) for n in nodes)

        summary = f"Found flow for {intent.start_entity} '{intent.start_id}': {labels_chain}."
        
        if intent.target_entity and not target_reached:
            summary += f" Note: No path reaching '{intent.target_entity}' was found; showing the longest available chain."
            
        return summary

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
