"""GraphIQ — Store Router: decides PostgreSQL vs Neo4j per intent."""
from __future__ import annotations

from typing import Literal

from app.core.dsl.intents import (
    AggregationIntent,
    BrokenFlowIntent,
    CompoundIntent,
    EntityListIntent,
    EntityLookupIntent,
    FlowTraceIntent,
    OutOfScopeIntent,
)
from app.core.registry.join_graph import JoinGraph
from app.core.registry.schema_registry import SchemaRegistry

StoreType = Literal["pg", "neo4j", "none"]


class StoreRouter:
    """Routes intents to the appropriate data store.

    Rules from instruction.md:
    - EntityLookup, EntityList, Aggregation → PostgreSQL
    - FlowTrace → Neo4j
    - BrokenFlow 1-hop → PostgreSQL (LEFT JOIN WHERE NULL)
    - BrokenFlow 2+ hops → Neo4j (OPTIONAL MATCH)
    - OutOfScope → none (no query)
    - Compound → handled per-step by CompoundHandler
    """

    def __init__(self, registry: SchemaRegistry, join_graph: JoinGraph) -> None:
        self._registry = registry
        self._join_graph = join_graph

    def route(self, intent: object) -> StoreType:
        """Determine which store should handle this intent.

        Args:
            intent: A resolved intent object.

        Returns:
            "pg", "neo4j", or "none".
        """
        if isinstance(intent, (EntityLookupIntent, EntityListIntent, AggregationIntent)):
            return "pg"

        if isinstance(intent, FlowTraceIntent):
            return "neo4j"

        if isinstance(intent, BrokenFlowIntent):
            return self._route_broken_flow(intent)

        if isinstance(intent, OutOfScopeIntent):
            return "none"

        if isinstance(intent, CompoundIntent):
            # CompoundHandler handles routing per step
            return "pg"  # placeholder — not used directly

        return "pg"

    def _route_broken_flow(self, intent: BrokenFlowIntent) -> StoreType:
        """Route BrokenFlow by hop count between source and target."""
        source_table = self._registry.resolve_entity_alias(intent.source_entity)
        target_table = self._registry.resolve_entity_alias(intent.expected_target)

        if source_table is None or target_table is None:
            # Fallback to PG; let handler/guardrail surface the error
            return "pg"

        hops = self._join_graph.hop_count(source_table, target_table)
        if hops == 1:
            return "pg"
        elif hops >= 2:
            return "neo4j"
        else:
            # No path found — let handler return an error
            return "pg"
