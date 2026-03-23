"""GraphIQ — QueryService: the single public facade orchestrating everything.

Lifecycle (per instruction.md):
1.  Create RequestContext
2.  Emit request_received
3.  LLM intent extraction (FallbackChain + StructuredOutputParser, with retry)
4.  Emit intent_parsed
5.  Guardrail chain — reject early if failed
6.  Emit guardrail_passed / guardrail_rejected
7.  AliasResolver — resolve entity/field aliases + zero-pad doc numbers
8.  IntentRouter.dispatch → handler
9.  Handler: build_query → execute → shape_result
10. Emit query_executed
11. LLM prose generation
12. Emit prose_generated
13. Assemble QueryResponse (includes sync_lag_seconds)
14. Emit completed
"""
from __future__ import annotations

import time
from typing import Any

import structlog
from pydantic import BaseModel

from app.core.exceptions import GuardrailError, LLMError, O2CBaseError, ParseError
from app.llm.fallback_chain import FallbackChain
from app.llm.prompts.intent_extraction import build_intent_prompt
from app.llm.prompts.prose_generation import build_prose_prompt
from app.llm.structured_parser import StructuredOutputParser
from app.supervision.event_bus import EventBus
from app.supervision.request_context import RequestContext
from app.supervision.guardrails.chain import GuardrailChain

logger = structlog.get_logger()

MAX_PARSE_ATTEMPTS = 3


class QueryMetadata(BaseModel):
    """Metadata returned alongside every query response."""
    intent_type: str | None = None
    store_used: str | None = None
    query_ms: int = 0
    total_ms: int = 0
    row_count: int = 0
    truncated: bool = False
    sync_lag_seconds: float = -1.0
    corrections_applied: list[dict[str, Any]] = []
    node_ids: list[str] = []
    edge_sequence: list[str] = []


class QueryResponse(BaseModel):
    """Full API response for a user question."""
    request_id: str
    answer: str
    data: list[dict[str, Any]]
    metadata: QueryMetadata

    model_config = {"arbitrary_types_allowed": True}


