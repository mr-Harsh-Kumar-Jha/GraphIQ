"""GraphIQ — FastAPI application entry point.

Wires all dependencies at startup:
- PostgreSQL pool (asyncpg)
- Neo4j async driver
- LLM adapters + FallbackChain
- SchemaRegistry + JoinGraph
- Handlers + IntentRouter
- QueryService facade
- EventBus + Observers
"""
from __future__ import annotations

import asyncio
import structlog
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import settings
from app.core.registry.definitions import JOIN_EDGES
from app.core.registry.join_graph import JoinGraph
from app.core.registry.schema_registry import SchemaRegistry
from app.core.dsl.intents import Intent
from app.handlers.aggregation import AggregationHandler
from app.handlers.broken_flow import BrokenFlowHandler
from app.handlers.compound import CompoundHandler
from app.handlers.entity_list import EntityListHandler
from app.handlers.entity_lookup import EntityLookupHandler
from app.handlers.flow_trace import FlowTraceHandler
from app.handlers.out_of_scope import OutOfScopeHandler
from app.llm.adapters.gemini import GeminiAdapter
from app.llm.adapters.groq import GroqAdapter
from app.llm.adapters.openrouter import OpenRouterAdapter
from app.llm.fallback_chain import FallbackChain
from app.llm.structured_parser import StructuredOutputParser
from app.query.cypher_builder import CypherBuilder
from app.query.sql_builder import SQLBuilder
from app.query.store_router import StoreRouter
from app.router.intent_router import IntentRouter
from app.services.alias_resolver import AliasResolver
from app.services.query_service import QueryService
from app.storage.neo4j import Neo4jStore
from app.storage.postgres import PostgresStore
from app.supervision.event_bus import EventBus
from app.supervision.guardrails.chain import (
    ComplexityGuard, FieldGuard, GuardrailChain, RateGuard, ScopeGuard, TypeGuard,
)
from app.supervision.observers.observers import AuditObserver, LoggingObserver
from app.supervision.request_context import RequestContext

logger = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """FastAPI lifespan: startup wiring and graceful shutdown."""
    logger.info("graphiq_starting")

    # ── Storage ──────────────────────────────────────────────────────────────
    pg_store = await PostgresStore.create(settings.postgres_url)
    neo4j_store = await Neo4jStore.create(
        settings.neo4j_url, settings.neo4j_user, settings.neo4j_password
    )

    # ── Registry + Graph ─────────────────────────────────────────────────────
    registry = SchemaRegistry()
    join_graph = JoinGraph(JOIN_EDGES)

    # ── LLM adapters ─────────────────────────────────────────────────────────
    adapters = {
        "gemini": GeminiAdapter(),
        "groq": GroqAdapter(),
        "openrouter": OpenRouterAdapter(),
    }
    fallback_chain = FallbackChain(adapters)
    parser = StructuredOutputParser()

    # ── Query builders ────────────────────────────────────────────────────────
    sql_builder = SQLBuilder(registry, settings.max_query_limit)
    cypher_builder = CypherBuilder()
    store_router = StoreRouter(registry, join_graph)

    # ── Handlers ──────────────────────────────────────────────────────────────
    lookup_h = EntityLookupHandler(sql_builder, pg_store, neo4j_store, registry)
    list_h = EntityListHandler(sql_builder, pg_store, neo4j_store, registry)
    agg_h = AggregationHandler(sql_builder, pg_store, neo4j_store, registry)
    trace_h = FlowTraceHandler(cypher_builder, pg_store, neo4j_store, registry)
    oos_h = OutOfScopeHandler(pg_store, neo4j_store, registry)

    handler_map = {
        "entity_lookup": lookup_h,
        "entity_list": list_h,
        "aggregation": agg_h,
        "flow_trace": trace_h,
        "out_of_scope": oos_h,
    }

    broken_h = BrokenFlowHandler(
        sql_builder, cypher_builder, store_router,
        pg_store, neo4j_store, registry, join_graph,
    )
    compound_h = CompoundHandler(handler_map, pg_store, neo4j_store, registry)
    handler_map["broken_flow"] = broken_h
    handler_map["compound"] = compound_h

    intent_router = IntentRouter(handler_map)

    # ── Guardrails ────────────────────────────────────────────────────────────
    guardrail_chain = GuardrailChain([
        ScopeGuard(),
        FieldGuard(registry),
        TypeGuard(registry),
        ComplexityGuard(),
        RateGuard(),
    ])

    # ── Alias resolver ────────────────────────────────────────────────────────
    alias_resolver = AliasResolver(registry)

    # ── Event bus + observers ─────────────────────────────────────────────────
    event_bus = EventBus()
    logging_obs = LoggingObserver()
    audit_obs = AuditObserver(pg_store)

    for event in [
        "request_received", "intent_parsed", "guardrail_passed", "guardrail_rejected",
        "alias_corrected", "query_built", "query_executed", "result_shaped",
        "prose_generated", "llm_fallback", "query_timeout", "completed", "error",
    ]:
        event_bus.subscribe(event, logging_obs)
        event_bus.subscribe(event, audit_obs)

    # ── QueryService ──────────────────────────────────────────────────────────
    query_service = QueryService(
        registry=registry,
        fallback_chain=fallback_chain,
        parser=parser,
        guardrail_chain=guardrail_chain,
        alias_resolver=alias_resolver,
        intent_router=intent_router,
        event_bus=event_bus,
        neo4j_store=neo4j_store,
    )

    # ── Attach to app state ───────────────────────────────────────────────────
    app.state.pg_store = pg_store
    app.state.neo4j_store = neo4j_store
    app.state.fallback_chain = fallback_chain
    app.state.query_service = query_service

    logger.info("graphiq_ready")
    yield

    # ── Shutdown ──────────────────────────────────────────────────────────────
    logger.info("graphiq_shutting_down")
    await pg_store.close()
    await neo4j_store.close()


def create_app() -> FastAPI:
    """Create and configure the FastAPI application."""
    app = FastAPI(
        title="GraphIQ",
        description="LLM-native Graph Exploration for SAP O2C Data",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["https://specified-yolanda-streamlen-ecab5888.koyeb.app", "http://localhost:5173", "http://localhost:3000"],
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(router)
    return app


app = create_app()
