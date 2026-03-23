"""GraphIQ — Filter Pydantic model."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, model_validator

from app.core.dsl.enums import OperatorType, SortOrder  # import here


class Filter(BaseModel):
    """A single WHERE-clause predicate.

    The ``field`` attribute holds a semantic alias (e.g. "order_date").
    It is resolved to a real (table, column) reference by AliasResolver
    before the query builder sees it.
    """

    field: str
    operator: OperatorType
    value: Any  # Type-checked against registry during guardrail phase

    @model_validator(mode="after")
    def validate_between_value(self) -> "Filter":
        """Ensure BETWEEN operator receives a 2-element list or a placeholder string."""
        if self.operator == OperatorType.between:
            if isinstance(self.value, str) and self.value.startswith("$"):
                return self
            if not isinstance(self.value, list) or len(self.value) != 2:
                raise ValueError(
                    "BETWEEN operator requires value to be a list of exactly 2 elements or a placeholder string, "
                    f"got: {self.value!r}"
                )
        return self

    @model_validator(mode="after")
    def validate_in_value(self) -> "Filter":
        """Ensure IN operator receives a non-empty list or a placeholder string."""
        if self.operator == OperatorType.in_:
            if isinstance(self.value, str) and self.value.startswith("$"):
                return self
            if not isinstance(self.value, list) or len(self.value) == 0:
                raise ValueError(
                    "IN operator requires value to be a non-empty list or a placeholder string, "
                    f"got: {self.value!r}"
                )
        return self


class SortSpec(BaseModel):
    """Ordering specification for a query."""

    field: str  # Semantic alias
    order: SortOrder = SortOrder.desc

