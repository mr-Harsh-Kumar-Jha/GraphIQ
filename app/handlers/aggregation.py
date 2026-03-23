"""GraphIQ — AggregationHandler: GROUP BY aggregate queries from PostgreSQL.

Cross-currency guard: when aggregating a monetary field without grouping
by transaction_currency, a warning is appended to prose_context.
"""
from __future__ import annotations

from typing import Any

from app.core.dsl.intents import AggregationIntent
from app.handlers.base import BaseHandler, HandlerResult

# Monetary field aliases that trigger the cross-currency warning
_MONETARY_ALIASES = frozenset({
    "billing_amount", "order_amount", "order_total", "payment_amount",
    "net_amount", "total_net_amount", "invoice_amount", "billing_total",
    "paid_amount", "item_amount", "line_amount", "net_amount_so",
    "line_billing_amount", "item_billing_amount", "net_amount_soi",
})


class AggregationHandler(BaseHandler):
    """Handles AggregationIntent — GROUP BY aggregation from PostgreSQL."""

    store_type = "pg"

    def __init__(self, sql_builder: Any, pg_store: Any, neo4j_store: Any, registry: Any) -> None:
        super().__init__(pg_store, neo4j_store, registry)
        self.sql_builder = sql_builder

    def build_query(self, intent: AggregationIntent) -> tuple[str, tuple[Any, ...]]:  # type: ignore[override]
        entity = self.registry.get_entity_by_alias(intent.entity_type)
        resolved = intent.model_copy(update={"entity_type": entity.table_name})
        return self.sql_builder.build_aggregation(resolved)

    async def execute(self, query: str, params: tuple[Any, ...]) -> list[dict[str, Any]]:
        rows = await self.pg_store.fetch(query, *params)
        return [dict(row) for row in rows]

    def shape_result(self, raw_data: list[dict[str, Any]], intent: AggregationIntent) -> str:  # type: ignore[override]
        if not raw_data:
            return (
                f"No data found for {intent.agg_fn.value}({intent.measure}) "
                f"on {intent.entity_type}. Try different filters."
            )

        # Cross-currency warning
        currency_warning = ""
        if (
            intent.measure.lower() in _MONETARY_ALIASES
            and intent.agg_fn.value in ("sum", "avg")
            and not any(
                g.lower() in ("transaction_currency", "currency", "billing_currency",
                              "payment_currency", "so_currency")
                for g in intent.group_by
            )
        ):
            currency_warning = (
                "\n⚠️ WARNING: Results may span multiple currencies. "
                "Consider grouping by 'transaction_currency' for accurate totals."
            )

        lines: list[str] = []
        for i, row in enumerate(raw_data, 1):
            val = row.get("agg_value")
            group_parts = {k: v for k, v in row.items() if k != "agg_value" and v is not None}
            group_str = ", ".join(f"{k}={v}" for k, v in group_parts.items())
            lines.append(f"  {i}. {group_str} → {intent.agg_fn.value}={val}")

        return (
            f"{intent.agg_fn.value.upper()} of {intent.measure} "
            f"on {intent.entity_type} ({len(raw_data)} groups):\n"
            + "\n".join(lines)
            + currency_warning
        )

    async def handle(self, intent: AggregationIntent, context: Any) -> HandlerResult:  # type: ignore[override]
        result = await super().handle(intent, context)
        node_ids = []
        for r in result.raw_data:
            for k, v in r.items():
                if k != "agg_value" and v is not None:
                    node_ids.append(str(v))
        node_ids = list(dict.fromkeys(node_ids))
        return result.model_copy(update={"node_ids": node_ids})
