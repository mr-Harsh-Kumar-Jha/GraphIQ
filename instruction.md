# O2C Graph-Based Query System — Implementation Instructions

## Project Overview

Build an LLM-native graph exploration system for SAP Order-to-Cash (O2C) data. Users ask natural language questions about orders, deliveries, billing, and payments. The system interprets intent, builds safe parameterized queries, executes against PostgreSQL (relational) and Neo4j (graph traversals), and returns structured answers with natural language prose.

**Architecture framework:** BAES (Blueprint, Assembly, Execution, Supervision)
**Core principle:** The LLM never produces SQL or Cypher. It produces structured intent objects (validated Pydantic models). A deterministic Python layer builds safe queries from those intents.

---

## Tech Stack

| Component | Technology | Reason |
|-----------|-----------|--------|
| Backend framework | FastAPI (async) | Lightweight, non-blocking, easy scaling |
| Primary database | PostgreSQL | Source of truth, high-read workloads, ACID |
| Graph database | Neo4j | Synced projection, multi-hop traversals |
| Schema contracts | Pydantic v2 | Strict typing, discriminated unions, validation |
| Async DB driver | asyncpg | Native PostgreSQL async |
| Neo4j driver | neo4j (async) | Official async Python driver |
| HTTP client | httpx (async) | For LLM API calls |
| LLM providers | Gemini, Groq, OpenRouter | Free tiers, fallback-based rotation |
| Fuzzy matching | thefuzz (or rapidfuzz) | Alias correction for LLM outputs |
| Migrations | Alembic | PostgreSQL schema versioning |

---

## Implementation Order

Follow this exact sequence. Each step depends on the one before it.

### Phase 1: Foundation (implement first)
1. **Schema Registry** — the single source of truth everything references
2. **PostgreSQL schema + Alembic migrations** — tables, indexes, FK strategy
3. **Pydantic DSL models** — intent types, filter model, validation

### Phase 2: Core Engine
4. **Query builder** — SQL builder with join resolver, Cypher builder
5. **Intent handlers** — one handler per intent type, following BaseHandler interface
6. **Intent router** — dict-based dispatch, CompoundHandler with $ref resolution

### Phase 3: LLM Integration
7. **LLM adapter interface** — abstract LLMClient with provider adapters
8. **Fallback chain** — provider health registry, selection algorithm, retry logic
9. **Prompt templates** — intent extraction prompt, prose generation prompt
10. **Structured output parser** — 4-stage pipeline (extract → parse → validate → resolve)

### Phase 4: Data Layer
11. **Neo4j graph model** — node types, relationship types, property mapping
12. **Sync pipeline** — change detector, transformer, Neo4j writer

### Phase 5: Orchestration
13. **QueryService facade** — single entry point orchestrating the full lifecycle
14. **FastAPI endpoints** — POST /query, GET /health, GET /audit/{request_id}

### Phase 6: Supervision
15. **EventBus** — in-process pub/sub for lifecycle events
16. **Guardrail chain** — 5 ordered guards (scope, fields, types, complexity, rate)
17. **Observers** — logging, metrics, audit record assembly
18. **Audit table** — PostgreSQL schema for request traces

---

## Project Structure

