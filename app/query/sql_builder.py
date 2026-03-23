"""GraphIQ — SQL Builder: parameterized clause-by-clause assembly.

SAFETY INVARIANTS (never violate):
- ALL user values go through $N parameters — never string-interpolated.
- ALL table/column names come from the registry whitelist — never from user input.
- LIMIT is always present (hard cap at MAX_QUERY_LIMIT).
- No subqueries, raw SQL fragments, or dynamic table names from user input.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any

from app.core.dsl.enums import AggFunction, OperatorType
from app.core.dsl.filters import Filter, SortSpec
from app.core.dsl.intents import (
    AggregationIntent,
    BrokenFlowIntent,
    EntityListIntent,
    EntityLookupIntent,
)
from app.core.exceptions import QueryBuildError
from app.core.registry.schema_registry import SchemaRegistry
from app.core.registry.definitions import EntityDef

MAX_QUERY_LIMIT = 500

# Operator → SQL fragment (LHS is injected by builder, never user value)
_OP_MAP: dict[OperatorType, str] = {
    OperatorType.eq: "= {}",
    OperatorType.neq: "!= {}",
    OperatorType.gt: "> {}",
    OperatorType.gte: ">= {}",
    OperatorType.lt: "< {}",
    OperatorType.lte: "<= {}",
    OperatorType.like: "ILIKE {}",
    OperatorType.in_: "= ANY({})",   # asyncpg handles list params via ANY($N)
    OperatorType.between: "BETWEEN {} AND {}",  # special-cased below
}

# SQL aggregate function names
_AGG_MAP: dict[AggFunction, str] = {
    AggFunction.sum: "SUM",
    AggFunction.count: "COUNT",
    AggFunction.avg: "AVG",
    AggFunction.min: "MIN",
    AggFunction.max: "MAX",
    AggFunction.count_distinct: "COUNT(DISTINCT {})",  # special-cased
}


@dataclass
class _QueryState:
    """Mutable helper for building parameterized queries."""

    params: list[Any] = field(default_factory=list)

    def add(self, value: Any) -> str:
        """Append a parameter and return its $N placeholder."""
        self.params.append(value)
        return f"${len(self.params)}"

    def add_between(self, low: Any, high: Any) -> tuple[str, str]:
        return self.add(low), self.add(high)


class SQLBuilder:
    """Builds safe, parameterized SQL for PostgreSQL via asyncpg.

    Constructed once at startup and injected into handlers.
    All methods accept resolved (table, column) references from the registry.
    """

    def __init__(self, registry: SchemaRegistry, max_limit: int = MAX_QUERY_LIMIT) -> None:
        self._registry = registry
        self._max_limit = max_limit

    # ── Public build methods ──────────────────────────────────────────────────

    def build_lookup(self, intent: EntityLookupIntent) -> tuple[str, tuple[Any, ...]]:
        """Build a PK-lookup query.

        Args:
            intent: Resolved EntityLookupIntent (entity_type is the table name).

        Returns:
            (sql_string, params_tuple) for asyncpg.
        """
        entity = self._registry.get_entity_by_table(intent.entity_type)
        state = _QueryState()

        select_cols = self._select_columns(entity, intent.fields)
        pk_col = entity.primary_key[0]  # Single PK for lookup entities
        placeholder = state.add(intent.identifier)

        sql = (
            f"SELECT {select_cols}\n"
            f"FROM {entity.table_name}\n"
            f"WHERE {entity.table_name}.{pk_col} = {placeholder}\n"
            f"LIMIT 1"
        )
        return sql, tuple(state.params)

    def build_list(self, intent: EntityListIntent) -> tuple[str, tuple[Any, ...]]:
        """Build a filtered list query.

        Args:
            intent: Resolved EntityListIntent.

        Returns:
            (sql_string, params_tuple) for asyncpg.
        """
        entity = self._registry.get_entity_by_table(intent.entity_type)
        state = _QueryState()

        select_cols = self._select_columns(entity, intent.fields)
        where_clause = self._build_where(intent.filters, entity, state)
        order_clause = self._build_order(intent.sort_by, entity)
        limit = min(intent.limit, self._max_limit)

        parts = [
            f"SELECT {select_cols}",
            f"FROM {entity.table_name}",
        ]
        if where_clause:
            parts.append(f"WHERE {where_clause}")
        if order_clause:
            parts.append(f"ORDER BY {order_clause}")
        parts.append(f"LIMIT {limit}")  # LIMIT is an integer, not a param

        return "\n".join(parts), tuple(state.params)

    def build_aggregation(self, intent: AggregationIntent) -> tuple[str, tuple[Any, ...]]:
        """Build a GROUP BY aggregation query.

        Args:
            intent: Resolved AggregationIntent.

        Returns:
            (sql_string, params_tuple) for asyncpg.
        """
        entity = self._registry.get_entity_by_table(intent.entity_type)
        state = _QueryState()

        # Resolve measure field
        measure_col = self._resolve_col(entity, intent.measure)
        agg_expr = self._agg_expression(intent.agg_fn, measure_col)

        # Resolve group-by fields
        group_cols = [self._resolve_col(entity, f) for f in intent.group_by]
        qual_group_cols = [f"{entity.table_name}.{c}" for c in group_cols]

        # SELECT: group columns + aggregate expression
        select_parts = qual_group_cols + [f"{agg_expr} AS agg_value"]
        select_sql = ", ".join(select_parts)

        where_clause = self._build_where(intent.filters, entity, state)
        group_sql = ", ".join(qual_group_cols) if qual_group_cols else None

        # ORDER BY: default to agg_value DESC unless overridden
        if intent.sort_by:
            if intent.sort_by.field in ("agg_value", intent.measure):
                order_sql = f"agg_value {intent.sort_by.order.value.upper()}"
            else:
                col = self._resolve_col(entity, intent.sort_by.field)
                order_sql = f"{entity.table_name}.{col} {intent.sort_by.order.value.upper()}"
        else:
            order_sql = "agg_value DESC"

        limit = min(intent.limit, 100)

        parts = [f"SELECT {select_sql}", f"FROM {entity.table_name}"]
        if where_clause:
            parts.append(f"WHERE {where_clause}")
        if group_sql:
            parts.append(f"GROUP BY {group_sql}")
        parts.append(f"ORDER BY {order_sql}")
        parts.append(f"LIMIT {limit}")

        return "\n".join(parts), tuple(state.params)

    def build_broken_flow_1hop(
        self,
        intent: BrokenFlowIntent,
        source_table: str,
        target_table: str,
        join_col_source: str,
        join_col_target: str,
    ) -> tuple[str, tuple[Any, ...]]:
        """Build a LEFT JOIN WHERE NULL query for 1-hop broken flow detection.

        Args:
            intent: Resolved BrokenFlowIntent.
            source_table: The source entity table.
            target_table: The expected downstream table.
            join_col_source: Column on source used for the join.
            join_col_target: Column on target used for the join.

        Returns:
            (sql_string, params_tuple) for asyncpg.
        """
        source_entity = self._registry.get_entity_by_table(source_table)
        state = _QueryState()

        where_parts: list[str] = [f"t.{join_col_target} IS NULL"]
        extra_filters = self._build_where(intent.filters, source_entity, state)
        if extra_filters:
            where_parts.append(extra_filters)

        limit = min(intent.limit, self._max_limit)

        sql = (
            f"SELECT s.*\n"
            f"FROM {source_table} s\n"
            f"LEFT JOIN {target_table} t ON s.{join_col_source} = t.{join_col_target}\n"
            f"WHERE {' AND '.join(where_parts)}\n"
            f"LIMIT {limit}"
        )
        return sql, tuple(state.params)

    # ── Private helpers ───────────────────────────────────────────────────────

    def _select_columns(self, entity: EntityDef, requested: list[str] | None) -> str:
        """Return the SELECT column list, fully qualified."""
        if requested is None:
            return f"{entity.table_name}.*"
        validated: list[str] = []
        for alias in requested:
            col = self._resolve_col(entity, alias)
            validated.append(f"{entity.table_name}.{col}")
        return ", ".join(validated)

    def _resolve_col(self, entity: EntityDef, alias: str) -> str:
        """Resolve a field alias to a column name, or validate as exact column."""
        # Try exact column match first
        if alias in entity.fields:
            return alias
        # Try alias match within this entity's fields
        for col_name, fdef in entity.fields.items():
            if alias.lower() in [a.lower() for a in fdef.aliases]:
                return col_name
        raise QueryBuildError(
            f"Field '{alias}' not found on entity '{entity.table_name}'. "
            f"Known fields: {', '.join(entity.fields.keys())}"
        )
    def _build_where(
        self, filters: list[Filter], entity: EntityDef, state: _QueryState
    ) -> str:
        """Convert Filter list to parameterized WHERE clause body."""
        clauses: list[str] = []
        for f in filters:
            col = self._resolve_col(entity, f.field)
            fdef = entity.fields[col]
            qualified = f"{entity.table_name}.{col}"

            # Type conversion (e.g. str -> date for asyncpg)
            val = f.value
            if fdef.type == "date":
                val = self._to_date(val)

            if f.operator == OperatorType.between:
                if isinstance(val, list) and len(val) == 2:
                    low_ph, high_ph = state.add_between(
                        self._to_date(val[0]) if fdef.type == "date" else val[0],
                        self._to_date(val[1]) if fdef.type == "date" else val[1],
                    )
                    clauses.append(f"{qualified} BETWEEN {low_ph} AND {high_ph}")
            elif f.operator == OperatorType.in_:
                if isinstance(val, list):
                    converted_vals = [
                        self._to_date(v) if fdef.type == "date" else v for v in val
                    ]
                    ph = state.add(converted_vals)
                    clauses.append(f"{qualified} = ANY({ph})")
            else:
                ph = state.add(val)
                op_template = _OP_MAP[f.operator]
                clauses.append(f"{qualified} {op_template.format(ph)}")

        return " AND ".join(clauses)

    def _to_date(self, val: Any) -> Any:
        """Convert string to date object if possible."""
        if isinstance(val, str):
            try:
                # Handle ISO format 'YYYY-MM-DD'
                return datetime.strptime(val[:10], "%Y-%m-%d").date()
            except ValueError:
                return val
        return val

    def _build_order(self, sort: SortSpec | None, entity: EntityDef) -> str:
        """Convert SortSpec to ORDER BY clause body."""
        if sort is None:
            return ""
        col = self._resolve_col(entity, sort.field)
        return f"{entity.table_name}.{col} {sort.order.value.upper()}"

    @staticmethod
    def _agg_expression(fn: AggFunction, col: str) -> str:
        """Return the aggregate SQL expression for a column."""
        if fn == AggFunction.count_distinct:
            return f"COUNT(DISTINCT {col})"
        if fn == AggFunction.count:
            return f"COUNT({col})"
        return f"{fn.value.upper()}({col})"
