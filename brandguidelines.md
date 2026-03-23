# GraphIQ — Brand & Engineering Guidelines

## Product Identity

**Name:** GraphIQ
**Tagline:** "Understand your business flows instantly"

GraphIQ is a production-grade, LLM-native graph exploration system for SAP Order-to-Cash data. It communicates strong backend fundamentals, thoughtful LLM usage, and real-world system design.

---

## Design Principles

### 1. Clarity over complexity
- Graphs should not overwhelm — show only relevant nodes
- Code should read like documentation — intent obvious from structure
- Every abstraction must justify its existence with a concrete benefit

### 2. Data trust
- Every answer must feel reliable — no hallucination, no speculation
- The LLM never produces queries — it produces validated intent objects
- All data flows through typed contracts (Pydantic models at every boundary)

### 3. Explorability
- Users should feel like they are discovering insights, not fighting a tool
- Errors are guiding, not blocking — suggest alternatives on failure
- The system explains what it did (audit trail) and what it could not do (guardrail messages)

### 4. Deterministic where possible
- Query building is pure Python — no LLM involvement in SQL/Cypher generation
- Routing is dict-based lookup, not heuristic
- Only two components involve LLM non-determinism: intent parsing and prose generation. Everything else is testable without an LLM.

---

## Communication Tone

### Chat responses (prose generation)
- Professional and analytical — no fluff, no hedging
- Cite specific numbers, document IDs, and dates from the data
- Never say "It seems like..." — always assert what the data shows

Examples:
- BAD: "It looks like there might be some orders that haven't been delivered yet."
- GOOD: "47 orders have no associated delivery. The oldest is Order 0000010023, created on January 3, 2026."

- BAD: "Based on my analysis, the top product appears to be..."
- GOOD: "The highest-billed product is MAT-4500 (Industrial Valve) at $128,400 across 23 invoices."

### Error messages
Clear, strict, and helpful:
- Domain rejection: "This system is designed only for O2C dataset queries. Try asking about orders, deliveries, billing, or payments."
- Field not found: "I couldn't find a field called 'invoice_status'. Did you mean 'billing_document_type' or 'goods_movement_status'?"
- No results: "No matching records found for the given filters. Try broadening the date range or removing the customer filter."

---

## Engineering Standards

### Naming Conventions

| Element | Convention | Example |
|---------|-----------|---------|
| Files | snake_case | `sql_builder.py`, `flow_trace.py` |
| Classes | PascalCase | `FlowTraceHandler`, `SchemaRegistry` |
| Functions/methods | snake_case | `build_query()`, `shape_result()` |
| Constants | UPPER_SNAKE | `MAX_JOIN_DEPTH`, `HANDLER_REGISTRY` |
| Pydantic models | PascalCase + Intent/Filter/Config suffix | `AggregationIntent`, `Filter`, `ProviderHealth` |
| Enum members | snake_case | `OperatorType.count_distinct` |
| Database tables | snake_case (match SAP naming) | `sales_order_headers` |
| API endpoints | lowercase with slashes | `POST /query`, `GET /health` |

### Code Organization

Every module follows this structure:
1. Imports (stdlib → third-party → local, separated by blank lines)
2. Constants
3. Type definitions / Pydantic models (if small, otherwise separate file)
4. Main class or function
5. No loose code at module level — everything inside functions or classes

### Docstrings

Use Google-style docstrings on every public class and function:

```python
async def generate_structured(
    self, prompt: str, schema: type[BaseModel], context: str = ""
) -> BaseModel:
    """Extract structured intent from natural language using the LLM.

    Args:
        prompt: The user's natural language question.
        schema: Pydantic model class to validate against.
        context: Additional schema context injected into the prompt.

    Returns:
        Validated Pydantic model instance matching the intent.

    Raises:
        LLMError: If all providers fail after retries.
        ValidationError: If structured output cannot be parsed after retries.
    """
```

### Async Discipline

- ALL I/O operations are async: database queries, LLM calls, Neo4j operations
- Never use `time.sleep()` — use `asyncio.sleep()`
- Never use `requests` — use `httpx.AsyncClient`
- Never use synchronous DB drivers — use `asyncpg` and `neo4j.AsyncDriver`
- Connection pools created at startup (`@app.on_event("startup")`), closed at shutdown
- Use `asyncio.gather()` for independent concurrent operations (e.g., health checks)

### Error Handling Philosophy

```python
# WRONG: bare except, swallows everything
try:
    result = await self.execute(query)
except:
    return None

# WRONG: catches too broadly
try:
    result = await self.execute(query)
except Exception as e:
    logger.error(f"Query failed: {e}")
    raise

# RIGHT: specific exceptions, structured logging, proper propagation
try:
    result = await self.pg_pool.fetch(query, *params)
except asyncpg.PostgresError as e:
    context.emit("query_error", {"error": str(e), "query": query})
    raise StoreError(f"PostgreSQL query failed: {e}") from e
except asyncio.TimeoutError:
    context.emit("query_timeout", {"query": query})
    raise StoreError("Query exceeded timeout limit") from None
```

