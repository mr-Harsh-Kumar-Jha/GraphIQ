"""GraphIQ — Observers: Logging and Audit."""
from __future__ import annotations

import json
import time
from typing import Any

import structlog

from app.storage.postgres import PostgresStore

logger = structlog.get_logger()


class LoggingObserver:
    """Writes a structured JSON log entry for each lifecycle event."""

    async def __call__(self, event_type: str, payload: dict[str, Any]) -> None:
        level = _EVENT_LEVELS.get(event_type, "info")
        safe_payload = dict(payload)
        # Avoid conflict with structlog's positional 'event' argument
        if "event" in safe_payload:
            safe_payload["_event_data"] = safe_payload.pop("event")
            
        getattr(logger, level)(event_type, **safe_payload)


_EVENT_LEVELS: dict[str, str] = {
    "request_received": "info",
    "intent_parsed": "info",
    "guardrail_passed": "info",
    "guardrail_rejected": "warning",
    "alias_corrected": "warning",
    "query_built": "debug",
    "query_executed": "info",
    "result_shaped": "debug",
    "prose_generated": "info",
    "llm_fallback": "warning",
    "query_timeout": "error",
    "completed": "info",
    "error": "error",
}


class AuditObserver:
    """Accumulates events per request and writes a single AuditRecord to PostgreSQL on completion."""

    _INSERT_SQL = """
        INSERT INTO audit.request_logs (
            request_id, timestamp, user_question, llm_provider_used,
            intent_raw_json, intent_validated, corrections_applied,
            guardrail_result, guardrail_detail,
            query_generated, query_params, store_used,
            query_ms, result_row_count, result_truncated,
            prose_answer, total_latency_ms, error_type, error_detail
        ) VALUES (
            $1, $2, $3, $4, $5, $6, $7, $8, $9,
            $10, $11, $12, $13, $14, $15, $16, $17, $18, $19
        )
        ON CONFLICT (request_id) DO NOTHING
    """

    def __init__(self, pg_store: PostgresStore) -> None:
        self._pg = pg_store
        self._buffers: dict[str, dict[str, Any]] = {}

    async def __call__(self, event_type: str, payload: dict[str, Any]) -> None:
        request_id = payload.get("request_id")
        if not request_id:
            return

        buf = self._buffers.setdefault(request_id, {})
        buf.update(payload)

        if event_type in ("completed", "error"):
            await self._flush(request_id, buf)
            del self._buffers[request_id]

    async def _flush(self, request_id: str, buf: dict[str, Any]) -> None:
        from datetime import datetime
        try:
            await self._pg.execute(
                self._INSERT_SQL,
                request_id,
                buf.get("timestamp", datetime.utcnow()),
                buf.get("question", ""),
                buf.get("llm_provider_used"),
                json.dumps(buf.get("intent_raw_json")) if buf.get("intent_raw_json") else None,
                json.dumps(buf.get("intent_validated")) if buf.get("intent_validated") else None,
                json.dumps(buf.get("corrections_applied", [])),
                buf.get("guardrail_result"),
                buf.get("guardrail_detail"),
                buf.get("query_generated"),
                json.dumps(buf.get("query_params")) if buf.get("query_params") else None,
                buf.get("store_used"),
                buf.get("query_ms", 0),
                buf.get("result_row_count", 0),
                buf.get("result_truncated", False),
                buf.get("prose_answer"),
                buf.get("total_latency_ms", 0),
                buf.get("error_type"),
                buf.get("error_detail"),
            )
        except Exception as e:
            logger.error("audit_flush_failed", request_id=request_id, error=str(e))
