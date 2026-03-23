"""GraphIQ — FastAPI route definitions."""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse

from app.api.schemas import HealthResponse, QueryRequest
from app.services.query_service import QueryResponse

router = APIRouter()


@router.post("/query", response_model=QueryResponse)
async def query_endpoint(body: QueryRequest, request: Request) -> QueryResponse:
    """Process a natural language O2C question and return a structured response.

    The full lifecycle: LLM intent extraction → guardrails → query execution →
    LLM prose generation → graph highlight context.
    """
    service = request.app.state.query_service
    user_id = request.client.host if request.client else "anonymous"
    return await service.answer(body.question, user_id=user_id)


@router.get("/health", response_model=HealthResponse)
async def health_endpoint(request: Request) -> HealthResponse:
    """Return system health: DB connectivity and LLM provider statuses."""
    pg_store = request.app.state.pg_store
    neo4j_store = request.app.state.neo4j_store
    fallback_chain = request.app.state.fallback_chain

    pg_ok = await pg_store.health_check()
    neo4j_ok = await neo4j_store.health_check()

    return HealthResponse(
        postgres=pg_ok,
        neo4j=neo4j_ok,
        sync_lag_seconds=neo4j_store.sync_lag_seconds(),
        llm_providers=fallback_chain.get_health_summary(),
    )


@router.get("/audit/{request_id}")
async def audit_endpoint(request_id: str, request: Request) -> JSONResponse:
    """Retrieve the audit record for a past request."""
    pg_store = request.app.state.pg_store
    row = await pg_store.fetch_one(
        "SELECT * FROM audit.request_logs WHERE request_id = $1", request_id
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Audit record not found")
    return JSONResponse(content=dict(row))


@router.get("/graph/nodes")
async def graph_nodes_endpoint(request: Request) -> JSONResponse:
    """Return Neo4j nodes (up to a limit) and their relationships for initial graph rendering."""
    neo4j_store = request.app.state.neo4j_store
    
    # 1. Fetch nodes
    nodes_cypher = """
        MATCH (n)
        WHERE n:Customer OR n:SalesOrder OR n:Delivery OR n:Invoice
           OR n:JournalEntry OR n:Payment OR n:Product OR n:Plant
        RETURN labels(n)[0] AS label, properties(n) AS props
        LIMIT 500
    """
    node_rows = await neo4j_store.run_query(nodes_cypher, {})
    nodes = [
        {"id": r["props"].get("id", ""), "label": r["label"], **r["props"]}
        for r in node_rows
    ]
    node_ids = list({n["id"] for n in nodes if "id" in n})

    # 2. Fetch edges between these nodes
    edges = []
    if node_ids:
        edges_cypher = """
            MATCH (n)-[r]->(m)
            WHERE n.id IN $node_ids AND m.id IN $node_ids
            RETURN n.id AS source, m.id AS target, type(r) AS rel_type
            LIMIT 1000
        """
        edge_rows = await neo4j_store.run_query(edges_cypher, {"node_ids": node_ids})
        edges = [
            {"source": r["source"], "target": r["target"], "rel_type": r["rel_type"]}
            for r in edge_rows
        ]
        
    return JSONResponse(content={"nodes": nodes, "edges": edges})


@router.get("/graph/neighbors/{node_id}")
async def graph_neighbors_endpoint(node_id: str, request: Request) -> JSONResponse:
    """Return immediate neighbors of a graph node (for expand-on-click)."""
    neo4j_store = request.app.state.neo4j_store
    cypher = """
        MATCH (n {id: $node_id})-[r]-(neighbor)
        RETURN labels(n)[0] AS from_label, properties(n) AS from_props,
               type(r) AS rel_type,
               labels(neighbor)[0] AS to_label, properties(neighbor) AS to_props
        LIMIT 100
    """
    rows = await neo4j_store.run_query(cypher, {"node_id": node_id})
    return JSONResponse(content={"edges": rows})
