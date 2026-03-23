"""GraphIQ — Enum definitions for the DSL intent models."""
from __future__ import annotations

from enum import Enum


class OperatorType(str, Enum):
    """Comparison operators supported in Filter predicates."""

    eq = "eq"
    neq = "neq"
    gt = "gt"
    gte = "gte"
    lt = "lt"
    lte = "lte"
    in_ = "in"
    between = "between"
    like = "like"


class AggFunction(str, Enum):
    """Aggregation functions supported in AggregationIntent."""

    sum = "sum"
    count = "count"
    avg = "avg"
    min = "min"
    max = "max"
    count_distinct = "count_distinct"


class SortOrder(str, Enum):
    """Sort direction."""

    asc = "asc"
    desc = "desc"


class IntentType(str, Enum):
    """All valid intent type discriminator values."""

    entity_lookup = "entity_lookup"
    entity_list = "entity_list"
    aggregation = "aggregation"
    flow_trace = "flow_trace"
    broken_flow = "broken_flow"
    out_of_scope = "out_of_scope"
    compound = "compound"
