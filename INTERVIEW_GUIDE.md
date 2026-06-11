# Universal Data Assistant — Interview Guide

Technical reference for senior backend and AI engineer interviews.  
Each section covers one design decision: the context, the choice, the trade-offs, and the code evidence.

---

## Table of Contents

1. [System Architecture Decisions](#1-system-architecture-decisions)
2. [Why LangGraph Was Used for the Agent Layer](#2-why-langgraph-was-used-for-the-agent-layer)
3. [Why QueryPlan Was Chosen Over Raw LLM Code](#3-why-queryplan-was-chosen-over-raw-llm-code)
4. [How SQL Injection Is Prevented](#4-how-sql-injection-is-prevented)
5. [How CRUD Approval Works End-to-End](#5-how-crud-approval-works-end-to-end)
6. [Why Forecasting Is Deterministic](#6-why-forecasting-is-deterministic)
7. [How SQL Pushdown Works](#7-how-sql-pushdown-works)
8. [How Database Credentials Are Secured](#8-how-database-credentials-are-secured)
9. [Why Services Are Separated](#9-why-services-are-separated)
10. [Common Interviewer Questions with Model Answers](#10-common-interviewer-questions-with-model-answers)

---

## 1. System Architecture Decisions

### Decision: Clean vertical layering — API → Service → Schema

**Context.** The system spans nine functional phases: file uploads, NL analytics, charting, PDF reports, database connectivity, NL-to-SQL, CRUD operations, forecasting, and agentic orchestration. Keeping these concerns in one layer would produce a monolith that is hard to test and impossible to evolve.

**Choice.** Three strict layers:

```
HTTP boundary      →   FastAPI routers  (app/api/routes/)
Business logic     →   Services         (app/services/)
Data contracts     →   Pydantic schemas (app/schemas/)
```

- Routers own only request parsing, dependency injection, and HTTP error mapping.  
- Services own all business logic, LLM calls, pandas operations, and SQL execution.  
- Schemas define every input/output contract; no raw `dict` crosses a service boundary.

**Evidence.** `app/main.py` registers eight routers, each delegating immediately to a service via `Depends()`. No pandas or SQLAlchemy imports exist in any router.

**Trade-off.** Adds indirection for simple CRUD operations. Accepted because testability and phase isolation outweigh the overhead: every service can be unit-tested without an HTTP server.

---

### Decision: Single shared `httpx.AsyncClient` per process

**Context.** Every LLM provider (Ollama, Groq) is called over HTTP. Creating a new client per request wastes TCP connections and skips connection pooling.

**Choice.** A single `httpx.AsyncClient` is created in the FastAPI `lifespan` context manager and injected into every planner via `set_client(client)`. On shutdown the client is gracefully closed.

**Evidence.** `app/main.py`:

```python
@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    client = httpx.AsyncClient(timeout=settings.ollama_timeout_seconds)
    for planner in (query_planner, forecast_planner, crud_planner, agent_planner):
        if hasattr(planner, "set_client"):
            planner.set_client(client)
    try:
        yield
    finally:
        await client.aclose()
```

**Trade-off.** The client timeout is set globally from `ollama_timeout_seconds`. Groq calls are faster and could benefit from a shorter timeout. Accepted as sufficient for a single-process deployment; a multi-client design would be appropriate for high-throughput production.

---

### Decision: `lru_cache(maxsize=1)` singletons in `dependencies.py`

**Context.** FastAPI's `Depends()` can re-construct service objects on every request if not cached. Services like `ConnectionService` hold SQLAlchemy engine pools; rebuilding them would leak connections.

**Choice.** Every service factory is decorated with `@lru_cache(maxsize=1)`. The first call constructs the object; all subsequent calls return the same instance.

**Trade-off.** Settings changes require a process restart. Acceptable for a twelve-factor app that reads configuration from environment variables.

---

## 2. Why LangGraph Was Used for the Agent Layer

### Context

Phase 9 required multi-step planning, conditional tool execution, human-in-the-loop CRUD approval, automatic failure recovery, and persistent session state across HTTP calls. Implementing this as a linear async function would produce a fragile state machine with no checkpointing.

### Choice: LangGraph `StateGraph` with `MemorySaver`

LangGraph provides:

| Requirement | LangGraph mechanism |
|---|---|
| Multi-step execution | `StateGraph` nodes execute sequentially or conditionally |
| Session state across calls | `MemorySaver` checkpointer keyed by `thread_id` |
| Human approval (suspend/resume) | `interrupt()` pauses the graph; `Command(resume=value)` continues it |
| Conditional routing | `add_conditional_edges()` with router functions |
| Failure recovery | Dedicated `recovery` node with replan capability |
| Explain-only mode | `verifier` routes to `aggregator` when `explain_only=True` |

### Graph topology

```
START → planner → verifier ──(explain)──────────────────────► aggregator → END
                      │                                             ▲
                      └──(execute)──► executor ──(done)────────────┤
                                          │                         │
                                          ├──(crud preview)──► approval_gate
                                          │                         │
                                          │            (approved)───┘
                                          │            (rejected)──► recovery
                                          │                              │
                                          └──(error)──► recovery ────────┘
                                                             │
                                                      (exhausted)──► aggregator
```

### Why not a hand-rolled state machine?

A custom state machine would need to implement checkpointing, interrupt/resume, and partial-state serialisation from scratch. LangGraph's `MemorySaver` handles all of this: the full `AgentState` TypedDict is serialised after every node, so a suspended session can be resumed in any subsequent HTTP request using only the `session_id` as a key.

### Key implementation detail: `operator.add` reducer

The `results` field in `AgentState` uses an append-only reducer:

```python
results: Annotated[list[dict], operator.add]
```

LangGraph merges node outputs by calling this reducer. Without it, each executor node would replace the results list rather than append to it, losing prior steps.

---

## 3. Why QueryPlan Was Chosen Over Raw LLM Code

### The problem with raw LLM code

The obvious approach is to ask the LLM to produce a pandas snippet and `exec()` it. This is rejected unconditionally because:

1. `eval()` / `exec()` are banned by project security requirements.
2. LLM-generated code is unpredictable: it can access the filesystem, import os, or produce infinite loops.
3. Testing becomes impossible: you cannot write deterministic tests for free-form code generation.

### The QueryPlan approach

The LLM is constrained to emit a small structured JSON object:

```python
class Operation(str, Enum):
    ROW_COUNT = "row_count"
    SUM = "sum"
    AVERAGE = "average"
    MAX = "max"
    MIN = "min"
    GROUPBY_SUM = "groupby_sum"
    GROUPBY_COUNT = "groupby_count"
    TOP_N = "top_n"
    XY_SELECT = "xy_select"

class QueryPlan(BaseModel):
    model_config = {"extra": "forbid"}
    operation: Operation
    column: Optional[str] = None
    group_by: Optional[str] = None
    n: Optional[int] = Field(default=None, ge=1)
    x_column: Optional[str] = None
    y_column: Optional[str] = None
```

`extra = "forbid"` ensures the LLM cannot inject unexpected fields. Pydantic validates the operation enum and numeric constraints. Column names from the plan are used only as dictionary keys to look up real `DataFrame` columns — they are never string-formatted into code.

### Execution flow

```
question → LLM → raw JSON string
         → Pydantic parse (QueryPlan)
         → semantic validation against real DataFrame schema
         → deterministic pandas dispatch table
         → answer string
```

Every operation in the dispatch table is a hand-written function. The LLM's only contribution is selecting which function to call and which columns to pass.

---

## 4. How SQL Injection Is Prevented

The system touches SQL in four distinct places. Each uses a different prevention mechanism.

### 4a. NL-to-SQL analytics (`SqlExecutor`)

The LLM produces a `QueryPlan` (see §3). The `SQLTranslator` converts this into a `sqlalchemy.sql.Select` using reflected `Column` objects:

```python
# Column name from plan used only as a dict key — never string-formatted
col = table.c[plan.column]
return select(func.sum(col))
```

`table.c[name]` raises `KeyError` if the column does not exist in the reflected schema. No SQL string is ever assembled. The only bound literal is `n` (an integer validated `ge=1`).

### 4b. CRUD validator (`CrudValidator`)

All WHERE clauses are built via `_apply_filter`, which resolves column names against the reflected `Table` object and composes SQLAlchemy Core expressions:

```python
col = table.c[f.column]   # KeyError if column absent
if op is FilterOperator.EQ:
    return col == f.value  # bound parameter, never formatted
```

The `_WRITE_DENYLIST` blocks writes to columns named `password`, `token`, `api_key`, etc., regardless of what the LLM proposes.

### 4c. CRUD executor (`CrudExecutor`)

All DML (INSERT/UPDATE/DELETE) uses `sqlalchemy.Table` with bound parameters inside `engine.begin()` transactions:

```python
with engine.begin() as conn:
    pre_image = self._capture_pre_image(conn, table, plan)
    affected_rows, inserted_pk = self._run_dml(conn, table, plan, pk_cols)
```

No raw SQL strings are assembled anywhere in the executor.

### 4d. Direct database queries (`ConnectionService`)

The only use of `text()` is a connectivity probe (`SELECT 1`). Schema discovery uses SQLAlchemy's `inspect()` API exclusively.

### Summary

| Layer | Mechanism |
|---|---|
| NL analytics | LLM → QueryPlan enum → reflected Column objects |
| CRUD planning | LLM → CrudPlan Pydantic model → reflected Column objects |
| CRUD execution | SQLAlchemy Core DML with bound parameters |
| Schema discovery | SQLAlchemy `inspect()` API |

Raw SQL from the LLM is **never executed**. This is a hard architectural constraint, not a runtime check.

---

## 5. How CRUD Approval Works End-to-End

Destructive operations (DELETE, BULK_UPDATE, SOFT_DELETE) require explicit human confirmation. The mechanism spans three phases:

### Phase 1: Planner produces a preview + execute pair

The LLM is instructed to always emit `crud_preview` immediately before `crud_execute` for any mutation. The verifier enforces this:

```python
# Guard 5 in verifier node
for i, step in enumerate(plan):
    if step.get("tool_name") == "crud_execute":
        if i == 0 or plan[i - 1].get("tool_name") != "crud_preview":
            errors.append("crud_execute must be immediately preceded by crud_preview.")
```

### Phase 2: Preview generates a signed confirmation token

`CrudValidator.preview()` counts affected rows, builds a before-image, and issues an HMAC-SHA256 token:

```python
payload = json.dumps({
    "connection_id": ...,
    "operation": plan.operation.value,
    "table_name": plan.table_name,
    "filter_hash": ...,
    "set_hash": ...,
    "affected_rows": count,
    "iat": int(time.time()),
}, sort_keys=True)
sig = hmac.new(secret, payload.encode(), hashlib.sha256).hexdigest()
token = base64.urlsafe_b64encode(f"{payload}|{sig}".encode()).decode()
```

The token binds the exact operation, table, filter, and row count. If any of these change between preview and execute, verification fails.

### Phase 3: Approval gate suspends the LangGraph session

After `crud_preview` returns `requires_confirmation=True`, the executor routes to the `approval_gate` node, which calls `interrupt()`:

```python
def _approval_gate_node(state: AgentState) -> dict[str, Any]:
    approved: bool = interrupt({
        "type": "crud_approval",
        "session_id": state["session_id"],
        "preview": preview_output,
    })
    if approved:
        return {"error": None, "status": AgentStatus.RUNNING.value}
    return {"error": "User rejected the CRUD operation.", ...}
```

`interrupt()` saves the complete graph state to `MemorySaver` and returns `{"__interrupt__": [...]}` to the HTTP caller. The session is now suspended.

### Phase 4: User approves or rejects via HTTP

The caller receives `status: "suspended"` and a `pending_approval` object containing the preview details. The frontend displays this to the user.

`POST /api/v1/agent/resume/{session_id}` with `{"approved": true/false}` calls:

```python
result = await self._graph.ainvoke(Command(resume=request.approved), config=config)
```

LangGraph restores the full session state and resumes from the `approval_gate` node with the user's boolean.

### Phase 5: Auto-injection of confirmation token

The executor node auto-injects the `confirmation_token` from the `crud_preview` result into the `crud_execute` arguments:

```python
if tool_name == "crud_execute":
    token = _find_confirmation_token(state["results"])
    if token:
        arguments["confirmation_token"] = token
```

The executor never uses the LLM-provided token — it always pulls the token from the validated preview result.

### Phase 6: Execution inside a transaction with rollback snapshot

`CrudExecutor.execute()` captures a pre-image of affected rows inside the same `engine.begin()` transaction before applying DML. If rollback is supported, the pre-image is written to a JSON snapshot file. The `rollback_token` returned to the caller can be used to reverse the operation within `crud_rollback_ttl_seconds`.

---

## 6. Why Forecasting Is Deterministic

### The problem

LLM-generated forecasts are non-deterministic: the same question can produce different answers on repeated calls, making the system unsuitable for business reporting.

### The choice: statistical model chain with no LLM in the execution path

Forecasting uses a pure-Python numerical pipeline. The LLM is involved only in parsing the question to extract the target column and horizon — it never produces forecast values.

```
question → ForecastPlanner (LLM) → ForecastRequest (Pydantic)
         → ForecastService → forecast_series() → ForecastOutput
```

`forecast_series()` in `forecast_models.py` tries models in a fixed preference order:

| Priority | Model | Condition |
|---|---|---|
| 1 | Holt-Winters seasonal (statsmodels) | `n ≥ 2 × seasonal_periods` |
| 2 | Holt-Winters (statsmodels) | `n ≥ 4` |
| 3 | Linear OLS (NumPy) | `n ≥ 3` |
| 4 | Naive (last value) | always |

Each model either succeeds deterministically or raises, at which point the next model is tried. The `method_used` field in the response tells the caller exactly which model ran.

Confidence intervals are computed as `±1.96σ` where `σ` is the standard deviation of residuals — a fixed formula with no randomness.

### Why numpy/statsmodels rather than an LLM?

- Results are reproducible: the same data always produces the same forecast.
- Confidence intervals are mathematically grounded.
- No token costs, no latency variability.
- Anomaly detection (`detect_anomalies`) uses rolling z-scores, also deterministic.

---

## 7. How SQL Pushdown Works

### The problem

Loading a 10-million-row table into a pandas `DataFrame` to compute `SUM(revenue)` wastes memory and takes seconds. The database can answer the same query in milliseconds.

### The design: `QueryPlan → SQLTranslator → SqlExecutor`

When a dataset is backed by a live database connection (not an uploaded file), the `AnalyticsService` checks whether the operation can be pushed down:

```python
# In AnalyticsService.analyze()
if (
    metadata.source == DatasetSource.DATABASE
    and self._sql_executor
    and self._sql_executor.supports(plan.operation)
):
    result = await run_in_threadpool(self._sql_executor.execute, metadata, plan)
```

`SQLTranslator` converts the `QueryPlan` into a `sqlalchemy.sql.Select` using reflected `Column` objects:

```python
# SUM pushdown
return select(func.sum(self._col(columns, plan.column)))

# GROUPBY_SUM pushdown
group = self._col(columns, plan.group_by)
aggregate = func.sum(self._col(columns, plan.column))
return select(group, aggregate).group_by(group).order_by(aggregate.desc())
```

The supported operations for pushdown are:

```
ROW_COUNT, SUM, AVERAGE, MAX, MIN
GROUPBY_SUM, GROUPBY_COUNT, TOP_N
```

`XY_SELECT` and `COLUMN_COUNT` are not pushed down (they require local DataFrame operations).

### Fallback

If the database is unavailable or the operation is unsupported, `SqlExecutor.execute()` raises `DatabaseError`, and `AnalyticsService` falls back to loading a capped pandas frame and computing locally. The caller receives the same `QueryResponse` shape regardless of which path ran.

### Parity guarantee

`tests/test_sql_pushdown_parity.py` asserts that for every supported operation, the SQL path and the pandas path produce identical answers against the same data. This prevents silent correctness regressions.

---

## 8. How Database Credentials Are Secured

### At-rest encryption

Passwords are encrypted with Fernet (AES-128-CBC + HMAC-SHA256) before being written to disk. The key is loaded from `DB_ENCRYPTION_KEY` (a base64-encoded 32-byte secret in `.env`):

```python
# app/core/crypto.py
class CredentialCipher:
    def __init__(self, key: Optional[str]) -> None:
        if key:
            self._fernet = Fernet(key.encode("utf-8"))

    def encrypt(self, plaintext: str) -> str:
        return self._fernet.encrypt(plaintext.encode()).decode()

    def decrypt(self, token: str) -> str:
        return self._fernet.decrypt(token.encode()).decode()
```

If `DB_ENCRYPTION_KEY` is absent, `CredentialCipher.available` returns `False` and the service refuses to persist any connection that has a password. SQLite (passwordless) connections are always allowed.

### In-memory only

Decrypted passwords are used only to build a SQLAlchemy connection URL and are never returned in any API response. The `_StoredConnection` model stores `password_encrypted`; the API response model (`ConnectionMetadata`) has no password field.

### Credential denylist

Even if the LLM or a user attempts to write to a `password` or `token` column through the CRUD layer, `_WRITE_DENYLIST` in `crud_validator.py` blocks it before any SQL is generated.

### HMAC confirmation tokens

Confirmation tokens for destructive CRUD operations are HMAC-SHA256 signed with a separate secret (`crud_secret_key`). If `crud_secret_key` is absent, a per-process `os.urandom(32)` secret is used (tokens do not survive restarts). The token payload encodes the exact operation, table, filter hash, and affected-row count, so tokens cannot be reused for a different operation.

---

## 9. Why Services Are Separated

Each service owns exactly one domain. The reasons are practical, not theoretical.

| Service | Domain | Why isolated |
|---|---|---|
| `DatasetService` | File storage, DataFrame cache, metadata | File I/O and cache management should not leak into analytics |
| `AnalyticsService` | NL → QueryPlan → pandas/SQL | Depends on DatasetService and two executor strategies; testing each strategy requires isolation |
| `VisualizationService` | QueryPlan → Vega-Lite spec | Chart logic is independent of how the data was fetched |
| `ForecastService` | Time-series forecasting | Statistical models have no dependency on LLM providers |
| `ReportService` | PDF generation | ReportLab dependencies are unrelated to analytics |
| `ConnectionService` | Database pool management | Engine lifecycle (pool, timeout, schema reflection) is a distinct concern |
| `CrudService` | Planner → validator → executor pipeline | Three internal stages each need independent testing |
| `AgentOrchestrator` | LangGraph graph facade | Orchestration logic must not contain business logic from any other service |

**Key invariant:** `AgentOrchestrator` calls other services only through the `ToolRegistry` adapter layer. It has no direct imports from any service. This means the entire agent layer can be tested with `FakeTool` and `FakePlanner` doubles without starting any real service.

---

## 10. Common Interviewer Questions with Model Answers

---

**Q: How do you prevent prompt injection in the agent layer?**

The agent never executes arbitrary text produced by the LLM. Every LLM output is parsed into a typed structure (`QueryPlan`, `CrudPlan`, `list[PlannedToolCall]`) via Pydantic before anything is acted on. The `verifier` node rejects plans that reference unknown tools, exceed complexity limits, or sequence `crud_execute` without a preceding `crud_preview`. Tool arguments are passed to service methods that use bound SQL parameters — they are never string-interpolated into queries.

---

**Q: What happens if the LLM is unavailable?**

Every planner follows the `FallbackPlanner` pattern. When `llm_provider=groq`, requests go to Groq first. If Groq raises `LLMError`, the fallback calls Ollama. If Ollama is also unreachable, the `LLMError` propagates to the HTTP caller with a 503 response. The fallback is wired at startup in `dependencies.py` and is transparent to the calling service.

---

**Q: How is the CRUD rollback mechanism implemented?**

Before executing any DML, `CrudExecutor` runs a `SELECT` inside the same transaction to capture the pre-image of affected rows. This snapshot is written to a JSON file keyed by a `rollback_token`. If the caller later requests a rollback within `crud_rollback_ttl_seconds`, the executor reads the snapshot and issues compensating DML (re-INSERT for DELETEs, re-UPDATE for UPDATEs). Rollback is unavailable when the pre-image exceeds `crud_max_rollback_rows` to prevent memory exhaustion.

---

**Q: How does the agent handle partial failures — e.g., step 2 of 4 fails?**

The executor records the failure in `results` with an `error` field and routes to the `recovery` node. Recovery calls `planner.replan()`, passing the completed results, the failed step, the error message, and the remaining planned steps. The planner returns a revised plan for only the outstanding work. `retry_count` is incremented; if it reaches `max_retries`, the recovery node writes a partial answer to `final_answer` and routes to the aggregator with `status=FAILED`. The caller always receives a response — never a hung session.

---

**Q: Why is `MemorySaver` used instead of a database-backed checkpointer?**

`MemorySaver` stores session state in process memory. It is appropriate for a single-process deployment where sessions do not need to survive restarts. A production deployment with horizontal scaling would replace `MemorySaver` with LangGraph's `PostgresSaver` or `RedisSaver` — no application code needs to change because the checkpointer is injected at graph compile time.

---

**Q: How does the SQL pushdown interact with the row-cap on uploads?**

Uploaded CSV/Excel datasets are loaded into pandas `DataFrames` with a configurable row cap (`db_max_rows`). There is no pushdown for uploaded files because they have no database connection. Pushdown applies exclusively to datasets of type `DatasetSource.DATABASE`. `AnalyticsService.analyze()` checks `metadata.source` before attempting `SqlExecutor.execute()`. The pandas path always serves as the fallback.

---

**Q: How are settings validated and where are they sourced?**

`pydantic-settings` reads from environment variables and an optional `.env` file (case-insensitive). Every setting has a typed field with a default. There are no hardcoded values in service code. The `Settings` object is cached via `lru_cache(maxsize=1)` so `.env` is read only once per process. Type validation at startup means invalid configuration raises an error before any request is handled.

---

**Q: How is thread safety handled for the SQLAlchemy connection pool?**

`ConnectionService` holds a `dict[str, Engine]` protected by a `threading.Lock`. `CrudExecutor` has a separate `threading.Lock` for its table reflection cache. SQLAlchemy's connection pool itself is thread-safe. FastAPI runs synchronous service methods in a threadpool via `run_in_threadpool`, so the locks prevent race conditions on the shared dicts without blocking the event loop.

---

**Q: Why does the `AgentState` use `TypedDict` instead of a Pydantic model?**

LangGraph's `MemorySaver` checkpoints state by serialising it. Using `TypedDict` avoids coupling the graph internals to Pydantic's serialisation lifecycle and makes the state trivially JSON-serialisable. Pydantic models are used only at the HTTP boundary (`AgentRunRequest`, `AgentRunResponse`). Inside the graph all Pydantic objects are converted to plain dicts before being stored in state.

---

**Q: Walk me through what happens when a user sends "Delete all orders from 2020".**

1. `POST /api/v1/agent/run` receives the request.
2. The **planner** calls the LLM with the goal and tool schemas. The LLM returns a plan: `[{crud_preview, ...}, {crud_execute, ...}]`.
3. The **verifier** confirms: ≤10 steps, valid tool names, `crud_execute` follows `crud_preview`, mutation intent detected in goal.
4. The **executor** runs `CrudPreviewTool`. The validator reflects the `orders` table, counts rows matching the 2020 filter, issues an HMAC token, and returns `requires_confirmation=True`.
5. The **executor** routes to `approval_gate`. LangGraph calls `interrupt()`, which snapshots state and returns `status: suspended` to the HTTP caller.
6. The frontend shows the user: "This will delete 847 rows from orders. Approve?"
7. The user clicks Approve. `POST /api/v1/agent/resume/{session_id}` sends `{approved: true}`.
8. LangGraph restores state and resumes `approval_gate`, which returns `status: running`.
9. The **executor** runs `CrudExecuteTool`. It auto-injects the `confirmation_token` from the preview result. The validator verifies the token signature and row count. The executor captures a pre-image, runs `DELETE` inside a transaction, writes a rollback snapshot, and returns `affected_rows: 847`.
10. The **aggregator** builds a final answer. `POST /agent/run` (step 7) returns `status: done, final_answer: "Deleted 847 rows from orders."`.

---

**Q: How many tests cover this system and how are they organised?**

188 tests across 17 test files. Each test file corresponds to one service or component:

| Category | Tests |
|---|---|
| Analytics service | 28 |
| CRUD (service, executor, validator) | ~95 |
| Forecasting (models, service) | 26 |
| SQL (translator, pushdown parity) | ~15 |
| Connections | 11 |
| Visualization | 12 |
| Reports | ~8 |
| Provider selection | ~10 |
| Agent (tools, planner, graph) | 50 |

Integration tests for the agent graph use `FakePlanner` and `FakeTool` doubles so no LLM or real database is required. The `test_sql_pushdown_parity.py` suite runs both the SQL and pandas paths against the same in-memory SQLite database and asserts identical results.