Custom exception hierarchy:
```
O2CBaseError
├── LLMError              # All LLM-related failures
│   ├── ProviderError     # Specific provider failure
│   └── ParseError        # Structured output parsing failure
├── QueryBuildError       # SQL/Cypher assembly failures
├── StoreError            # Database execution failures
├── GuardrailError        # Guardrail rejections (not really errors — expected behavior)
└── ValidationError       # DSL/alias validation failures
```

### Type Safety Rules

- All function signatures MUST have full type annotations (params + return)
- No `Any` return types — always specific
- Use `Literal` for closed string sets
- Use `Enum` for values that map to behavior
- Pydantic `BaseModel` at every boundary: API input, LLM output, handler result, audit record, event payloads
- Use `TypeAlias` for complex union types
- Run `mypy --strict` — zero errors is the target

### Logging Standards

Use structured JSON logging (via `structlog` or `python-json-logger`):

```python
logger.info(
    "query_executed",
    request_id=context.request_id,
    store="pg",
    query_ms=elapsed_ms,
    row_count=len(results),
    intent_type="aggregation"
)
```

Log levels:
- `DEBUG`: internal state changes (provider selection, alias resolution steps)
- `INFO`: normal lifecycle events (request received, query executed, response sent)
- `WARNING`: recoverable issues (LLM fallback triggered, alias auto-corrected, result truncated)
- `ERROR`: failures requiring attention (all LLM providers down, DB connection lost, sync failure)

Never log:
- Raw API keys or credentials
- Full LLM prompts in production (too verbose — log prompt hash + length instead)
- Raw user PII beyond what's in the question

### Dependency Injection

Handlers and services receive their dependencies through constructor injection, not global imports:

```python
# RIGHT: explicit dependencies, testable
class AggregationHandler(BaseHandler):
    def __init__(self, sql_builder: SQLBuilder, pg_pool: Pool, registry: SchemaRegistry):
        self.sql_builder = sql_builder
        self.pg_pool = pg_pool
        self.registry = registry

# WRONG: hidden global dependency, untestable
class AggregationHandler(BaseHandler):
    def handle(self, intent):
        from app.core.registry import get_registry  # hidden coupling
        registry = get_registry()
```

Wire dependencies at startup in `main.py` and pass them down.

### Testing Standards

Test naming: `test_{method}_{scenario}_{expected_result}`

```python
def test_join_resolver_orders_to_customer_returns_one_hop():
    ...

def test_sql_builder_aggregation_with_filters_produces_parameterized_where():
    ...

def test_guardrail_field_guard_rejects_unknown_field_with_suggestions():
    ...
```

Every test must:
- Test ONE behavior
- Have clear arrange/act/assert sections
- Use fixtures for shared setup (database connections, registry instances)
- Mock LLM calls in unit tests — never hit real APIs
- Use real database in integration tests (Docker Compose for PG + Neo4j)

### Git Practices

Branch naming: `feature/{layer}-{component}` or `fix/{layer}-{component}`
Examples: `feature/layer1-schema-registry`, `fix/layer4-groq-adapter-timeout`

Commit messages: conventional commits
- `feat(registry): add alias resolution with fuzzy matching`
- `fix(sql-builder): handle ambiguous join path for billing-to-customer`
- `test(join-resolver): add exhaustive entity pair path tests`
- `refactor(handlers): extract shape_result into base class template`

---

## What NOT To Do

1. **Fancy UI without correctness** — the query must be right before the graph looks pretty
2. **Overusing LLM** — the LLM does exactly two things: parse intent and write prose. Everything else is deterministic Python.
3. **No guardrails** — every LLM output is validated before execution. Period.
4. **Static answers** — the system queries real data every time. No cached responses for user queries.
5. **String concatenation for SQL** — ALWAYS parameterized. No exceptions.
6. **Synchronous I/O in async context** — blocks the entire event loop for all users.
7. **Catch-all exception handlers** — be specific, log context, propagate correctly.
8. **Hardcoded provider logic** — all LLM interaction goes through the adapter interface. No direct Gemini/Groq SDK calls outside adapter classes.

---

## Demo Strategy

When presenting GraphIQ:

1. Start with graph exploration — show the O2C network visually
2. Ask a trace query: "Trace order 12345 from order through to payment"
3. Ask an aggregation: "Top 5 products by billing amount this quarter"
4. Ask a broken flow: "Which orders have no deliveries?"
5. Show an out-of-scope rejection: "What's the weather?" → graceful domain boundary
6. Show the audit trail: "Here's exactly what happened for that last query"
7. Trigger a fallback: demonstrate LLM rotation when primary provider is down

The reviewer should think: **"This person knows how to build production-grade AI systems."**