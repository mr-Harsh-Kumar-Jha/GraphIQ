"""GraphIQ — EntityLookupHandler: single-entity PK fetch from PostgreSQL."""
from __future__ import annotations

import json
from typing import Any

from app.core.dsl.intents import EntityLookupIntent
from app.handlers.base import BaseHandler, HandlerResult
from app.core.exceptions import QueryBuildError


class EntityLookupHandler(BaseHandler):
    """Handles EntityLookupIntent — single document lookup by PK."""

    store_type = "pg"

    def __init__(self, sql_builder: Any, pg_store: Any, neo4j_store: Any, registry: Any) -> None:
        super().__init__(pg_store, neo4j_store, registry)
        self.sql_builder = sql_builder

    def build_query(self, intent: EntityLookupIntent) -> tuple[str, tuple[Any, ...]]:  # type: ignore[override]
        # Resolve entity alias → table name
        entity = self.registry.get_entity_by_alias(intent.entity_type)
        resolved = intent.model_copy(update={"entity_type": entity.table_name})
        return self.sql_builder.build_lookup(resolved)

    async def execute(self, query: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        rows = await self.pg_store.fetch(query, *params)
        return [dict(row) for row in rows]

    def shape_result(self, raw_data: list[dict[str, Any]], intent: EntityLookupIntent) -> str:  # type: ignore[override]
        if not raw_data:
            return f"No {intent.entity_type} found with identifier '{intent.identifier}'."
        row = raw_data[0]
        pairs = ", ".join(f"{k}: {v}" for k, v in row.items() if v is not None)
        return f"Found {intent.entity_type} '{intent.identifier}': {pairs}"

    async def handle(self, intent: EntityLookupIntent, context: Any) -> HandlerResult:  # type: ignore[override]
        result = await super().handle(intent, context)
        # Attach node_id for graph highlight
        if result.raw_data:
            entity = self.registry.get_entity_by_alias(intent.entity_type)
            pk_col = entity.primary_key[0]
            node_id = str(result.raw_data[0].get(pk_col, intent.identifier))
            result = result.model_copy(update={"node_ids": [node_id]})
        return result
