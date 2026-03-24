# GraphIQ

**Graph-Based Data Modeling and Query System for SAP Order-to-Cash**

GraphIQ lets users ask natural language questions about SAP O2C business data — orders, deliveries, invoices, payments — and get accurate, data-backed answers with interactive graph visualization. The system translates human language into deterministic database queries, never allowing the LLM to generate SQL or make ungrounded claims.

---

## Table of Contents

- [Architecture Overview](#architecture-overview)
- [Why This Architecture](#why-this-architecture)
- [Database Strategy](#database-strategy)
- [The DSL Contract — How LLM Meets Database](#the-dsl-contract--how-llm-meets-database)
- [LLM Prompting Strategy](#llm-prompting-strategy)
- [Guardrails and Safety](#guardrails-and-safety)
- [Query Execution Pipeline](#query-execution-pipeline)
- [Design Patterns and Rationale](#design-patterns-and-rationale)
- [Failure Modes and Recovery](#failure-modes-and-recovery)
- [What I Would Do Differently at Scale](#what-i-would-do-differently-at-scale)

---

## Architecture Overview

GraphIQ follows a BAES (Blueprint, Assembly, Execution, Supervision) architecture across six layers, each with a distinct responsibility and well-defined boundaries.

```
User Question
    │
    ▼
┌─────────────────────────────┐
│  LLM Intent Parser          │  ← Extracts structured intent (JSON)
│  Fallback: Gemini→Groq→OR   │     Never produces SQL/Cypher
└──────────┬──────────────────┘
           │ Pydantic DSL object
           ▼
┌─────────────────────────────┐
│  Validation + Guardrails    │  ← Schema registry check + domain scope
│  Alias Resolution           │     Fuzzy matching for typo tolerance
└──────────┬──────────────────┘
           │ Resolved, validated intent
           ▼
┌─────────────────────────────┐
│  Intent Router → Handler    │  ← Strategy pattern dispatch
│  Query Builder              │     Deterministic SQL/Cypher assembly
└──────────┬──────────────────┘
           │ Parameterized query
      ┌────┴────┐
      ▼         ▼
┌──────────┐ ┌──────────┐
│PostgreSQL│ │  Neo4j   │      ← Store router decides which DB
│ (truth)  │ │ (graph)  │
└────┬─────┘ └────┬─────┘
     └──────┬─────┘
            │ Raw data
            ▼
┌─────────────────────────────┐
│  LLM Prose Generator        │  ← Converts data to human narrative
│  Grounded: only cites data  │     Never speculates or infers
└──────────┬──────────────────┘
           │
           ▼
     Final Answer
  (prose + data + graph context)
```

The critical design decision visible in this diagram: the LLM appears exactly twice — once to understand the question, once to explain the answer. Everything between those two calls is deterministic Python. This is not accidental. It is the core architectural principle.

---

## Why This Architecture

### The Problem with LLM-Generated Queries

The obvious approach to "natural language to database" is to have the LLM write SQL directly. Systems like Text-to-SQL do this. I rejected this approach for three reasons.

First, **correctness**. SAP O2C data has 19 interconnected entities with composite primary keys, zero-padded document numbers, and implicit cross-document references that do not follow foreign key conventions. An LLM generating SQL against this schema will hallucinate join conditions, confuse `sales_order_items.sales_order` (a foreign key) with `sales_order_headers.sales_order` (a primary key), and produce syntactically valid but semantically wrong queries. In a business system, a wrong answer is worse than no answer.

Second, **security**. Any system that passes LLM output directly into a query engine is one prompt injection away from data exfiltration or corruption. Even with parameterization, if the LLM controls the query structure (table names, join conditions, WHERE clauses), it controls what data is accessed.

Third, **testability**. If the LLM writes queries, every query is non-deterministic. You cannot unit test "does the system produce the correct SQL for this question" because the SQL changes on every run. By separating intent extraction (non-deterministic, LLM) from query construction (deterministic, Python), I can exhaustively test the query layer without ever calling an LLM.

### The Intent DSL Approach

Instead, GraphIQ uses a constrained Domain-Specific Language. The LLM does not produce queries — it produces structured intent objects that describe what the user wants in typed, validated terms. A deterministic Python layer then translates those intents into safe, parameterized queries.

This approach has precedent in production NL-to-data systems. It trades the flexibility of arbitrary SQL for the reliability of a closed operation set. The tradeoff is intentional: GraphIQ cannot answer every conceivable question, but every question it does answer is correct, auditable, and safe.

---

## Database Strategy

### Why Dual Storage: PostgreSQL + Neo4j

This was the most debated architectural decision. The alternatives considered were:

| Option | Pros | Cons | Verdict |
|--------|------|------|---------|
| PostgreSQL only | Simple ops, one store, ACID | Multi-hop traversals require 5+ recursive JOINs, unreadable and slow | Rejected for graph queries |
| Neo4j only | Natural for traversals | Poor at aggregation (GROUP BY, SUM), no ACID for source-of-truth | Rejected for analytics |
| PostgreSQL + Apache AGE | Single DB, graph extension | AGE is immature, limited tooling, uncertain production readiness | Considered but risky |
| **PostgreSQL + Neo4j** | **Each DB does what it is best at** | **Sync complexity, two systems to operate** | **Selected** |

The decision comes down to query patterns. The O2C dataset generates two fundamentally different query types.

**Relational queries** — "top 10 products by billing amount", "list blocked customers", "show me order 12345" — are lookups, filters, and aggregations. PostgreSQL handles these with indexed scans and GROUP BY in milliseconds. These represent roughly 70-80% of expected queries.

**Graph traversal queries** — "trace order 12345 from creation through delivery, billing, and payment", "which orders reached billing but never got paid" — require following chains of document references across 4-6 entities. In PostgreSQL, this becomes a recursive CTE or 5-way LEFT JOIN that is difficult to write, difficult to read, and difficult to optimize. In Neo4j, it is a single `MATCH path = (start)-[*1..4]->(end)` query that returns the full chain with all intermediate nodes.

### PostgreSQL as Source of Truth

PostgreSQL owns all data. Every write goes to PostgreSQL first. The schema mirrors SAP's document structure with some important decisions.

**Composite primary keys** where SAP uses them. `sales_order_items` has a PK on `(sales_order, sales_order_item)` — not a surrogate `id` column. This preserves the SAP document numbering that users already know and query by. When a user says "order 12345", that maps directly to the PK without a lookup table.

**Hard FK constraints for header-to-item relationships** (sales_order_headers → sales_order_items) because these are guaranteed by SAP — an item cannot exist without its header. **Soft lookups (no FK constraint) for cross-document references** (billing_document_items.reference_sd_document → sales_order_headers.sales_order) because SAP allows orphaned references. A billing document might reference a sales order that has been archived or exists in a different system. Enforcing FKs here would reject valid SAP data.

**Indexes are driven by query patterns, not by convention.** The composite index on `(sold_to_party, creation_date)` exists because EntityList queries filter by customer and date range. The index on `(material, net_amount)` exists because Aggregation queries group by product and sum amounts. Each index traces back to a specific intent type and its expected query shape.

### Neo4j as Projective Search Layer

Neo4j receives a projected subset of PostgreSQL data, optimized for graph traversal. The projection makes two key modeling decisions.

**Item tables become relationship properties, not nodes.** In PostgreSQL, `sales_order_items` is a table with rows. In Neo4j, a line item is the connection between an order and a product — it becomes a `CONTAINS_ITEM` relationship with `quantity` and `amount` as properties. This keeps the graph shallow. Tracing Customer → Order → Product is 2 hops, not 3. Every extra hop in a graph traversal multiplies the search space.

**Node properties are a subset of PostgreSQL columns.** A `SalesOrder` node carries `id`, `creation_date`, `total_net_amount`, `sold_to_party` — the fields needed for graph-level filtering and display. Fields like `created_by_user` or `distribution_channel` stay in PostgreSQL only. The graph is lean; the relational store is complete.

**Sync is currently triggered manually or via bootstrap.** The `scripts/neo4j_bootstrap.py` tool performs an idempotent projection from PostgreSQL to Neo4j. It validates soft references before creating edges — if a billing document references a sales order that does not exist in the system, the edge is skipped and logged, not created as a dangling reference.

---

## The DSL Contract — How LLM Meets Database

The DSL (Domain-Specific Language) is the firewall between the non-deterministic LLM layer and the deterministic query layer. It is implemented as Pydantic v2 discriminated unions.

### Intent Types

The system supports six intent types, chosen to cover the question space observable in O2C business operations.

| Intent | Example Question | Query Target | Why It Exists |
|--------|-----------------|-------------|---------------|
| EntityLookup | "Show me order 12345" | PG: PK scan | Single-document retrieval — the most common query |
| EntityList | "List blocked customers" | PG: filtered scan | Multi-row lookup with conditions — second most common |
| Aggregation | "Top products by revenue" | PG: GROUP BY | Rankings and metrics — the analytical use case |
| FlowTrace | "Trace order to payment" | Neo4j: path traversal | End-to-end O2C chain — the differentiating use case |
| BrokenFlow | "Orders without deliveries" | PG or Neo4j | Gap analysis — operationally critical for business users |
| OutOfScope | "What's the weather?" | None | Explicit rejection — not a failure, a designed behavior |
| Compound | "Top 5 products and trace the best" | Mixed | Multi-step with data dependencies — max 3 steps |

Each intent is a Pydantic model with typed fields. The LLM must produce valid JSON matching one of these schemas. If it does not, the structured output parser retries with error feedback.

### The Alias System

The LLM never sees real database column names. It works with semantic aliases.

When the LLM receives a question about "order amount", it produces `{field: "order_amount"}`. The alias resolver maps this to `sales_order_headers.total_net_amount`. When it produces `{entity_type: "invoice"}`, the resolver maps this to `billing_document_headers`.

This design has three benefits. First, the LLM prompt becomes readable — "order_amount" is self-explanatory, while "total_net_amount" requires SAP domain knowledge. Second, the database schema can change (column renames, table restructuring) without touching any LLM prompts — only the alias registry needs updating. Third, fuzzy matching becomes practical on natural language terms: "order_amnt" is 85% similar to "order_amount" and can be auto-corrected, but "ttl_nt_amt" is not similar to anything meaningful.

### The Schema Registry

The schema registry is a Python module (not a database table) that serves as the single source of truth for the entire system. It contains the entity catalog (19 entities with field definitions), the alias registry (semantic name → real column mappings), the join path graph (legal traversals between tables), and aggregation rules (which fields support which operations).

Three consumers read from the same registry: the LLM prompt builder (to tell the LLM what entities and fields are available), the DSL validator (to reject invalid references), and the query builder (to resolve aliases and assemble joins). When the registry changes — a new alias added, a field marked as aggregatable — all three consumers update automatically because they read from the same source. This eliminates the class of bugs where the prompt mentions a field that the validator does not accept, or the validator accepts a join that the query builder cannot execute.

---

## LLM Prompting Strategy

### Provider Architecture

GraphIQ uses a multi-provider LLM strategy with fallback-based rotation, not by preference but by necessity. Free-tier LLM APIs have rate limits, occasional downtime, and variable reliability. The system must be resilient to any single provider being unavailable.

The providers are prioritized: Gemini (highest structured output reliability), Groq (fastest latency), OpenRouter (widest model selection). The fallback chain is not round-robin — it is health-aware. Each provider has a health record tracking consecutive failures, JSON validity rate (what percentage of structured calls return valid, parseable JSON), average latency, and remaining credits where detectable.

When a provider fails 3 consecutive calls, it enters a circuit-breaker "dead" state with an exponential cooldown (1 minute, doubling to max 15 minutes). During cooldown, periodic probe calls test recovery. This prevents the system from repeatedly hammering a down provider while remaining responsive to recovery.

### Two-Call Architecture

The system makes exactly two LLM calls per user request, each with a fundamentally different prompt design.

**Call 1: Intent Extraction** — the LLM receives the user's question, a schema context section (auto-generated from the registry listing all available entities, fields, and aliases), few-shot examples (1-2 per intent type showing question → expected JSON), and strict instructions to return only valid JSON matching the intent schema. The schema context is generated programmatically from the registry at call time — never hand-maintained. This means if a new entity or alias is added to the registry, the prompt updates without code changes.

The structured output parser handles LLM response variability with a 4-stage pipeline: strip markdown fences → JSON parse → Pydantic validation → alias resolution with fuzzy matching. If stages 1-2 fail (malformed JSON), the system retries with a stricter instruction: "Return ONLY a valid JSON object." If stages 3-4 fail (valid JSON but wrong schema), the system retries with the specific error injected: "Field 'invoice_status' is not a known alias. Available alternatives: billing_document_type, goods_movement_status." Most models self-correct on the second attempt when told exactly what went wrong.

**Call 2: Prose Generation** — the LLM receives the original question, the query results as compact JSON, and grounding rules: "only describe what the data shows, do not speculate, cite specific numbers and document IDs." The result is a human-readable narrative anchored in actual data.

The two calls use different reliability requirements. Intent extraction needs strong models with good JSON adherence. Prose generation works with any model that produces coherent text. The fallback chain respects this — a provider with low JSON validity rate is deprioritized for structured calls but may still be used for prose.

### Why Not Fine-Tuning

A fine-tuned model for intent extraction would improve reliability and reduce prompt size. I chose not to fine-tune for two reasons. First, the few-shot prompting approach works well enough with the current intent taxonomy — structured output reliability exceeds 90% on the first attempt with Gemini. Second, fine-tuning creates a hard dependency on a specific model version. When the underlying model updates, the fine-tune may degrade. The few-shot approach is model-agnostic and can be moved between providers without retraining.

---

## Guardrails and Safety

### The Guardrail Chain

Every LLM output passes through a validation chain before any query is built or executed. The chain uses the Chain of Responsibility pattern — each guard inspects the request and either approves (pass to next) or rejects (terminate with a user-friendly message).

The guards execute in cost-optimized order — cheapest checks first.

**Guard 1: Domain Scope** — is this question about O2C data? Catches "what's the weather" and "write me a poem." This is the cheapest check — it just verifies the intent type is not `out_of_scope` (already determined by the LLM) and double-checks for obvious domain violations.

**Guard 2: Entity and Field Validation** — are all entity types and field names referenced in the intent present in the schema registry? This catches LLM hallucinations that passed Pydantic shape validation but reference nonexistent fields. If a field is close to a known alias (fuzzy match ≥ 50%), the rejection message includes suggestions: "Did you mean 'billing_amount' or 'billing_date'?"

**Guard 3: Operator-Type Compatibility** — is the "greater than" operator applied to a numeric or date field, not a string? Is "sum" applied to a decimal field, not a customer name? The registry's field metadata (type, aggregatable, filterable) enables these checks without querying the database.

**Guard 4: Complexity Limiter** — are there fewer than 10 filters? Fewer than 3 group-by fields? Fewer than 3 compound steps? These limits prevent the LLM from producing absurdly complex intents that would generate expensive queries.

**Guard 5: Rate Limiter** — has this user exceeded the request limit? This is last because it requires external state (a counter), while all previous guards operate on the intent object alone.

### Why Guardrails Are Not Prompt-Only

A common approach is to put all safety instructions in the LLM prompt: "do not answer questions outside the dataset domain." This is necessary but insufficient. Prompts are suggestions, not guarantees. A well-crafted prompt reduces the frequency of violations; guardrails in code eliminate them. The prompt says "only produce valid field names"; the FieldGuard enforces it. Both layers are required — the prompt reduces retry frequency, the guardrail ensures correctness.

### SQL Injection Prevention

The query builder enforces four invariants that cannot be violated regardless of LLM output:

1. **No string interpolation of user values** — all values go through parameterized placeholders ($1, $2)
2. **No table or column names from user input** — only names from the registry whitelist
3. **No subqueries or raw SQL fragments** — only assembled clauses from the builder
4. **LIMIT always present** — hard cap at 500 rows even if the intent specifies more

These are not configurable. They are structural properties of the query builder — the code physically cannot produce a query that violates them.

---

## Query Execution Pipeline

### The Store Router

Not every query goes to the same database. The store router examines the validated intent and determines the appropriate target.

EntityLookup, EntityList, and Aggregation always go to PostgreSQL — these are relational operations where PostgreSQL excels. FlowTrace always goes to Neo4j — multi-hop path traversal is Neo4j's strength.

BrokenFlow is the interesting case. "Which orders don't have deliveries?" is a 1-hop gap — sales_order_headers LEFT JOIN outbound_delivery_headers WHERE delivery IS NULL. PostgreSQL handles this efficiently. But "which orders reached billing but were never paid?" is a 3-hop gap (order → delivery → billing → payment) where the system needs to find orders whose chain terminates before payment. This goes to Neo4j as an OPTIONAL MATCH pattern.

The router decides by counting hops between the source and target entities in the schema registry's join path graph. One hop → SQL. Two or more hops → Cypher.

### The Join Resolver

For SQL queries, the most complex component is the join resolver. When a user asks "top products by billing amount for customer ACME", three tables are needed: `billing_document_items` (for amounts), `products` (for product details), and `business_partners` (for customer name). But the LLM does not specify joins — it just references field aliases.

The join resolver uses BFS pathfinding on the schema registry's join path graph to discover the shortest path between any set of required tables. It collects all tables referenced in SELECT, WHERE, and GROUP BY clauses, finds the shortest path from the base table to each additional table, merges the paths (removing duplicate joins), and assembles the JOIN chain.

If the shortest path exceeds 3 joins, the resolver rejects the query — a signal that this request is probably a graph traversal that should go to Neo4j, not a SQL query that should accumulate JOINs.

### Handler Architecture

Each intent type has a dedicated handler following the Strategy pattern. Every handler implements three methods: `build_query` (translate intent to parameterized SQL or Cypher), `execute` (run the query against the appropriate store), and `shape_result` (transform raw data into a compact prose context for the LLM).

The `shape_result` method deserves specific attention. The prose LLM does not receive the full result set — it receives a shaped summary. An EntityList returning 200 rows sends the LLM a summary like "Found 200 orders matching filters. Showing the first 20." An Aggregation sends a ranked list. A FlowTrace sends a linearized path chain: "Order 12345 → Delivery 80001 ($14K) → Invoice 90001 → Payment CLR001 (cleared)." This shaping is critical for prose quality — dumping 500 rows into an LLM prompt produces worse prose than a concise, structured summary.

---

## Design Patterns and Rationale

| Pattern | Where Used | Why This Pattern, Not Another |
|---------|-----------|------------------------------|
| **Adapter** | LLM client (Gemini, Groq, OpenRouter) | Each provider has different SDKs, auth mechanisms, and response formats. The adapter hides this behind a uniform `LLMClient` interface. Switching or adding providers requires zero changes to the rest of the system. |
| **Strategy** | Intent handlers | Each intent type (lookup, list, aggregation, trace, broken flow) requires fundamentally different query construction and result shaping. Strategy lets the router dispatch to the right handler without conditional logic. |
| **Chain of Responsibility** | Guardrail chain | Each guard is independent and composable. New guards can be added without modifying existing ones. The chain short-circuits on first rejection — cheap checks run before expensive ones. |
| **Facade** | QueryService | The FastAPI endpoint calls one method: `QueryService.answer(question)`. It does not know about LLM adapters, query builders, Neo4j, or handlers. This makes the API layer trivially simple and the pipeline testable as a single unit. |
| **Builder** | SQL/Cypher builders | Query construction has ordering constraints (SELECT before WHERE, JOIN before GROUP BY). The builder pattern enforces correct assembly order and always produces parameterized output. |
| **Observer** | Event bus + supervision | Logging, metrics, and audit recording are cross-cutting concerns. The observer pattern keeps them decoupled from business logic — if the logging observer fails, the user query still completes. |
| **Registry** | Intent router, schema registry | The intent router is a dict lookup, not a Chain of Responsibility. When the routing key (intent_type) is unambiguous, a registry is O(1) and deterministic. CoR adds complexity without benefit when there is no ambiguity. |
| **Circuit Breaker** | LLM fallback chain | Prevents cascading failures when an LLM provider goes down. After 3 consecutive failures, the provider is taken offline with exponential cooldown. This avoids wasting user latency on a dead provider. |

A deliberate non-use: I considered using Chain of Responsibility for intent routing (as discussed in initial design), but the discriminator field on the Pydantic model makes routing unambiguous. A dict lookup is faster, simpler, and more debuggable than a chain where each handler inspects the intent and decides whether to handle it.

---

## Failure Modes and Recovery

| Failure | Detection | Recovery | User Experience |
|---------|-----------|----------|----------------|
| LLM returns malformed JSON | Structured parser stage 1-2 | Retry with stricter "return only JSON" instruction | Transparent — user sees normal response with +500ms latency |
| LLM returns wrong schema | Structured parser stage 3-4 | Retry with error feedback injected into prompt | Transparent — most models self-correct on second attempt |
| Primary LLM provider down | 3 consecutive failures → circuit breaker | Automatic fallback to next provider in priority chain | Transparent — different model, same interface |
| All LLM providers down | No healthy provider after selection | Return system error: "AI service temporarily unavailable" | Graceful degradation — clear error, no false data |
| Unknown field in intent | Alias resolver fuzzy match < 50% | Reject with suggestions from registry | User sees: "Did you mean 'billing_amount'?" |
| Query timeout | Statement-level timeout on PG/Neo4j | Return partial result + timeout flag | User sees: "Query timed out. Try narrowing your filters." |
| Neo4j out of sync | `sync_lag_seconds` threshold exceeded | Note data freshness in prose | User sees: "Based on the last manual sync..." |
| Orphaned SAP references | Sync transformer validates soft refs | Skip edge creation, log orphan | No dangling edges in graph — data integrity preserved |
| Cross-currency aggregation | AggregationHandler detects monetary field without currency group-by | Auto-adds warning to prose context | User sees: "Note: results may span multiple currencies" |

---

## What I Would Do Differently at Scale

This system is designed for hundreds of customers. Here is what changes at larger scale, and why I chose not to implement these for v1.

**Automated Sync with Change Data Capture (CDC).** Currently, sync is manual. At larger scale, I would implement CDC via PostgreSQL logical replication or Debezium to provide near-zero-lag sync between the stores. This was omitted to keep the v1 operational footprint small.

**Dedicated prompt cache.** The intent extraction prompt includes the full schema context (all entities, fields, aliases). At 19 entities, this is manageable. At 100+ entities, the prompt becomes unwieldy. A prompt cache that hashes the registry version and reuses compiled prompts would reduce token usage. Some providers (Gemini) already support prefix caching that could be leveraged.

**Query result cache.** Identical questions within a short window hit the database repeatedly. A cache keyed on the resolved intent (post-alias-resolution) would serve frequent queries from memory. The cache invalidation signal is the sync pipeline — when data changes, affected cache entries expire.

**Fine-tuned intent extraction model.** As the intent taxonomy grows beyond 10-15 types, few-shot prompting becomes unreliable. A fine-tuned model trained on (question, intent JSON) pairs from production audit logs would improve accuracy and reduce prompt size. The audit trail already captures every question and its corresponding intent — this is training data accumulating automatically.

**Async graph visualization.** The current frontend loads the full graph on startup. At scale, this becomes impractical. A lazy-loading approach — load only the neighborhood of queried entities, expand on click — is already supported by the `/graph/neighbors/{node_id}` endpoint but the frontend could be more aggressive about progressive loading.

---

## Running the Project

```bash
# Prerequisites
# - Python 3.11+
# - PostgreSQL 15+
# - Neo4j 5+
# - Node.js 18+ (for frontend)

# Backend setup
cd graphiq
cp .env.example .env        # Fill in API keys and DB credentials
pip install -e ".[dev]"
alembic upgrade head         # Create database tables
python scripts/ingest_data.py    # Load SAP dataset
python scripts/neo4j_bootstrap.py  # Initial graph sync

# Start backend
uvicorn app.main:app --reload

# Frontend setup (separate terminal)
cd frontend
npm install
npm run dev

# Run tests
pytest tests/unit/ -v            # No DB needed
pytest tests/integration/ -v     # Requires PG + Neo4j
```

---

## Project Structure

```
graphiq/
├── app/
│   ├── main.py                    # FastAPI app, startup/shutdown, CORS
│   ├── api/routes.py              # POST /query, GET /health, GET /graph/*
│   ├── core/
│   │   ├── config.py              # pydantic-settings, env loading
│   │   ├── registry/              # Schema registry (single source of truth)
│   │   └── dsl/                   # Pydantic intent models, filters, enums
│   ├── llm/
│   │   ├── adapters/              # Gemini, Groq, OpenRouter adapters
│   │   ├── fallback_chain.py      # Health-aware provider selection
│   │   ├── structured_parser.py   # 4-stage JSON extraction pipeline
│   │   └── prompts/               # Auto-generated from registry
│   ├── query/
│   │   ├── sql_builder.py         # Parameterized SQL assembly
│   │   ├── cypher_builder.py      # Neo4j traversal patterns
│   │   ├── join_resolver.py       # BFS pathfinding for auto-JOINs
│   │   └── store_router.py       # Intent → PG or Neo4j decision
│   ├── handlers/                  # One handler per intent type (Strategy)
│   ├── services/
│   │   ├── query_service.py       # Facade: single orchestration entry point
│   │   └── alias_resolver.py      # Fuzzy matching + SAP zero-padding
│   ├── storage/
│   │   ├── postgres.py            # asyncpg pool
│   │   ├── neo4j.py               # Neo4j async driver
│   │   └── sync/                  # PG → Neo4j sync pipeline
│   └── supervision/
│       ├── guardrails/            # 5-guard Chain of Responsibility
│       ├── event_bus.py           # In-process pub/sub
│       └── observers/             # Logging, metrics, audit trail
├── frontend/                      # React + D3/force-graph
├── migrations/                    # Alembic (PG schema versioning)
├── scripts/                       # Data ingestion, Neo4j bootstrap
└── tests/                         # Unit + integration
```

---

*Built with intentional constraints: the LLM interprets and explains, Python decides and executes, and every request is auditable from question to answer.*