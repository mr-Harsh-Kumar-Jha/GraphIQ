"""GraphIQ — API request/response Pydantic schemas."""
from __future__ import annotations

from typing import Any

from pydantic import BaseModel


class QueryRequest(BaseModel):
    """POST /query request body."""
    question: str


class HealthProviderStatus(BaseModel):
    status: str
    consecutive_fails: int
    avg_latency_ms: float
    json_validity_rate: float
    cooldown_until: str | None


class HealthResponse(BaseModel):
    """GET /health response."""
    postgres: bool
    neo4j: bool
    sync_lag_seconds: float
    llm_providers: dict[str, Any]
