"""GraphIQ — SchemaRegistry: the single source of truth accessor.

Wraps the static definitions from definitions.py and provides
typed lookup methods consumed by every other module.
"""
from __future__ import annotations

from app.core.registry.definitions import (
    ENTITY_CATALOG,
    ENTITY_ALIAS_MAP,
    FIELD_ALIAS_MAP,
    JOIN_EDGES,
    EntityDef,
    FieldDef,
    JoinEdge,
)
from app.core.exceptions import ValidationError


class SchemaRegistry:
    """Typed accessor for the O2C entity catalog, alias maps, and join edges.

    This class is instantiated once at startup and injected where needed.
    It is read-only — the underlying data comes from definitions.py.
    """

    def __init__(self) -> None:
        self._entities = ENTITY_CATALOG
        self._entity_alias_map = ENTITY_ALIAS_MAP
        self._field_alias_map = FIELD_ALIAS_MAP
        self._join_edges = JOIN_EDGES

    # ── Entity lookups ───────────────────────────────────────────────────────

    def get_entity_by_alias(self, alias: str) -> EntityDef:
        """Resolve a semantic entity alias to its EntityDef.

        Args:
            alias: Semantic alias such as "order", "invoice", etc.

        Returns:
            The resolved EntityDef.

        Raises:
            ValidationError: If the alias does not map to any known entity.
        """
        table_name = self._entity_alias_map.get(alias.lower())
        if table_name is None:
            raise ValidationError(
                f"Unknown entity alias: '{alias}'",
                detail=f"Known aliases: {', '.join(sorted(self._entity_alias_map.keys())[:20])} ...",
            )
        return self._entities[table_name]

    def get_entity_by_table(self, table_name: str) -> EntityDef:
        """Retrieve an EntityDef by exact table name.

        Args:
            table_name: Actual PostgreSQL table name.

        Returns:
            The resolved EntityDef.

        Raises:
            ValidationError: If the table is not in the catalog.
        """
        entity = self._entities.get(table_name)
        if entity is None:
            raise ValidationError(f"Unknown table: '{table_name}'")
        return entity

    def resolve_entity_alias(self, alias: str) -> str | None:
        """Return the canonical table_name for an alias, or None if unknown."""
        return self._entity_alias_map.get(alias.lower())

    @property
    def all_entities(self) -> dict[str, EntityDef]:
        """All entities keyed by table_name."""
        return self._entities

    @property
    def all_entity_aliases(self) -> list[str]:
        """All known entity alias strings."""
        return list(self._entity_alias_map.keys())

    # ── Field lookups ────────────────────────────────────────────────────────

    def get_field(self, table_name: str, field_name: str) -> FieldDef:
        """Retrieve a FieldDef by table and exact column name.

        Args:
            table_name: Exact PostgreSQL table name.
            field_name: Exact column name in that table.

        Returns:
            The resolved FieldDef.

        Raises:
            ValidationError: If the table or field does not exist.
        """
        entity = self.get_entity_by_table(table_name)
        field = entity.fields.get(field_name)
        if field is None:
            known = list(entity.fields.keys())
            raise ValidationError(
                f"Unknown field '{field_name}' on table '{table_name}'",
                detail=f"Known fields: {', '.join(known)}",
            )
        return field

    def resolve_field_alias(self, alias: str) -> tuple[str, str] | None:
        """Resolve a semantic field alias to (table_name, column_name).

        Args:
            alias: Semantic alias such as "billing_amount", "order_date".

        Returns:
            (table_name, column_name) tuple, or None if not found.
        """
        return self._field_alias_map.get(alias.lower())

    @property
    def all_field_aliases(self) -> list[str]:
        """All known field alias strings."""
        return list(self._field_alias_map.keys())

    # ── Join path access ─────────────────────────────────────────────────────

    @property
    def join_edges(self) -> list[JoinEdge]:
        """All legal join edges between tables."""
        return self._join_edges

    # ── Neo4j helpers ─────────────────────────────────────────────────────────

    def get_neo4j_label(self, table_name: str) -> str | None:
        """Return the Neo4j node label for a table, or None if not a graph node."""
        entity = self._entities.get(table_name)
        return entity.neo4j_label if entity else None

    def graph_node_tables(self) -> list[str]:
        """Return all table names that project as Neo4j nodes."""
        return [name for name, ent in self._entities.items() if ent.neo4j_label]
