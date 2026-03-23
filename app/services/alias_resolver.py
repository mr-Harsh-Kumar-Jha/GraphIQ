"""GraphIQ — Alias Resolver: fuzzy matching and SAP zero-padding.

Resolution algorithm (per instruction.md):
1. Exact match against entity/field alias registry → use it
2. Fuzzy match (rapidfuzz) against all aliases
3. Score >= 85% → auto-correct (log the correction)
4. Score 50-85% → return clarification suggestions
5. Score < 50% → reject as unknown

SAP zero-padding: numeric document numbers padded to 10 digits.
"""
from __future__ import annotations

import re
import structlog
from typing import Any

from rapidfuzz import process, fuzz  # type: ignore[import]

from app.core.exceptions import ValidationError
from app.core.registry.schema_registry import SchemaRegistry

logger = structlog.get_logger()

_SAP_DOC_PATTERN = re.compile(r"^\d{1,10}$")
_AUTO_CORRECT_THRESHOLD = 85.0
_CLARIFY_THRESHOLD = 50.0


class AliasResolver:
    """Resolves semantic entity/field aliases to real (table, column) references.

    Also applies SAP document number zero-padding to 10 digits where appropriate.
    """

    def __init__(self, registry: SchemaRegistry) -> None:
        self._registry = registry
        self._all_entity_aliases = registry.all_entity_aliases
        self._all_field_aliases = registry.all_field_aliases

    def resolve_entity(self, alias: str) -> str:
        """Resolve an entity alias to a canonical table name.

        Args:
            alias: Semantic alias from the LLM, e.g. "order".

        Returns:
            Canonical table name, e.g. "sales_order_headers".

        Raises:
            ValidationError: If the alias cannot be resolved even with fuzzy matching.
        """
        # 1. Exact match
        table = self._registry.resolve_entity_alias(alias)
        if table:
            return table

        # 2. Fuzzy match
        return self._fuzzy_entity(alias)

    def resolve_field(self, field_alias: str, entity_table: str) -> tuple[str, str]:
        """Resolve a field alias to (table_name, column_name).

        Args:
            field_alias: Semantic field alias, e.g. "billing_amount".
            entity_table: The resolved entity table for context.

        Returns:
            (table_name, column_name) tuple.

        Raises:
            ValidationError: If the field cannot be resolved.
        """
        # 1. Exact match in the field alias map
        ref = self._registry.resolve_field_alias(field_alias)
        if ref:
            return ref

        # 2. Try direct column name match within the entity
        entity = self._registry.get_entity_by_table(entity_table)
        if field_alias in entity.fields:
            return entity_table, field_alias

        # 3. Fuzzy match
        return self._fuzzy_field(field_alias, entity_table)

    def normalize_document_number(self, value: str) -> str:
        """Pad SAP document numbers to 10 digits with leading zeros.

        Args:
            value: Identifier from LLM, e.g. "12345".

        Returns:
            Zero-padded string, e.g. "0000012345".
            Non-numeric strings are returned as-is.
        """
        if _SAP_DOC_PATTERN.match(value.strip()):
            return value.strip().zfill(10)
        return value

    def resolve_intent_aliases(self, intent: Any) -> Any:
        """Walk an intent object and resolve all entity/field aliases in-place.

        Args:
            intent: Any validated intent object.

        Returns:
            New intent with resolved aliases (entity_type → table name,
            field aliases → column names, identifiers zero-padded).
        """
        from app.core.dsl.intents import (
            EntityLookupIntent, EntityListIntent, AggregationIntent,
            FlowTraceIntent, BrokenFlowIntent, CompoundIntent,
        )

        if isinstance(intent, EntityLookupIntent):
            table = self.resolve_entity(intent.entity_type)
            identifier = self.normalize_document_number(intent.identifier)
            return intent.model_copy(update={"entity_type": table, "identifier": identifier})

        if isinstance(intent, EntityListIntent):
            table = self.resolve_entity(intent.entity_type)
            filters = self._resolve_filters(intent.filters, table)
            return intent.model_copy(update={"entity_type": table, "filters": filters})

        if isinstance(intent, AggregationIntent):
            table = self.resolve_entity(intent.entity_type)
            _, measure_col = self.resolve_field(intent.measure, table)
            resolved_groups = [self.resolve_field(g, table)[1] for g in intent.group_by]
            filters = self._resolve_filters(intent.filters, table)
            return intent.model_copy(update={
                "entity_type": table,
                "measure": measure_col,
                "group_by": resolved_groups,
                "filters": filters,
            })

        if isinstance(intent, (FlowTraceIntent, BrokenFlowIntent)):
            return intent  # Labels handled by CypherBuilder

        if isinstance(intent, CompoundIntent):
            resolved_steps = []
            for step in intent.steps:
                resolved_inner = self.resolve_intent_aliases(step.intent)
                resolved_steps.append(step.model_copy(update={"intent": resolved_inner}))
            return intent.model_copy(update={"steps": resolved_steps})

        return intent

    # ── Private helpers ───────────────────────────────────────────────────────

    def _resolve_filters(self, filters: list[Any], table: str) -> list[Any]:
        resolved = []
        for f in filters:
            try:
                _, col = self.resolve_field(f.field, table)
                resolved.append(f.model_copy(update={"field": col}))
            except ValidationError:
                resolved.append(f)  # Let TypeGuard catch unknown fields
        return resolved

    def _fuzzy_entity(self, alias: str) -> str:
        result = process.extractOne(
            alias.lower(),
            self._all_entity_aliases,
            scorer=fuzz.WRatio,
        )
        if result is None:
            raise ValidationError(f"Unknown entity: '{alias}'")
        match_str, score, _ = result
        if score >= _AUTO_CORRECT_THRESHOLD:
            logger.warning("alias_autocorrected_entity", original=alias, corrected=match_str, score=score)
            table = self._registry.resolve_entity_alias(match_str)
            return table or match_str
        top3 = [r[0] for r in process.extract(alias.lower(), self._all_entity_aliases, limit=3)]
        if score >= _CLARIFY_THRESHOLD:
            raise ValidationError(
                f"Unknown entity '{alias}'. Did you mean one of: {', '.join(top3)}?",
                detail="clarification_needed",
            )
        raise ValidationError(
            f"Unknown entity '{alias}'. No close match found. "
            f"Try: {', '.join(top3[:3])}",
        )

    def _fuzzy_field(self, alias: str, table: str) -> tuple[str, str]:
        result = process.extractOne(
            alias.lower(),
            self._all_field_aliases,
            scorer=fuzz.WRatio,
        )
        if result is None:
            raise ValidationError(f"Unknown field: '{alias}'")
        match_str, score, _ = result
        entity_aliases = [
            a for a in self._all_field_aliases
            if a.lower() in [f.lower() for f in
                              (self._registry.get_entity_by_table(table).fields.get(match_str, type('')).aliases
                               if hasattr(self._registry.get_entity_by_table(table).fields.get(match_str, None), 'aliases')
                               else [])]
        ]
        if score >= _AUTO_CORRECT_THRESHOLD:
            logger.warning("alias_autocorrected_field", original=alias, corrected=match_str, score=score)
            ref = self._registry.resolve_field_alias(match_str)
            if ref:
                return ref
        top3_aliases = [r[0] for r in process.extract(alias.lower(), self._all_field_aliases, limit=3)]
        if score >= _CLARIFY_THRESHOLD:
            raise ValidationError(
                f"Unknown field '{alias}'. Did you mean: {', '.join(top3_aliases)}?",
                detail="clarification_needed",
            )
        raise ValidationError(
            f"Unknown field '{alias}'. No close match found. "
            f"Try: {', '.join(top3_aliases)}",
        )
