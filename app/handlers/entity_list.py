"""GraphIQ — EntityListHandler: filtered list query from PostgreSQL."""
from __future__ import annotations

from typing import Any

from app.core.dsl.intents import EntityListIntent
from app.handlers.base import BaseHandler, HandlerResult


class EntityListHandler(BaseHandler):
    """Handles EntityListIntent — filtered, sorted entity list."""

    store_type = "pg"

    def __init__(self, sql_builder: Any, pg_store: Any, neo4j_store: Any, registry: Any) -> None:
        super().__init__(pg_store, neo4j_store, registry)
        self.sql_builder = sql_builder

    def build_query(self, intent: EntityListIntent) -> tuple[str, tuple[Any, ...]]:  # type: ignore[override]
        entity = self.registry.get_entity_by_alias(intent.entity_type)
        resolved = intent.model_copy(update={"entity_type": entity.table_name})
        return self.sql_builder.build_list(resolved)

    async def execute(self, query: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        rows = await self.pg_store.fetch(query, *params)
        return [dict(row) for row in rows]

    def shape_result(self, raw_data: list[dict[str, Any]], intent: EntityListIntent) -> str:  # type: ignore[override]
        count = len(raw_data)
        if count == 0:
            return (
                f"No {intent.entity_type} found matching the given filters. "
                "Try broadening the date range or removing some filters."
            )
        preview = raw_data[:20]
        rows_str = "; ".join(
            "{" + ", ".join(f"{k}: {v}" for k, v in r.items() if v is not None) + "}"
            for r in preview
        )
        truncated_note = f" (showing first 20 of {count})" if count > 20 else ""
        return f"Found {count} {intent.entity_type}{truncated_note}: {rows_str}"

    async def handle(self, intent: EntityListIntent, context: Any) -> HandlerResult:  # type: ignore[override]
        result = await super().handle(intent, context)
        if not result.raw_data:
            return result

        entity = self.registry.get_entity_by_alias(intent.entity_type)
        pk_col = entity.primary_key[0]  # Take first PK for graph ID
        node_ids = []
        for row in result.raw_data:
            val = row.get(pk_col)
            if val:
                node_ids.append(str(val))

        # Distinct and limit to reasonable count for UI
        node_ids = list(dict.fromkeys(node_ids))[:100]
        return result.model_copy(update={"node_ids": node_ids})
