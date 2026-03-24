"""GraphIQ — Intent Extraction Prompt.

Schema context section is AUTO-GENERATED from the live SchemaRegistry at
startup — never hand-maintained. When definitions.py changes, the prompt
updates automatically.

Few-shot examples are versioned constants covering all 7 intent types.
"""
from __future__ import annotations

from app.core.registry.schema_registry import SchemaRegistry

# ── Few-shot examples (1-2 per intent type, ~10 total) ───────────────────────

FEW_SHOT_EXAMPLES: list[dict[str, str]] = [
    {
        "question": "Show me sales order 740552",
        "intent": '{"intent_type": "entity_lookup", "entity_type": "order", "identifier": "0000740552", "fields": null}',
    },
    {
        "question": "Find billing document 90504248",
        "intent": '{"intent_type": "entity_lookup", "entity_type": "billing", "identifier": "0090504248", "fields": null}',
    },
    {
        "question": "List all blocked customers",
        "intent": '{"intent_type": "entity_list", "entity_type": "customer", "filters": [{"field": "is_blocked", "operator": "eq", "value": true}], "sort_by": null, "limit": 50, "fields": null}',
    },
    {
        "question": "Show orders created after January 1 2025",
        "intent": '{"intent_type": "entity_list", "entity_type": "order", "filters": [{"field": "order_date", "operator": "gte", "value": "2025-01-01"}], "sort_by": null, "limit": 50, "fields": null}',
    },
    {
        "question": "Which invoices are still unpaid?",
        "intent": '{"intent_type": "entity_list", "entity_type": "journal_entry", "filters": [{"field": "is_paid", "operator": "eq", "value": null}], "sort_by": null, "limit": 50, "fields": null}',
    },
    {
        "question": "Top 5 products by billing amount",
        "intent": '{"intent_type": "aggregation", "entity_type": "billing_item", "measure": "billing_amount", "agg_fn": "sum", "group_by": ["product_id"], "filters": [], "sort_by": {"field": "agg_value", "order": "desc"}, "limit": 5}',
    },
    {
        "question": "Total billing per currency this year",
        "intent": '{"intent_type": "aggregation", "entity_type": "billing", "measure": "billing_total", "agg_fn": "sum", "group_by": ["billing_currency"], "filters": [{"field": "billing_date", "operator": "gte", "value": "2025-01-01"}], "sort_by": {"field": "agg_value", "order": "desc"}, "limit": 10}',
    },
    {
        "question": "Trace order 740552 from order to payment",
        "intent": '{"intent_type": "flow_trace", "start_entity": "SalesOrder", "start_id": "0000740552", "target_entity": "Payment", "max_depth": 4}',
    },
    {
        "question": "Which orders have no deliveries?",
        "intent": '{"intent_type": "broken_flow", "source_entity": "order", "expected_target": "delivery", "filters": [], "limit": 50}',
    },
    {
        "question": "What is the weather today?",
        "intent": '{"intent_type": "out_of_scope", "reason": "Weather is not part of the O2C dataset", "suggestion": "Try asking about orders, deliveries, billing, or payments"}',
    },
    {
        "question": "Top 5 products and trace the best one to payment",
        "intent": '{"intent_type": "compound", "steps": [{"step_id": "step_1", "intent": {"intent_type": "aggregation", "entity_type": "billing_item", "measure": "billing_amount", "agg_fn": "sum", "group_by": ["product_id"], "filters": [], "sort_by": {"field": "agg_value", "order": "desc"}, "limit": 5}, "depends_on": null}, {"step_id": "step_2", "intent": {"intent_type": "flow_trace", "start_entity": "Product", "start_id": "$step_1.results[0].product_id", "target_entity": "Payment", "max_depth": 4}, "depends_on": "step_1"}]}',
    },
]

_SYSTEM_PROMPT = """\
You are an O2C (Order-to-Cash) data analyst. You interpret user questions about
SAP business data including sales orders, deliveries, billing documents, payments,
customers, and products.

Given a user question, return a JSON object matching one of the defined intent types.
Use ONLY the entity names and field aliases listed in the schema below.
If the question is outside the O2C domain, return an out_of_scope intent.
If the question requires multiple steps, return a compound intent (max 3 steps).

CRITICAL RULES:
- Return ONLY valid JSON. No markdown, no code fences, no explanation.
- Start your response with '{' and end with '}'.
- Use semantic aliases for entity_type and field names — NEVER real column names.
- SAP document numbers must be zero-padded to 10 digits (e.g., "12345" → "0000012345").
- Choose the ENTITY that contains all required fields (e.g., use headers for date-based filters).
"""


def build_intent_prompt(registry: SchemaRegistry, question: str) -> str:
    """Build the full intent extraction prompt with auto-generated schema context.

    Args:
        registry: Live SchemaRegistry instance.
        question: User's natural language question.

    Returns:
        Full prompt string to send to the LLM.
    """
    schema_context = _build_schema_context(registry)
    examples_text = _build_examples_section()

    return (
        _SYSTEM_PROMPT
        + "\n\n"
        + schema_context
        + "\n\n"
        + examples_text
        + f"\n\nUser question: {question}\n"
        + "JSON response:"
    )


def _build_schema_context(registry: SchemaRegistry) -> str:
    """Auto-generate the schema context section from the live registry."""
    lines: list[str] = ["## Available Entities and Fields\n"]

    for table_name, entity in registry.all_entities.items():
        aliases_str = ", ".join(entity.aliases[:4])  # Show up to 4 aliases
        lines.append(f"### {table_name} (use aliases: {aliases_str})")
        for col_name, fdef in entity.fields.items():
            if col_name == "updated_at":
                continue  # Internal field, don't expose to LLM
            alias_str = f" | aliases: {', '.join(fdef.aliases[:3])}" if fdef.aliases else ""
            flags: list[str] = []
            if fdef.filterable:
                flags.append("filterable")
            if fdef.aggregatable:
                flags.append("aggregatable")
            if fdef.type == "date":
                flags.append("DATE-FIELD")
            flag_str = f" [{', '.join(flags)}]" if flags else ""
            lines.append(f"  - {col_name} ({fdef.type}){flag_str}{alias_str}")
        lines.append("")

    lines.append("## Intent Types\n")
    lines.append("entity_lookup: fetch one entity by ID")
    lines.append("entity_list: filtered list with optional sort/limit")
    lines.append("aggregation: GROUP BY with SUM/COUNT/AVG/MIN/MAX/COUNT_DISTINCT")
    lines.append("flow_trace: trace O2C path via graph (Customer→SalesOrder→Delivery→Invoice→JournalEntry→Payment)")
    lines.append("broken_flow: find entities missing a downstream step")
    lines.append("out_of_scope: question not about O2C data")
    lines.append("compound: 2-3 sequential steps (max)")
    lines.append("")
    lines.append("## Filter Operators")
    lines.append("eq, neq, gt, gte, lt, lte, in, between, like")

    return "\n".join(lines)


def _build_examples_section() -> str:
    """Format the few-shot examples as a prompt section."""
    lines: list[str] = ["## Examples\n"]
    for ex in FEW_SHOT_EXAMPLES:
        lines.append(f"Q: {ex['question']}")
        lines.append(f"A: {ex['intent']}")
        lines.append("")
    return "\n".join(lines)