```
o2c_query_system/
├── app/
│   ├── main.py                          # FastAPI app, startup, shutdown
│   ├── api/
│   │   ├── routes.py                    # POST /query, GET /health, GET /audit
│   │   └── schemas.py                   # API request/response Pydantic models
│   │
│   ├── core/
│   │   ├── config.py                    # Settings (env vars, provider keys, DB URLs)
│   │   ├── registry/
│   │   │   ├── schema_registry.py       # Entity catalog, field metadata, aliases
│   │   │   ├── join_graph.py            # Join path graph + BFS pathfinding
│   │   │   └── definitions.py           # Static registry data (18 entities, aliases)
│   │   │
│   │   └── dsl/
│   │       ├── intents.py               # Pydantic intent models (discriminated union)
│   │       ├── filters.py               # Filter model (field, operator, value)
│   │       └── enums.py                 # EntityType, OperatorType, AggFunction enums
│   │
│   ├── llm/
│   │   ├── client.py                    # Abstract LLMClient interface
│   │   ├── adapters/
│   │   │   ├── gemini.py                # Gemini adapter
│   │   │   ├── groq.py                  # Groq adapter
│   │   │   └── openrouter.py            # OpenRouter adapter
│   │   ├── fallback_chain.py            # Provider health registry + selection
│   │   ├── structured_parser.py         # 4-stage JSON extraction + validation
│   │   └── prompts/
│   │       ├── intent_extraction.py     # System prompt + schema context builder
│   │       └── prose_generation.py      # Grounding rules + result formatting
│   │
│   ├── query/
│   │   ├── store_router.py              # Intent → PostgreSQL or Neo4j decision
│   │   ├── sql_builder.py               # Clause-by-clause SQL assembly
│   │   ├── cypher_builder.py            # Graph traversal pattern assembly
│   │   └── join_resolver.py             # BFS join pathfinding for SQL
│   │
│   ├── handlers/
│   │   ├── base.py                      # BaseHandler abstract class
│   │   ├── entity_lookup.py             # EntityLookupHandler
│   │   ├── entity_list.py               # EntityListHandler
│   │   ├── aggregation.py               # AggregationHandler
│   │   ├── flow_trace.py                # FlowTraceHandler
│   │   ├── broken_flow.py               # BrokenFlowHandler
│   │   ├── compound.py                  # CompoundHandler with $ref resolution
│   │   └── out_of_scope.py              # OutOfScopeHandler (returns rejection)
│   │
│   ├── router/
│   │   └── intent_router.py             # Dict-based intent_type → handler mapping
│   │
│   ├── services/
│   │   ├── query_service.py             # QueryService facade (main entry point)
│   │   └── alias_resolver.py            # Fuzzy match + correction logic
│   │
│   ├── storage/
│   │   ├── postgres.py                  # asyncpg connection pool, query execution
│   │   ├── neo4j.py                     # Neo4j async driver, query execution
│   │   └── sync/
│   │       ├── change_detector.py       # Poll updated_at timestamps
│   │       ├── transformer.py           # PG rows → Neo4j nodes/relationships
│   │       └── writer.py               # MERGE upserts into Neo4j
│   │
│   └── supervision/
│       ├── event_bus.py                 # In-process pub/sub
│       ├── events.py                    # Event type definitions + payloads
│       ├── request_context.py           # Per-request state + event emitter
│       ├── guardrails/
│       │   ├── chain.py                 # Guardrail chain runner
│       │   ├── scope_guard.py           # Domain scope check
│       │   ├── field_guard.py           # Entity/field registry validation
│       │   ├── type_guard.py            # Operator-type compatibility
│       │   ├── complexity_guard.py      # Limits on filters, groups, steps
│       │   └── rate_guard.py            # Per-user rate limiting
│       └── observers/
│           ├── logging_observer.py      # Structured JSON logs
│           ├── metrics_observer.py      # Counters, histograms, gauges
│           └── audit_observer.py        # Assembles + persists AuditRecord
│
├── migrations/                          # Alembic migrations
│   └── versions/
├── tests/
│   ├── unit/
│   │   ├── test_registry.py
│   │   ├── test_join_resolver.py        # Most testable component
│   │   ├── test_sql_builder.py
│   │   ├── test_cypher_builder.py
│   │   ├── test_alias_resolver.py
│   │   ├── test_guardrails.py
│   │   └── test_handlers.py
│   └── integration/
│       ├── test_query_service.py
│       └── test_sync_pipeline.py
├── alembic.ini
├── pyproject.toml
└── .env.example
```

---

## Layer 1: Schema Registry + DSL

### Schema Registry

The registry is the single source of truth consumed by: LLM prompt builder, DSL validator, alias resolver, join resolver, query builder, and audit logger. It contains four sub-components.

#### Entity Catalog

Define all 18 SAP O2C entities. Each entity has:
- `table_name`: actual PostgreSQL table name
- `primary_key`: list of PK column(s) — many are composite
- `fields`: dict of field definitions with type, filterable flag, sortable flag, aggregatable flag
- `aliases`: list of semantic names the LLM can use for this entity

```
Entity: sales_order_headers
  Table: sales_order_headers
  PK: [sales_order]
  Aliases: ["sales_order", "order", "sales_order_header"]
  Fields:
    sales_order: {type: str, filterable: true, sortable: true, aggregatable: false}
    sales_order_type: {type: str, filterable: true, sortable: false, aggregatable: false}
    sold_to_party: {type: str, filterable: true, sortable: true, aggregatable: false}
    creation_date: {type: date, filterable: true, sortable: true, aggregatable: false}
    total_net_amount: {type: decimal, filterable: true, sortable: true, aggregatable: true}
    transaction_currency: {type: str, filterable: true, sortable: false, aggregatable: false}
    sales_organization: {type: str, filterable: true, sortable: false, aggregatable: false}
    distribution_channel: {type: str, filterable: true, sortable: false, aggregatable: false}
    created_by_user: {type: str, filterable: true, sortable: false, aggregatable: false}
```

Repeat this pattern for all 18 entities from the ER diagram. The complete list:
1. `sales_order_headers`
2. `sales_order_items`
3. `sales_order_schedule_lines`
4. `outbound_delivery_headers`
5. `outbound_delivery_items`
6. `billing_document_headers`
7. `billing_document_items`
8. `billing_document_cancellation`
9. `journal_entry_items_accounts_receivable`
10. `payment_accounts_receivable`
11. `business_partners`
12. `business_partner_address`
13. `customer_company_assignment`
14. `customer_sales_area_assignments`
15. `products`
16. `product_description`
17. `product_plants`
18. `product_storage_locations`
19. `plant`

#### Alias Registry

Maps semantic names (what the LLM produces) to real database references (table.column). The LLM NEVER sees real column names in its output — only aliases.

