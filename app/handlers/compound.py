"""GraphIQ — CompoundHandler: orchestrates multi-step compound intents.

Steps run sequentially. Results from step N can be referenced in step N+1
via the $step_N.results[index].field_name syntax in identifier fields.
"""
from __future__ import annotations

import re
import time
from typing import Any

from app.core.dsl.intents import CompoundIntent, CompoundStep
from app.handlers.base import BaseHandler, HandlerResult


# Pattern: $step_1.results[0].sales_order
_REF_PATTERN = re.compile(r"^\$(\w+)\.results\[(\d+)\]\.(\w+)$")


class CompoundHandler(BaseHandler):
    """Handles CompoundIntent — sequential multi-step query orchestration."""

    store_type = "pg"

    def __init__(self, handler_registry: dict[str, BaseHandler], pg_store: Any, neo4j_store: Any, registry: Any) -> None:
        super().__init__(pg_store, neo4j_store, registry)
        self._handler_registry = handler_registry

    def build_query(self, intent: Any) -> tuple[None, None]:
        return None, None  # CompoundHandler builds per-step

    async def execute(self, query: Any, params: Any) -> list[dict[str, Any]]:
        return []  # CompoundHandler executes per-step

    def shape_result(self, raw_data: list[dict[str, Any]], intent: Any) -> str:
        return ""  # Compound assembles per-step results

    async def handle(self, intent: CompoundIntent, context: Any) -> HandlerResult:  # type: ignore[override]
        start = time.monotonic()
        step_results: dict[str, HandlerResult] = {}
        all_raw: list[dict[str, Any]] = []
        summaries: list[str] = []
        all_node_ids: list[str] = []
        all_edge_seqs: list[str] = []

        for step in intent.steps:
            resolved_step = self._resolve_refs(step, step_results)
            handler = self._handler_registry.get(resolved_step.intent.intent_type)
            if handler is None:
                summaries.append(f"[{step.step_id}] Error: no handler for '{resolved_step.intent.intent_type}'")
                continue
            try:
                result = await handler.handle(resolved_step.intent, context)
                step_results[step.step_id] = result
                all_raw.extend(result.raw_data)
                summaries.append(f"[{step.step_id}] {result.prose_context}")
                all_node_ids.extend(result.node_ids)
                all_edge_seqs.extend(result.edge_sequence)
            except Exception as e:
                summaries.append(f"[{step.step_id}] Failed: {e}")

        elapsed_ms = int((time.monotonic() - start) * 1000)
        return HandlerResult(
            prose_context="\n\n".join(summaries),
            raw_data=all_raw,
            row_count=len(all_raw),
            truncated=False,
            store_used="mixed",
            query_ms=elapsed_ms,
            node_ids=all_node_ids,
            edge_sequence=all_edge_seqs,
        )

    def _resolve_refs(self, step: CompoundStep, results: dict[str, HandlerResult]) -> CompoundStep:
        """Substitute $step_N.results[i].field references in the step intent."""
        intent_data = step.intent.model_dump()
        self._substitute_refs_in_dict(intent_data, results)
        # Re-parse intent with resolved values
        from pydantic import TypeAdapter
        from app.core.dsl.intents import Intent
        new_intent = TypeAdapter(Intent).validate_python(intent_data)
        return step.model_copy(update={"intent": new_intent})

    def _substitute_refs_in_dict(self, data: dict[str, Any], results: dict[str, HandlerResult]) -> None:
        for key, value in data.items():
            if isinstance(value, str):
                match = _REF_PATTERN.match(value)
                if match:
                    step_id, idx_str, field = match.group(1), match.group(2), match.group(3)
                    idx = int(idx_str)
                    step_result = results.get(step_id)
                    if step_result and idx < len(step_result.raw_data):
                        data[key] = str(step_result.raw_data[idx].get(field, value))
            elif isinstance(value, dict):
                self._substitute_refs_in_dict(value, results)
            elif isinstance(value, list):
                for item in value:
                    if isinstance(item, dict):
                        self._substitute_refs_in_dict(item, results)
