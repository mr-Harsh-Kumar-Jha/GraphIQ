"""GraphIQ — Guardrail Chain: 5 ordered guards validating each intent.

Execution order (cheapest first):
1. ScopeGuard — valid intent_type, O2C domain check
2. FieldGuard — entity/field references known to registry
3. TypeGuard — operator ↔ field type compatibility
4. ComplexityGuard — within limits (filters ≤ 10, groups ≤ 3, steps ≤ 3)
5. RateGuard — per-user rate limit (30 req/min)
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Any

from pydantic import BaseModel

from app.core.config import settings
from app.core.dsl.enums import OperatorType
from app.core.dsl.intents import (
    AggregationIntent, BrokenFlowIntent, CompoundIntent,
    EntityListIntent, EntityLookupIntent, FlowTraceIntent,
)
from app.core.exceptions import GuardrailError
from app.core.registry.schema_registry import SchemaRegistry


class GuardrailResult(BaseModel):
    """Result from a guardrail evaluation."""
    passed: bool
    guard_name: str = ""
    user_message: str = ""
    suggestions: list[str] = []


class BaseGuard(ABC):
    """Abstract base for all guards."""

    @abstractmethod
    def check(self, intent: Any, user_id: str = "anonymous") -> GuardrailResult: ...


# ── 1. ScopeGuard ─────────────────────────────────────────────────────────────

_VALID_INTENT_TYPES = {
    "entity_lookup", "entity_list", "aggregation",
    "flow_trace", "broken_flow", "out_of_scope", "compound",
}


class ScopeGuard(BaseGuard):
    """Ensures the intent type is valid and in-domain."""

    def check(self, intent: Any, user_id: str = "anonymous") -> GuardrailResult:
        intent_type = getattr(intent, "intent_type", None)
        if intent_type not in _VALID_INTENT_TYPES:
            return GuardrailResult(
                passed=False,
                guard_name="ScopeGuard",
                user_message=(
                    "This system is designed only for O2C dataset queries. "
                    "Try asking about orders, deliveries, billing, or payments."
                ),
                suggestions=["Show me sales order 12345", "Top 5 products by billing amount"],
            )
        return GuardrailResult(passed=True)


# ── 2. FieldGuard ─────────────────────────────────────────────────────────────

class FieldGuard(BaseGuard):
    """Validates all entity_type and field references against the registry."""

    def __init__(self, registry: SchemaRegistry) -> None:
        self._registry = registry

    def check(self, intent: Any, user_id: str = "anonymous") -> GuardrailResult:
        unknown: list[str] = []

        # Check entity_type
        for attr in ("entity_type", "source_entity", "expected_target", "start_entity", "target_entity"):
            value = getattr(intent, attr, None)
            if value and isinstance(value, str):
                if not self._registry.resolve_entity_alias(value) and value not in {
                    "SalesOrder", "Delivery", "Invoice", "JournalEntry", "Payment",
                    "Customer", "Product", "Plant",
                }:
                    unknown.append(f"entity '{value}'")

        # Check filters
        for f in getattr(intent, "filters", []):
            ref = self._registry.resolve_field_alias(f.field)
            if ref is None:
                # Try entity context
                entity_alias = getattr(intent, "entity_type", None)
                if entity_alias:
                    table = self._registry.resolve_entity_alias(entity_alias)
                    if table:
                        try:
                            self._registry.get_field(table, f.field)
                            continue
                        except Exception:
                            pass
                unknown.append(f"field '{f.field}'")

        if unknown:
            suggestions = ["billing_amount", "order_date", "customer_name", "delivery_date"]
            msg = (
                f"I couldn't find the following in the O2C schema: {', '.join(unknown)}. "
                "Check the field names and try again."
            )
            return GuardrailResult(
                passed=False, guard_name="FieldGuard",
                user_message=msg, suggestions=suggestions,
            )
        return GuardrailResult(passed=True)


# ── 3. TypeGuard ──────────────────────────────────────────────────────────────

# Operators not valid for string fields
_NUMERIC_ONLY_OPS = {OperatorType.gt, OperatorType.gte, OperatorType.lt, OperatorType.lte, OperatorType.between}
_STRING_FIELDS = {"str"}


class TypeGuard(BaseGuard):
    """Checks operator-field type compatibility."""

    def __init__(self, registry: SchemaRegistry) -> None:
        self._registry = registry

    def check(self, intent: Any, user_id: str = "anonymous") -> GuardrailResult:
        entity_alias = getattr(intent, "entity_type", None)
        if not entity_alias:
            return GuardrailResult(passed=True)
        table = self._registry.resolve_entity_alias(entity_alias)
        if not table:
            return GuardrailResult(passed=True)

        for f in getattr(intent, "filters", []):
            ref = self._registry.resolve_field_alias(f.field)
            if ref:
                _, col = ref
                try:
                    fdef = self._registry.get_field(ref[0], col)
                    if fdef.type in _STRING_FIELDS and f.operator in _NUMERIC_ONLY_OPS:
                        return GuardrailResult(
                            passed=False,
                            guard_name="TypeGuard",
                            user_message=(
                                f"Operator '{f.operator.value}' is not valid for "
                                f"text field '{f.field}'. Use 'eq', 'neq', 'like', or 'in'."
                            ),
                        )
                except Exception:
                    pass
        return GuardrailResult(passed=True)


# ── 4. ComplexityGuard ────────────────────────────────────────────────────────

class ComplexityGuard(BaseGuard):
    """Enforces limits on filters, group_by, compound steps."""

    MAX_FILTERS = 10
    MAX_GROUPS = 3
    MAX_STEPS = 3

    def check(self, intent: Any, user_id: str = "anonymous") -> GuardrailResult:
        filters = getattr(intent, "filters", [])
        if len(filters) > self.MAX_FILTERS:
            return GuardrailResult(
                passed=False, guard_name="ComplexityGuard",
                user_message=f"Too many filters ({len(filters)}). Maximum allowed is {self.MAX_FILTERS}.",
            )
        group_by = getattr(intent, "group_by", [])
        if len(group_by) > self.MAX_GROUPS:
            return GuardrailResult(
                passed=False, guard_name="ComplexityGuard",
                user_message=f"Too many group-by fields ({len(group_by)}). Maximum is {self.MAX_GROUPS}.",
            )
        steps = getattr(intent, "steps", [])
        if len(steps) > self.MAX_STEPS:
            return GuardrailResult(
                passed=False, guard_name="ComplexityGuard",
                user_message=f"Compound query has {len(steps)} steps. Maximum is {self.MAX_STEPS}.",
            )
        return GuardrailResult(passed=True)


# ── 5. RateGuard ─────────────────────────────────────────────────────────────

class RateGuard(BaseGuard):
    """Simple in-memory per-user rate limiting (30 req/min default)."""

    def __init__(self, limit_per_minute: int | None = None) -> None:
        self._limit = limit_per_minute or settings.rate_limit_per_minute
        self._window: dict[str, list[float]] = defaultdict(list)

    def check(self, intent: Any, user_id: str = "anonymous") -> GuardrailResult:
        now = time.time()
        window = self._window[user_id]
        # Remove entries older than 60 seconds
        cutoff = now - 60.0
        self._window[user_id] = [t for t in window if t > cutoff]
        if len(self._window[user_id]) >= self._limit:
            return GuardrailResult(
                passed=False, guard_name="RateGuard",
                user_message=(
                    f"You've exceeded the rate limit of {self._limit} requests per minute. "
                    "Please wait a moment before trying again."
                ),
            )
        self._window[user_id].append(now)
        return GuardrailResult(passed=True)


# ── Guardrail Chain runner ────────────────────────────────────────────────────

class GuardrailChain:
    """Runs all 5 guards in order, stopping at first rejection."""

    def __init__(self, guards: list[BaseGuard]) -> None:
        self._guards = guards

    def run(self, intent: Any, user_id: str = "anonymous") -> GuardrailResult:
        """Run all guards in order.

        Args:
            intent: Validated intent object.
            user_id: Request user identifier for rate limiting.

        Returns:
            GuardrailResult — passed=True if all guards pass,
            or the first rejection result.
        """
        for guard in self._guards:
            result = guard.check(intent, user_id)
            if not result.passed:
                return result
        return GuardrailResult(passed=True, guard_name="all_passed")
