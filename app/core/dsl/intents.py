"""GraphIQ — Pydantic v2 DSL intent models.

These are the only objects the LLM produces. Query building never
involves the LLM - it operates on these validated intent objects.

The discriminated union ``Intent`` is the top-level type used by:
- StructuredOutputParser (validation target)
- IntentRouter (dispatch key)
- Guardrail chain (inspection target)
"""
from __future__ import annotations

from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field

from app.core.dsl.enums import AggFunction, SortOrder
from app.core.dsl.filters import Filter, SortSpec


# ── Concrete intent types ─────────────────────────────────────────────────────

class EntityLookupIntent(BaseModel):
    """Fetch a single entity by primary key.

    Example: "Show me sales order 0000012345"
    """

    intent_type: Literal["entity_lookup"]
    entity_type: str  # Semantic alias, e.g. "order"
    identifier: str   # Document number / PK value (already zero-padded)
    fields: list[str] | None = None  # None = return all fields


class EntityListIntent(BaseModel):
    """Fetch a filtered, sorted list of entities.

    Example: "List all blocked customers"
    """

    intent_type: Literal["entity_list"]
    entity_type: str
    filters: list[Filter] = Field(default_factory=list)
    sort_by: SortSpec | None = None
    limit: int = Field(default=50, ge=1, le=500)
    fields: list[str] | None = None


class AggregationIntent(BaseModel):
    """Compute aggregate metrics grouped by one or more fields.

    Example: "Top 5 products by billing amount"
    """

    intent_type: Literal["aggregation"]
    entity_type: str
    measure: str        # Field alias to aggregate (e.g. "billing_amount")
    agg_fn: AggFunction
    group_by: list[str] = Field(default_factory=list)  # Field aliases
    filters: list[Filter] = Field(default_factory=list)
    sort_by: SortSpec | None = None
    limit: int = Field(default=10, ge=1, le=100)


class FlowTraceIntent(BaseModel):
    """Trace an entity through the O2C graph via Neo4j.

    Example: "Trace order 12345 to payment"
    """

    intent_type: Literal["flow_trace"]
    start_entity: str        # Entity alias, e.g. "order"
    start_id: str            # Document number (zero-padded)
    target_entity: str | None = None  # None = return all reachable
    max_depth: int = Field(default=4, ge=1, le=6)


class BrokenFlowIntent(BaseModel):
    """Find entities missing an expected downstream step.

    Example: "Which orders have no deliveries?"
    Routes to SQL (1-hop) or Neo4j (2+ hops) based on hop count.
    """

    intent_type: Literal["broken_flow"]
    source_entity: str       # e.g. "order"
    expected_target: str     # e.g. "delivery"
    filters: list[Filter] = Field(default_factory=list)
    limit: int = Field(default=50, ge=1, le=500)


class OutOfScopeIntent(BaseModel):
    """User asked something outside the O2C domain.

    Example: "What is the weather today?"
    """

    intent_type: Literal["out_of_scope"]
    reason: str
    suggestion: str | None = None  # What the user could ask instead


# ── Compound intent ───────────────────────────────────────────────────────────

_LeafIntent = (
    EntityLookupIntent
    | EntityListIntent
    | AggregationIntent
    | FlowTraceIntent
    | BrokenFlowIntent
)


class CompoundStep(BaseModel):
    """A single step within a CompoundIntent.

    The ``depends_on`` field allows referencing another step's results via
    the ``$step_N.results[index].field_name`` syntax.
    """

    step_id: str   # e.g. "step_1", "step_2"
    intent: Annotated[_LeafIntent, Field(discriminator="intent_type")]
    depends_on: str | None = None  # step_id of dependency step


class CompoundIntent(BaseModel):
    """Multi-step query combining up to 3 sub-intents sequentially.

    Example: "Top 5 products and trace the best one to payment"
    """

    intent_type: Literal["compound"]
    steps: list[CompoundStep] = Field(min_length=2, max_length=3)


# ── Top-level discriminated union ─────────────────────────────────────────────

Intent = Annotated[
    EntityLookupIntent
    | EntityListIntent
    | AggregationIntent
    | FlowTraceIntent
    | BrokenFlowIntent
    | OutOfScopeIntent
    | CompoundIntent,
    Field(discriminator="intent_type"),
]
"""Top-level type for all intents. Use this as the validation target."""