```
Alias Mappings (examples — expand to cover all fields):

# Entity aliases
"order" → sales_order_headers
"sales_order" → sales_order_headers
"delivery" → outbound_delivery_headers
"billing" → billing_document_headers
"invoice" → billing_document_headers
"payment" → payment_accounts_receivable
"customer" → business_partners
"product" → products

# Field aliases (entity.field format after entity resolution)
"order_number" → sales_order_headers.sales_order
"sales_order_number" → sales_order_headers.sales_order
"order_date" → sales_order_headers.creation_date
"order_amount" → sales_order_headers.total_net_amount
"customer_number" → business_partners.customer
"customer_name" → business_partners.business_partner_full_name
"product_id" → products.product
"product_name" → product_description.product_description
"billing_amount" → billing_document_items.net_amount
"billing_date" → billing_document_headers.billing_document_date
"delivery_date" → outbound_delivery_headers.creation_date
"delivery_number" → outbound_delivery_headers.delivery_document
"payment_date" → payment_accounts_receivable.posting_date
"payment_amount" → payment_accounts_receivable.amount_in_transaction_currency
```

Multiple aliases CAN map to the same (table, column). This is intentional — users say "order amount", "order total", "net amount" etc.

#### Join Path Graph

Defines all legal join paths between tables. Used by the join resolver (BFS pathfinding) and the store router (hop counting). Each edge has:
- `from_table`, `from_column`
- `to_table`, `to_column`
- `join_type`: "inner" (hard FK) or "left" (soft lookup)
- `preferred`: bool — for disambiguation when multiple paths exist

```
Join Paths:

# Hard FK joins (header ↔ items)
sales_order_headers.sales_order → sales_order_items.sales_order [inner, preferred]
sales_order_items.(sales_order, sales_order_item) → sales_order_schedule_lines.(sales_order, sales_order_item) [inner]
outbound_delivery_headers.delivery_document → outbound_delivery_items.delivery_document [inner, preferred]
billing_document_headers.billing_document → billing_document_items.billing_document [inner, preferred]
products.product → product_description.product [inner]
products.product → product_plants.product [inner]
products.product → product_storage_locations.product [inner]
product_plants.plant → plant.plant [inner]

# Soft lookup joins (cross-document — SAP allows orphans)
billing_document_items.reference_sd_document → sales_order_headers.sales_order [left]
outbound_delivery_items.reference_sd_document → sales_order_items.sales_order [left]
billing_document_headers.sold_to_party → business_partners.customer [left, preferred]
billing_document_headers.accounting_document → journal_entry_items_accounts_receivable.accounting_document [left]
sales_order_headers.sold_to_party → business_partners.customer [left, preferred]
journal_entry_items_accounts_receivable.clearing_accounting_document → payment_accounts_receivable.accounting_document [left]
business_partners.business_partner → business_partner_address.business_partner [left]
business_partners.customer → customer_company_assignment.customer [left]
business_partners.customer → customer_sales_area_assignments.customer [left]
billing_document_headers.billing_document → billing_document_cancellation.cancelled_billing_document [left]
sales_order_items.material → products.product [left]
billing_document_items.material → products.product [left]
```

#### Aggregation Rules

Mark which fields support which aggregation functions:
- `sum`: only numeric fields (total_net_amount, net_amount, billing_quantity, requested_quantity, confd_order_qty, amount_in_transaction_currency, gross_weight, net_weight)
- `count`: all fields
- `avg`: only numeric fields
- `min/max`: numeric and date fields
- `count_distinct`: all fields

### DSL Intent Models

Use Pydantic v2 discriminated unions. The `intent_type` field is the discriminator.

#### Base and shared models:

```python
class OperatorType(str, Enum):
    eq = "eq"
    neq = "neq"
    gt = "gt"
    gte = "gte"
    lt = "lt"
    lte = "lte"
    in_ = "in"
    between = "between"
    like = "like"

class AggFunction(str, Enum):
    sum = "sum"
    count = "count"
    avg = "avg"
    min = "min"
    max = "max"
    count_distinct = "count_distinct"

class SortOrder(str, Enum):
    asc = "asc"
    desc = "desc"

class Filter(BaseModel):
    field: str              # Semantic alias — resolved later
    operator: OperatorType
    value: Any              # Type-checked during validation against registry

class SortSpec(BaseModel):
    field: str              # Semantic alias
    order: SortOrder = SortOrder.desc
```

#### Intent types:

