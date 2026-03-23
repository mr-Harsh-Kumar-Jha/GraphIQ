"""GraphIQ — BrokenFlowHandler: missing downstream entity detection.

Routes to PostgreSQL (1-hop LEFT JOIN WHERE NULL) or
Neo4j (2+ hop OPTIONAL MATCH) based on StoreRouter.
"""
from __future__ import annotations

from typing import Any

from app.core.dsl.intents import BrokenFlowIntent
from app.handlers.base import BaseHandler, HandlerResult
from app.query.store_router import StoreRouter


class BrokenFlowHandler(BaseHandler):
    """Handles BrokenFlowIntent — finds entities missing downstream steps."""

    def __init__(
        self,
        sql_builder: Any,
        cypher_builder: Any,
        store_router: StoreRouter,
        pg_store: Any,
        neo4j_store: Any,
        registry: Any,
        join_graph: Any,
    ) -> None:
        super().__init__(pg_store, neo4j_store, registry)
        self.sql_builder = sql_builder
        self.cypher_builder = cypher_builder
        self.store_router = store_router
        self.join_graph = join_graph

    def build_query(self, intent: BrokenFlowIntent) -> tuple[Any, Any]:  # type: ignore[override]
        store = self.store_router.route(intent)
        if store == "neo4j":
            self.store_type = "neo4j"
            return self.cypher_builder.build_broken_flow_nhop(intent)
        else:
            self.store_type = "pg"
            # Resolve tables and join columns for LEFT JOIN
            source_entity = self.registry.get_entity_by_alias(intent.source_entity)
            target_entity = self.registry.get_entity_by_alias(intent.expected_target)
            path = self.join_graph.find_path(source_entity.table_name, target_entity.table_name)
            edge = path.edges[0]
            return self.sql_builder.build_broken_flow_1hop(
                intent,
                source_table=source_entity.table_name,
                target_table=target_entity.table_name,
                join_col_source=edge.from_column,
                join_col_target=edge.to_column,
            )

    async def execute(self, query: Any, params: Any) -> list[dict[str, Any]]:
        if self.store_type == "neo4j":
            return await self.neo4j_store.run_query(query, params)
        rows = await self.pg_store.fetch(query, *params)
        return [dict(row) for row in rows]

    def shape_result(self, raw_data: list[dict[str, Any]], intent: BrokenFlowIntent) -> str:  # type: ignore[override]
        count = len(raw_data)
        if count == 0:
            return (
                f"All {intent.source_entity} entities have an associated {intent.expected_target}. "
                "No gaps detected."
            )
        # Show up to 5 oldest examples
        oldest = raw_data[:5]
        examples = "; ".join(
            str(r.get("source_id") or r.get(list(r.keys())[0], "?"))
            for r in oldest
        )
        return (
            f"{count} {intent.source_entity}(s) have no associated {intent.expected_target}. "
            f"{'Oldest' if count > 1 else 'Example'}: {examples}."
        )

    async def handle(self, intent: BrokenFlowIntent, context: Any) -> HandlerResult:  # type: ignore[override]
        result = await super().handle(intent, context)
        node_ids = []
        for r in result.raw_data:
            sid = r.get("source_id") or (list(r.values())[0] if r else None)
            if sid:
                node_ids.append(str(sid))
        return result.model_copy(update={"node_ids": node_ids})