class QueryService:
    """Single entry point orchestrating the full O2C query lifecycle."""

    def __init__(
        self,
        registry: Any,
        fallback_chain: FallbackChain,
        parser: StructuredOutputParser,
        guardrail_chain: GuardrailChain,
        alias_resolver: Any,
        intent_router: Any,
        event_bus: EventBus,
        neo4j_store: Any,
    ) -> None:
        self._registry = registry
        self._chain = fallback_chain
        self._parser = parser
        self._guardrails = guardrail_chain
        self._alias_resolver = alias_resolver
        self._router = intent_router
        self._event_bus = event_bus
        self._neo4j_store = neo4j_store

    async def answer(self, question: str, user_id: str = "anonymous") -> QueryResponse:
        """Run the full query lifecycle and return a structured response.

        Args:
            question: Natural language question from the user.
            user_id: Identifier for rate limiting (IP or session).

        Returns:
            QueryResponse with prose answer, raw data, and metadata.
        """
        start = time.monotonic()
        ctx = RequestContext(question=question, event_bus=self._event_bus)
        await ctx.emit("request_received", {"question": question})

        try:
            # ── Step 3: LLM intent extraction with retry ──────────────────────
            base_prompt = build_intent_prompt(self._registry, question)
            intent = await self._extract_intent_with_retry(ctx, base_prompt)
            ctx.intent_validated = intent
            await ctx.emit("intent_parsed", {"intent_type": intent.intent_type})

            # ── Step 5: Guardrail chain ───────────────────────────────────────
            guardrail_result = self._guardrails.run(intent, user_id=user_id)
            ctx.guardrail_result = "passed" if guardrail_result.passed else "rejected"
            if not guardrail_result.passed:
                await ctx.emit("guardrail_rejected", {
                    "guard": guardrail_result.guard_name,
                    "message": guardrail_result.user_message,
                })
                total_ms = int((time.monotonic() - start) * 1000)
                return QueryResponse(
                    request_id=ctx.request_id,
                    answer=guardrail_result.user_message,
                    data=[],
                    metadata=QueryMetadata(
                        intent_type=intent.intent_type,
                        total_ms=total_ms,
                    ),
                )
            await ctx.emit("guardrail_passed")

            # ── Step 7: Alias resolution ──────────────────────────────────────
            intent = self._alias_resolver.resolve_intent_aliases(intent)

            # ── Step 8-9: Handler dispatch and execution ──────────────────────
            handler_result = await self._router.dispatch(intent, ctx)
            ctx.store_used = handler_result.store_used
            ctx.query_ms = handler_result.query_ms
            ctx.result_row_count = handler_result.row_count
            await ctx.emit("query_executed", {
                "store_used": handler_result.store_used,
                "query_ms": handler_result.query_ms,
                "row_count": handler_result.row_count,
            })

            # ── Step 11: Prose generation ─────────────────────────────────────
            prose_prompt = build_prose_prompt(question, handler_result.prose_context)
            prose_answer = await self._chain.generate_text(prose_prompt)
            await ctx.emit("prose_generated")

            # ── Step 13: Assemble response ────────────────────────────────────
            sync_lag = self._neo4j_store.sync_lag_seconds() if handler_result.store_used == "neo4j" else -1.0
            total_ms = int((time.monotonic() - start) * 1000)

            await ctx.emit("completed", {
                "total_ms": total_ms,
                "question": question,
                "prose_answer": prose_answer,
                "store_used": handler_result.store_used,
                "query_ms": handler_result.query_ms,
                "result_row_count": handler_result.row_count,
                "result_truncated": handler_result.truncated,
            })

            return QueryResponse(
                request_id=ctx.request_id,
                answer=prose_answer,
                data=handler_result.raw_data,
                metadata=QueryMetadata(
                    intent_type=str(intent.intent_type),
                    store_used=handler_result.store_used,
                    query_ms=handler_result.query_ms,
                    total_ms=total_ms,
                    row_count=handler_result.row_count,
                    truncated=handler_result.truncated,
                    sync_lag_seconds=sync_lag,
                    node_ids=handler_result.node_ids,
                    edge_sequence=handler_result.edge_sequence,
                ),
            )

        except O2CBaseError as e:
            total_ms = int((time.monotonic() - start) * 1000)
            await ctx.emit("error", {"error_type": type(e).__name__, "error_detail": e.message})
            return QueryResponse(
                request_id=ctx.request_id,
                answer=f"An error occurred: {e.message}",
                data=[],
                metadata=QueryMetadata(total_ms=total_ms),
            )
        except Exception as e:
            total_ms = int((time.monotonic() - start) * 1000)
            await ctx.emit("error", {"error_type": "UnexpectedError", "error_detail": str(e)})
            logger.exception("unexpected_query_error", question=question)
            return QueryResponse(
                request_id=ctx.request_id,
                answer="An unexpected error occurred. Please try again.",
                data=[],
                metadata=QueryMetadata(total_ms=total_ms),
            )

    async def _extract_intent_with_retry(self, ctx: RequestContext, base_prompt: str) -> Any:
        """Call LLM + parser with error-feedback retry loop.

        Max MAX_PARSE_ATTEMPTS total across all providers.
        """
        prompt = base_prompt
        last_feedback: str | None = None

        for attempt in range(1, MAX_PARSE_ATTEMPTS + 1):
            if last_feedback:
                prompt = self._parser.build_parse_retry_prompt(base_prompt, last_feedback)

            raw_text = await self._chain.generate_structured(prompt)
            ctx.intent_raw = raw_text

            intent, feedback = self._parser.parse(raw_text)
            if intent is not None:
                return intent
            last_feedback = feedback
            logger.warning(
                "intent_parse_retry",
                attempt=attempt,
                feedback=feedback[:100] if feedback else None,
            )

        raise ParseError(
            f"Failed to parse LLM response after {MAX_PARSE_ATTEMPTS} attempts. "
            f"Last feedback: {last_feedback}"
        )