```python
class EntityLookupIntent(BaseModel):
    intent_type: Literal["entity_lookup"]
    entity_type: str        # Semantic alias for entity
    identifier: str         # Document number / PK value
    fields: list[str] | None = None  # Specific fields to return, None = all

class EntityListIntent(BaseModel):
    intent_type: Literal["entity_list"]
    entity_type: str
    filters: list[Filter] = []
    sort_by: SortSpec | None = None
    limit: int = Field(default=50, le=500)
    fields: list[str] | None = None

class AggregationIntent(BaseModel):
    intent_type: Literal["aggregation"]
    entity_type: str
    measure: str            # Field alias to aggregate
    agg_fn: AggFunction
    group_by: list[str] = []  # Field aliases
    filters: list[Filter] = []
    sort_by: SortSpec | None = None
    limit: int = Field(default=10, le=100)

class FlowTraceIntent(BaseModel):
    intent_type: Literal["flow_trace"]
    start_entity: str       # Entity alias
    start_id: str           # Document number
    target_entity: str | None = None  # If None, return all reachable
    max_depth: int = Field(default=4, le=6)

class BrokenFlowIntent(BaseModel):
    intent_type: Literal["broken_flow"]
    source_entity: str
    expected_target: str
    filters: list[Filter] = []
    limit: int = Field(default=50, le=500)

class OutOfScopeIntent(BaseModel):
    intent_type: Literal["out_of_scope"]
    reason: str
    suggestion: str | None = None

class CompoundStep(BaseModel):
    step_id: str
    intent: EntityLookupIntent | EntityListIntent | AggregationIntent | FlowTraceIntent | BrokenFlowIntent
    depends_on: str | None = None  # step_id of previous step

class CompoundIntent(BaseModel):
    intent_type: Literal["compound"]
    steps: list[CompoundStep] = Field(min_length=2, max_length=3)

# Discriminated union — the top-level type
Intent = Annotated[
    EntityLookupIntent | EntityListIntent | AggregationIntent |
    FlowTraceIntent | BrokenFlowIntent | OutOfScopeIntent | CompoundIntent,
    Field(discriminator="intent_type")
]
```

### Alias Resolution + Fuzzy Matching

After Pydantic validates the shape, run alias resolution on every string field that references an entity or field name.

Resolution algorithm:
1. Exact match against alias registry → use it
2. No exact match → fuzzy match (Levenshtein) against all aliases
3. Best match score >= 85% → auto-correct, log the correction
4. Best match score 50-85% → return clarification question to user with top 3 suggestions
5. Best match score < 50% → reject as unknown field/entity

SAP document number normalization: pad numeric identifiers with leading zeros to 10 digits. If user says "order 12345", convert to "0000012345" before query execution.

---

## Layer 2: Query Builder

### Store Router

Decide which database handles each intent:

| Intent Type | Store | Reason |
|------------|-------|--------|
| EntityLookup | PostgreSQL | PK lookup, indexed |
| EntityList | PostgreSQL | Filtered scan, indexed |
| Aggregation | PostgreSQL | GROUP BY + SUM, native SQL strength |
| FlowTrace | Neo4j | Variable-length path traversal |
| BrokenFlow (1-hop) | PostgreSQL | LEFT JOIN WHERE NULL |
| BrokenFlow (2+ hops) | Neo4j | OPTIONAL MATCH |
| Compound | Each step independently | Mixed |

For BrokenFlowIntent: count hops between source_entity and expected_target in the join path graph. 1 hop → SQL. 2+ hops → Cypher.

### SQL Builder

Builds parameterized SQL clause-by-clause. NEVER use string interpolation for values. ALWAYS use $1, $2, ... parameter placeholders.

Assembly pipeline:
1. **SELECT**: resolve field aliases → real column names from registry. If `fields` is None, select all columns of the base entity.
2. **FROM**: resolve entity alias → real table name, assign short alias (e.g., `soh` for `sales_order_headers`)
3. **JOIN resolver**: if any referenced field lives on a different table, find shortest join path via BFS on the join graph. Max join depth: 3. If > 3 joins needed, reject (should go to Neo4j).
4. **WHERE**: each Filter → `real_column operator $N`. Type-check value against field type from registry.
5. **GROUP BY**: only for AggregationIntent. Resolve group_by aliases to real columns.
6. **ORDER BY**: resolve sort alias. For aggregation, allow sorting by the aggregate expression (e.g., `SUM(net_amount) DESC`).
7. **LIMIT**: always present. Hard cap at 500 even if not specified.

Output: `(query_string: str, params: tuple)` passed to asyncpg.

**Safety invariants (NEVER violate):**
- No string interpolation of user values — always parameterized
- No field/table names from user input — only from registry whitelist
- No subqueries or raw SQL fragments — only assembled clauses
- LIMIT always present

### Join Resolver

BFS pathfinding on the join graph:
1. Collect all tables needed (from SELECT, WHERE, GROUP BY fields)
2. Start from base table (intent.entity_type)
3. For each additional table: BFS shortest path in join graph
4. Merge all paths, deduplicate joins
5. Use `preferred` flag to break ties when multiple paths exist between same tables
6. If path length > 3: reject with error

This is the most unit-testable component. Test every pair of entities.

### Cypher Builder

For FlowTrace and BrokenFlow (2+ hops):

FlowTrace pattern:
```cypher
MATCH path = (start:{StartLabel} {id: $start_id})
      -[*1..$max_depth]->(end:{EndLabel})
RETURN nodes(path) as nodes, relationships(path) as rels
```

BrokenFlow pattern:
```cypher
MATCH (source:{SourceLabel})
WHERE source.creation_date >= $date_filter
OPTIONAL MATCH (source)-[:{EXPECTED_REL}]->(target:{TargetLabel})
WHERE target IS NULL
RETURN source.id, source.creation_date
LIMIT $limit
```

Node labels and relationship types come from registry. All values parameterized.

---

## Layer 3: PostgreSQL + Neo4j Data Model

### PostgreSQL Schema

#### FK Strategy
- **Hard FKs** (enforced): header ↔ items within same document domain
  - sales_order_headers → sales_order_items
  - sales_order_items → sales_order_schedule_lines
  - outbound_delivery_headers → outbound_delivery_items
  - billing_document_headers → billing_document_items
  - products → product_description, product_plants, product_storage_locations

