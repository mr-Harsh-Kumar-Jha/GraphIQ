"""GraphIQ — Cypher Builder for Neo4j traversal queries.

All values are parameterized. Node labels and relationship types
come from the schema registry — never from user input.
"""
from __future__ import annotations

from typing import Any

from app.core.dsl.intents import BrokenFlowIntent, FlowTraceIntent
from app.core.exceptions import QueryBuildError


# Neo4j O2C relationship type map  (source_label → (rel_type, target_label))
_O2C_REL_MAP: dict[str, tuple[str, str]] = {
    "Customer":    ("PLACED",        "SalesOrder"),
    "SalesOrder":  ("DELIVERED_BY",  "Delivery"),
    "Delivery":    ("BILLED_BY",     "Invoice"),
    "Invoice":     ("POSTED_AS",     "JournalEntry"),
    "JournalEntry": ("CLEARED_BY",   "Payment"),
}


class CypherBuilder:
    """Builds parameterized Cypher queries for Neo4j.

    Node labels and relationship types come from the registry constants —
    never from user-supplied strings.
    """

    def build_flow_trace(self, intent: FlowTraceIntent) -> tuple[str, dict[str, Any]]:
        """Build a variable-length path traversal for FlowTraceIntent.
        
        Uses a robust longest-path approach: matches all reachable nodes up to max_depth
        and returns the most complete path(s).
        """
        start_label = self._safe_label(intent.start_entity)
        params: dict[str, Any] = {
            "start_id": intent.start_id,
        }
        max_depth = intent.max_depth

        # Use a more robust query that finds as many nodes as possible
        # even if it doesn't reach a specific end node.
        cypher = (
            f"MATCH (start:{start_label} {{id: $start_id}})\n"
            f"MATCH path = (start)-[*0..{max_depth}]->(end)\n"
            "RETURN nodes(path) AS nodes, relationships(path) AS rels\n"
            "ORDER BY size(nodes) DESC\n"
            "LIMIT 5"
        )

        return cypher, params

    def build_broken_flow_nhop(
        self, intent: BrokenFlowIntent
    ) -> tuple[str, dict[str, Any]]:
        """Build a query to find entities disconnected from a target entity type."""
        source_label = self._safe_label(intent.source_entity)
        target_label = self._safe_label(intent.expected_target)
        params: dict[str, Any] = {"limit": intent.limit}

        # Use bi-directional path check to find orphans (missing ancestor OR descendant)
        cypher = (
            f"MATCH (source:{source_label})\n"
            f"WHERE NOT EXISTS {{\n"
            f"  MATCH (source)-[*1..5]-(target:{target_label})\n"
            "}\n"
            "RETURN source.id AS source_id\n"
            "LIMIT $limit"
        )

        return cypher, params

    # ── Private helpers ───────────────────────────────────────────────────────

    # Whitelist of valid Neo4j labels (prevents Cypher injection)
    _VALID_LABELS: frozenset[str] = frozenset({
        "Customer", "SalesOrder", "Delivery", "Invoice",
        "JournalEntry", "Payment", "Product", "Plant",
    })

    def _safe_label(self, label: str) -> str:
        """Validate a Neo4j label against the whitelist.

        Args:
            label: Proposed Neo4j label (should be resolved from registry).

        Returns:
            The validated label string.

        Raises:
            QueryBuildError: If label is not in the allowed whitelist.
        """
        # Normalize common aliases to Neo4j labels
        _alias_to_label: dict[str, str] = {
            "order": "SalesOrder",
            "orders": "SalesOrder",
            "salesorder": "SalesOrder",
            "delivery": "Delivery",
            "deliveries": "Delivery",
            "invoice": "Invoice",
            "invoices": "Invoice",
            "billing": "Invoice",
            "payment": "Payment",
            "payments": "Payment",
            "customer": "Customer",
            "customers": "Customer",
            "journal": "JournalEntry",
            "journalentry": "JournalEntry",
            "product": "Product",
            "products": "Product",
            "plant": "Plant",
            "plants": "Plant",
        }
        normalized = _alias_to_label.get(label.lower(), label)
        if normalized not in self._VALID_LABELS:
            raise QueryBuildError(
                f"'{label}' is not a valid graph node type. "
                f"Valid types: {', '.join(sorted(self._VALID_LABELS))}"
            )
        return normalized

    def _find_rel_type(self, source_label: str, target_label: str) -> str:
        """Look up the relationship type for a source → target pair.

        Args:
            source_label: Validated Neo4j source label.
            target_label: Validated Neo4j target label.

        Returns:
            The relationship type string (e.g. "PLACED").

        Raises:
            QueryBuildError: If no known relationship exists.
        """
        mapping = _O2C_REL_MAP.get(source_label)
        if mapping and mapping[1] == target_label:
            return mapping[0]
        # Allow any relationship type with wildcard
        raise QueryBuildError(
            f"No direct O2C relationship from '{source_label}' to '{target_label}'. "
            f"Known paths: {', '.join(f'{s} → {t}' for s, (_, t) in _O2C_REL_MAP.items())}"
        )