- **Soft lookups** (no FK constraint): cross-document references
  - billing_document_items.reference_sd_document → sales_order_headers.sales_order
  - outbound_delivery_items.reference_sd_document → sales_order_items.sales_order
  - billing_document_headers.accounting_document → journal_entry_items
  - All sold_to_party / customer references to business_partners

#### Primary Keys
Use composite PKs where SAP does:
- `sales_order_items`: PK(sales_order, sales_order_item)
- `billing_document_items`: PK(billing_document, billing_document_item)
- `outbound_delivery_items`: PK(delivery_document, delivery_document_item)
- `sales_order_schedule_lines`: PK(sales_order, sales_order_item, schedule_line)

Single-column PKs for header tables and master data.

#### Indexing Strategy (query-pattern driven)

```sql
-- Entity list queries (customer + date range)
CREATE INDEX idx_soh_sold_party_date ON sales_order_headers(sold_to_party, creation_date);
CREATE INDEX idx_bdh_sold_party_date ON billing_document_headers(sold_to_party, billing_document_date);

-- Aggregation queries (material + amount)
CREATE INDEX idx_bdi_material_amount ON billing_document_items(material, net_amount);
CREATE INDEX idx_soi_material_amount ON sales_order_items(material, net_amount);

-- Soft lookup joins (cross-document)
CREATE INDEX idx_bdi_ref_sd ON billing_document_items(reference_sd_document);
CREATE INDEX idx_odi_ref_sd ON outbound_delivery_items(reference_sd_document);
CREATE INDEX idx_bdh_accounting ON billing_document_headers(accounting_document);
CREATE INDEX idx_jeiar_clearing ON journal_entry_items_accounts_receivable(clearing_accounting_document);

-- Sync support
-- Add updated_at TIMESTAMP DEFAULT NOW() to every table
-- CREATE INDEX idx_{table}_updated ON {table}(updated_at);
```

#### Additional columns for system use
Add to EVERY table:
- `updated_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()` — for sync change detection
- Trigger: auto-update `updated_at` on any row modification

#### Audit schema
```sql
CREATE SCHEMA audit;
CREATE TABLE audit.request_logs (
    request_id UUID PRIMARY KEY,
    timestamp TIMESTAMPTZ NOT NULL,
    user_question TEXT NOT NULL,
    llm_provider_used VARCHAR(50),
    intent_raw_json JSONB,
    intent_validated JSONB,
    corrections_applied JSONB,
    guardrail_result VARCHAR(20),
    guardrail_detail TEXT,
    query_generated TEXT,
    query_params JSONB,
    store_used VARCHAR(10),
    query_ms INTEGER,
    result_row_count INTEGER,
    result_truncated BOOLEAN,
    prose_answer TEXT,
    total_latency_ms INTEGER,
    error_type VARCHAR(50),
    error_detail TEXT
);
CREATE INDEX idx_audit_timestamp ON audit.request_logs(timestamp);
```

### Neo4j Graph Model

#### Node Types (from PG header tables + master data)

| Node Label | Source PG Table | Key Properties |
|-----------|----------------|----------------|
| Customer | business_partners | id, name, category, is_blocked |
| SalesOrder | sales_order_headers | id, creation_date, total_net_amount, sold_to_party |
| Delivery | outbound_delivery_headers | id, creation_date, status |
| Invoice | billing_document_headers | id, creation_date, total_net_amount, type |
| JournalEntry | journal_entry_items_accounts_receivable | id, fiscal_year, amount, posting_date |
| Payment | payment_accounts_receivable | id, amount, posting_date |
| Product | products | id, type, group, base_unit |
| Plant | plant | id, name, sales_organization |

**Node properties are a SUBSET** of PG columns — only fields needed for graph-level filtering and display. Full data stays in PostgreSQL.

#### Relationship Types

| Relationship | From | To | Properties | Source |
|-------------|------|-----|-----------|--------|
| PLACED | Customer | SalesOrder | — | sold_to_party join |
| CONTAINS_ITEM | SalesOrder | Product | quantity, amount | sales_order_items |
| DELIVERED_BY | SalesOrder | Delivery | — | delivery_items.reference_sd_document |
| BILLED_BY | Delivery | Invoice | amount | billing_items.reference_sd_document |
| POSTED_AS | Invoice | JournalEntry | — | billing_headers.accounting_document |
| CLEARED_BY | JournalEntry | Payment | — | clearing_accounting_document |
| PRODUCED_AT | Product | Plant | — | product_plants |

**Critical design rule:** Item tables (sales_order_items, billing_document_items, outbound_delivery_items) do NOT become nodes. They become relationship properties. This keeps the graph shallow — Customer → Order → Product is 2 hops, not 3.

#### Sync Strategy

**Two modes:**

1. **Full sync (bootstrap):** Read all PG tables, transform to nodes + edges, bulk-load into Neo4j via UNWIND batch inserts. Run on: initial setup, disaster recovery, schema migration.

2. **Incremental sync (steady state):** Poll `updated_at` column every 10-30 seconds. Fetch changed rows, transform, MERGE upsert into Neo4j.

**Sync pipeline components:**
- `ChangeDetector`: queries each table for `WHERE updated_at > last_sync_timestamp`, maintains last_sync per table
- `Transformer`: maps PG rows to Neo4j node/relationship operations using configuration alongside the schema registry. Validates soft references exist before creating edges (skip orphans, log them).
- `Writer`: executes MERGE operations in Neo4j. Uses parameterized Cypher. Batches writes (100 operations per transaction).

**Sync failure handling:**
- Neo4j down → queue changes in memory, retry with exponential backoff
- Schema version mismatch → block graph queries, trigger full sync
- Orphaned soft references → skip edge creation, log for investigation

**Consistency guarantee:** Every query response includes `sync_lag_seconds` so the prose generator can note data freshness.

---

## Layer 4: LLM Adapter + Fallback Chain

### LLMClient Interface

```python
class LLMClient(ABC):
    @abstractmethod
    async def generate_structured(
        self, prompt: str, schema: type[BaseModel], context: str = ""
    ) -> BaseModel:
        """Returns a validated Pydantic model instance."""

    @abstractmethod
    async def generate_text(self, prompt: str, context: str = "") -> str:
        """Returns free-form text."""

    @abstractmethod
    async def health_check(self) -> ProviderHealth:
        """Returns current provider health status."""
```

Each adapter (Gemini, Groq, OpenRouter) implements this interface, hiding SDK differences, auth, rate limits, and response parsing.

### Provider Health Registry

In-memory, per-instance. Tracks per provider:
- `status`: healthy | degraded | dead
- `credits_remaining`: from API response headers where available
- `avg_latency_ms`: rolling average over last 50 calls
- `consecutive_fails`: reset to 0 on success
- `last_success`: timestamp
- `json_validity_rate`: percentage of generate_structured calls returning valid JSON (rolling 100 calls)
- `cooldown_until`: datetime, only set when status = dead

State transitions:
- `consecutive_fails >= 3` → status = dead, set cooldown (starts at 1 min)
- While dead: probe call every cooldown_interval. Success → healthy. Failure → double cooldown (max 15 min).
- Success at any time → reset consecutive_fails to 0

### Provider Selection Algorithm

For each LLM call:
1. Filter out dead providers and those in cooldown
2. For `generate_structured` calls: filter out providers with `json_validity_rate < 60%`
3. Rank remaining by: providers with `credits_remaining > 100` first, then by configured priority order
4. If no healthy provider: return system error

Configured priority order (default): Gemini > Groq > OpenRouter
This is configurable in .env.

### Retry Strategy

Max 3 total attempts across all providers per request.

On failure:
1. Increment `consecutive_fails` for that provider
2. If `consecutive_fails >= 3`: mark dead, start cooldown
3. Re-run provider selector, try next best provider
4. If all providers exhausted: return error

### Structured Output Parser (4-stage pipeline)

Stage 1 — JSON extraction: strip markdown fences (```json ... ```), find first { to last }, handle trailing commas
Stage 2 — JSON parse: `json.loads()`, catch JSONDecodeError
Stage 3 — Pydantic validation: parse into discriminated union Intent type
Stage 4 — Alias resolution + scope check: every field/entity ref → registry lookup + fuzzy match

**Retry on parse failure:**
- Stage 1-2 fail → retry same provider with stricter instruction: "Return ONLY a valid JSON object. No markdown, no explanation."
- Stage 3-4 fail → retry with error feedback injected into prompt: "Your previous response was invalid: field 'invoice_status' is not a known alias. Available aliases: ..."

### Prompt Templates

#### Intent Extraction Prompt

Structure:
1. System prompt (static): role definition, behavioral constraints
2. Schema context (AUTO-GENERATED from registry): available entities, fields, aliases, operators, intent types
3. Few-shot examples (versioned, 1-2 per intent type, ~10 total)
4. User query (per-request)

The schema context MUST be auto-generated from the registry at startup. When the registry changes, the prompt updates automatically. Never hand-maintain the schema section.

System prompt core instructions:
```
You are an O2C (Order-to-Cash) data analyst. You interpret user questions about
SAP business data including sales orders, deliveries, billing documents, payments,
customers, and products.

Given a user question, return a JSON object matching one of the defined intent types.
Use ONLY the entity names and field aliases provided in the schema below.
If the question is outside the O2C domain, return an out_of_scope intent.
If the question requires multiple steps, return a compound intent (max 3 steps).

Return ONLY valid JSON. No markdown, no explanation, no additional text.
```

#### Prose Generation Prompt

```
You present O2C data findings in clear, concise business language.
You are given the user's original question and the query results.

Rules:
- Only describe what the data shows. Do NOT speculate or infer beyond the data.
- If the result set is empty, say "No matching records found" and suggest possible reasons.
- Cite specific numbers, dates, and document IDs from the data.
- Keep the response under 200 words unless the data requires more detail.
- For flow traces, describe the chain step by step with key values at each node.
- If results were truncated, mention this: "Showing first N of M total results."
```

---

## Layer 5: Intent Router + Handlers

### Intent Router

Simple dict-based dispatch. NOT Chain of Responsibility — the discriminator field makes routing unambiguous.

```python
HANDLER_REGISTRY: dict[str, type[BaseHandler]] = {
    "entity_lookup": EntityLookupHandler,
    "entity_list": EntityListHandler,
    "aggregation": AggregationHandler,
    "flow_trace": FlowTraceHandler,
    "broken_flow": BrokenFlowHandler,
    "compound": CompoundHandler,
    "out_of_scope": OutOfScopeHandler,
}
```

### BaseHandler Interface

```python
class BaseHandler(ABC):
    def __init__(self, sql_builder, cypher_builder, pg_pool, neo4j_driver, registry):
        # Injected dependencies — handlers are stateless, instantiated once at startup

    async def handle(self, intent: BaseModel, context: RequestContext) -> HandlerResult:
        query, params = self.build_query(intent)
        raw_data = await self.execute(query, params)
        prose_context = self.shape_result(raw_data, intent)
        return HandlerResult(
            prose_context=prose_context,
            raw_data=raw_data,
            row_count=len(raw_data),
            truncated=len(raw_data) >= intent.limit if hasattr(intent, 'limit') else False,
            store_used=self.store_type,
            query_ms=execution_time
        )

    @abstractmethod
    def build_query(self, intent) -> tuple[str, tuple]: ...

    @abstractmethod
    def shape_result(self, raw_data: list[dict], intent) -> str: ...
```

### Handler-Specific Behavior

#### EntityLookupHandler
- Store: PostgreSQL
- build_query: `SELECT * FROM {table} WHERE {pk} = $1`
- shape_result: all fields as compact JSON key-value pairs

#### EntityListHandler
- Store: PostgreSQL
- build_query: uses SQL builder with filters, sort, limit
- shape_result: count + first 20 rows as compact JSON. "Found N {entity} matching filters."

#### AggregationHandler
- Store: PostgreSQL
- build_query: SQL builder with GROUP BY, aggregate function, sort, limit
- shape_result: ranked list with values. "Top N: {item} ({value}), ..."

#### FlowTraceHandler
- Store: Neo4j
- build_query: Cypher variable-length path traversal
- shape_result: linearized path chain. "Order → Delivery → Invoice → Payment" with key values at each node.

#### BrokenFlowHandler
- Store: PostgreSQL (1-hop) or Neo4j (2+ hops)
- build_query: LEFT JOIN WHERE NULL (SQL) or OPTIONAL MATCH WHERE null (Cypher)
- shape_result: count + top 5 oldest examples. "N {source} have no {target}. Oldest: ..."

#### CompoundHandler
- Orchestrates sub-handlers sequentially
- Resolves `$step_N.results[index].field_name` references between steps
- On partial failure: return completed steps + error message for failed step
- shape_result: concatenated summaries from each step with step labels

#### OutOfScopeHandler
- No query execution
- Returns rejection message directly from intent.reason and intent.suggestion

### QueryService Facade

Single entry point: `async def answer(question: str) -> QueryResponse`

Lifecycle:
1. Create RequestContext (request_id, timestamp, user question)
2. Emit `request_received` event
3. Call LLM intent extraction (via fallback chain)
4. Emit `intent_parsed` event
5. Run guardrail chain
6. Emit `guardrail_passed` or `guardrail_rejected` event
7. Run alias resolution + fuzzy match
8. Route to handler via IntentRouter
9. Handler: build_query → execute → shape_result
10. Emit `query_executed` event
11. Call LLM prose generation with ProseContext
12. Emit `prose_generated` event
13. Assemble final response (prose + raw_data + metadata)
14. Emit `completed` event
15. Return QueryResponse

---

## Layer 6: Supervision + Guardrails

### Event Bus

In-process pub/sub. NOT Kafka/RabbitMQ — unnecessary for this scale.

```python
class EventBus:
    _listeners: dict[EventType, list[Callable]]

    def subscribe(self, event_type: EventType, callback: Callable) -> None
    async def emit(self, event_type: EventType, payload: dict) -> None
        # Calls all subscribers. Callbacks are async, fire-and-forget.
        # Wrap each callback in try/except — observers NEVER crash the pipeline.
```

Event types: `request_received`, `intent_parsed`, `guardrail_passed`, `guardrail_rejected`, `alias_corrected`, `query_built`, `query_executed`, `result_shaped`, `prose_generated`, `llm_fallback`, `query_timeout`, `completed`, `error`

### Guardrail Chain

Chain of Responsibility pattern. Each guard inspects and either passes or rejects.

Execution order (cheapest first):
1. **ScopeGuard**: is intent_type valid? Is it about O2C data?
2. **FieldGuard**: are all entity_type and field references in the registry?
3. **TypeGuard**: are operators compatible with field types? (e.g., no `sum` on string)
4. **ComplexityGuard**: filters count ≤ 10? group_by fields ≤ 3? compound steps ≤ 3?
5. **RateGuard**: has user exceeded 30 requests per minute?

Rejection output: `GuardrailReject(guard_name, code, user_message, suggestions)`
- `user_message` is friendly, not technical
- `suggestions` includes fuzzy-matched alternatives when applicable

### Observers

Register at startup. Async, fire-and-forget.

**LoggingObserver:** writes structured JSON log per event. Log level by event type (info for success, warn for corrections/fallbacks, error for failures).

**MetricsObserver:** updates counters (requests, failures, fallbacks per provider), histograms (latency per stage), gauges (provider health status). Expose via /metrics endpoint for monitoring.

**AuditObserver:** accumulates events for a request in memory. On `completed` or `error` terminal event, assembles a single AuditRecord and writes to audit.request_logs in one DB call.

---

## Coding Practices

### Async Everywhere
- All LLM calls, DB queries, and Neo4j operations MUST be async
- Use `asyncpg` pool for PostgreSQL
- Use `neo4j.AsyncDriver` for Neo4j
- Use `httpx.AsyncClient` for LLM API calls
- Never block the FastAPI event loop

### Error Handling
- Custom exception hierarchy: `O2CBaseError` → `LLMError`, `QueryBuildError`, `StoreError`, `GuardrailError`, `ValidationError`
- Never let internal exceptions reach the API response. Catch at the QueryService facade level and return structured error responses.
- LLM errors trigger fallback, not user-facing errors (unless all providers fail)

### Type Safety
- All function signatures fully typed
- Pydantic models for every boundary: API input, LLM output, handler result, audit record
- Use `Literal` types and `Enum` for closed sets
- Return types explicitly declared — no `Any` returns

### Testing Priority
1. **Join resolver BFS** — exhaustively test all entity pair paths (most testable, highest impact)
2. **SQL builder** — test that each intent type produces correct parameterized SQL
3. **Guardrails** — test each guard independently with valid and invalid inputs
4. **Alias resolver** — test exact match, fuzzy match, and rejection thresholds
5. **Structured parser** — test with real LLM outputs (valid JSON, malformed, markdown-wrapped, etc.)
6. **Integration: QueryService** — test full lifecycle with mocked LLM and real DB

### Configuration
Use environment variables via pydantic-settings:
```
# Database
POSTGRES_URL=postgresql+asyncpg://user:pass@localhost:5432/o2c
NEO4J_URL=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=...

# LLM Providers
GEMINI_API_KEY=...
GROQ_API_KEY=...
OPENROUTER_API_KEY=...

# Provider priority (comma-separated)
LLM_PROVIDER_PRIORITY=gemini,groq,openrouter

# Limits
MAX_JOIN_DEPTH=3
MAX_QUERY_LIMIT=500
MAX_COMPOUND_STEPS=3
SYNC_INTERVAL_SECONDS=15
RATE_LIMIT_PER_MINUTE=30
```

---

## API Endpoints

### POST /query
Request:
```json
{
    "question": "Top 5 products by billing amount this quarter"
}
```

Response:
```json
{
    "request_id": "uuid",
    "answer": "The top 5 products by billing amount this quarter are: Product A ($45,200), ...",
    "data": [
        {"product": "MAT001", "product_name": "Widget A", "total_billing": 45200.00},
        ...
    ],
    "metadata": {
        "intent_type": "aggregation",
        "store_used": "pg",
        "query_ms": 23,
        "total_ms": 1847,
        "row_count": 5,
        "truncated": false,
        "sync_lag_seconds": 12,
        "corrections_applied": []
    }
}
```

### GET /health
Returns system health: DB connectivity, Neo4j connectivity, LLM provider statuses, sync lag.

### GET /audit/{request_id}
Returns the full AuditRecord for debugging.

---

## Edge Cases and Known Challenges

1. **SAP leading zeros:** Document numbers are 10-digit zero-padded strings. Normalize user input: "12345" → "0000012345". Apply this in alias resolution, not in the query builder.

2. **Ambiguous join paths:** When multiple paths exist between two tables (e.g., billing → customer via sold_to_party vs. via journal entry), the registry's `preferred` flag disambiguates. The intent's entity_type provides additional context.

3. **Compound intent $ref resolution:** Path format is `$step_N.results[index].field_name`. Only integer indices, no expressions, no wildcards. If step failed or index out of range or field missing → stop compound execution, return partial results.

4. **LLM produces unknown intent_type:** Pydantic discriminated union rejects it. Retry with error feedback.

5. **Empty result sets:** Not an error. shape_result produces "No matching records found." Prose generator receives empty data context and should say so explicitly, not speculate.

6. **Neo4j sync lag:** Every response includes `sync_lag_seconds`. Prose generator can note "data as of N seconds ago" when lag > 60s.

7. **Billing cancellations:** billing_document_cancellation contains cancelled invoices. FlowTrace should handle these as terminal nodes with a "cancelled" flag. BrokenFlow queries should optionally include/exclude cancelled documents.

8. **Multiple deliveries per order:** One SalesOrder can have multiple Deliveries (partial deliveries). FlowTrace returns ALL paths, not just the first one. shape_result presents them as parallel branches.

9. **Cross-currency aggregation:** Some aggregation queries may span multiple currencies (transaction_currency field). The system should NOT blindly sum amounts across currencies. AggregationHandler must check if group_by includes currency when aggregating monetary fields. If not, add a warning to the prose context.