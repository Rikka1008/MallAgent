# Async Storage, Config, and JWT Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the unused/synchronous PostgreSQL path with an async SQLAlchemy repository, split configuration into a dedicated package, repair RAG environment configuration, and propagate each Mall user's Bearer token through the Agent request.

**Architecture:** A top-level `config` package owns environment parsing. SQLAlchemy AsyncEngine owns the PostgreSQL pool and the memory repository exposes awaitable operations. FastAPI reads a request-scoped Bearer token and constructs a request-scoped asynchronous Mall gateway so concurrent users never share credentials.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2 async, asyncpg, httpx AsyncClient, pytest, pytest-asyncio.

---

## File structure

- Create `app/config/{__init__,app,llm,rag,storage,mall}.py`: focused environment configuration modules.
- Create `app/core/database/url.py`: pure database URL normalization.
- Modify `app/services/user_memory.py`: asynchronous repository protocol and SQLAlchemy implementation.
- Modify `app/adapters/ecommerce_gateway.py`: asynchronous gateway protocol.
- Modify `app/adapters/mall_gateway.py`: request-scoped JWT and AsyncClient calls.
- Modify `app/tools/*.py`, `app/agent/{nodes,graph}.py`, `app/api/{dependencies,routes}.py`: propagate async operations and token.
- Modify `app/main.py`: lifespan resource cleanup.
- Delete `app/core/config.py` and `app/core/database/postgre_pool.py` after all imports migrate.
- Modify tests and `.env.example` to document and verify the new contracts.

### Task 1: Configuration package and RAG contract

**Files:**
- Create: `after_sales_agent/app/config/__init__.py`
- Create: `after_sales_agent/app/config/app.py`
- Create: `after_sales_agent/app/config/llm.py`
- Create: `after_sales_agent/app/config/rag.py`
- Create: `after_sales_agent/app/config/storage.py`
- Create: `after_sales_agent/app/config/mall.py`
- Modify: `after_sales_agent/tests/unit/test_config.py`
- Modify: all production imports currently referencing `core.config`

- [ ] **Step 1: Write the failing public-contract test**

Change the test import to `import config`, reload its submodules, and assert `RagConfig.RETRIEVER`, `SEARCH_LIMIT`, `ENABLE_RERANK`, all embedding/Milvus values, and storage values come from the named environment variables. Assert `config` exports the expected classes.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/unit/test_config.py -q`

Expected: FAIL because package `config` does not exist.

- [ ] **Step 3: Add the focused modules and public exports**

Implement simple class attributes using `os.getenv`, preserving existing environment names. Define `RagConfig` (not `RetrievalConfig`) with:

```python
class RagConfig:
    RETRIEVER = os.getenv("RAG_RETRIEVER", "keyword")
    SEARCH_LIMIT = int(os.getenv("RAG_SEARCH_LIMIT", "5"))
    ENABLE_RERANK = os.getenv("RAG_ENABLE_RERANK", "false").lower() == "true"
```

Move all existing classes without changing defaults and export them from `config/__init__.py`.

- [ ] **Step 4: Migrate imports and verify GREEN**

Run: `python -m pytest tests/unit/test_config.py tests/unit/test_policy_retriever.py -q`

Expected: PASS.

### Task 2: Database URL normalization and async memory repository

**Files:**
- Create: `after_sales_agent/app/core/database/url.py`
- Modify: `after_sales_agent/app/services/user_memory.py`
- Modify: `after_sales_agent/app/api/dependencies.py`
- Modify: `after_sales_agent/tests/unit/test_memory_stores.py`
- Modify: `after_sales_agent/pyproject.toml`

- [ ] **Step 1: Write failing URL and async repository tests**

Add parametrized assertions that `postgresql://` and `postgresql+psycopg://` become `postgresql+asyncpg://`, while asyncpg URLs remain unchanged. Convert in-memory repository test to `async def` and await `upsert/get`. Add a fake async connection/engine test proving repository operations are awaitable without a real PostgreSQL service.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/unit/test_memory_stores.py -q`

Expected: FAIL because the normalization function is missing and repository methods are not awaitable.

- [ ] **Step 3: Implement minimal async storage**

Add `normalize_async_database_url(url: str) -> str`. Change protocol and in-memory methods to async. Build `SqlAlchemyUserMemoryRepository` with `create_async_engine`, `engine.begin()`, `await connection.run_sync(metadata.create_all)`, async selects, async PostgreSQL upserts, and `await engine.dispose()`.

Add `aiosqlite>=0.20.0` to dev dependencies for isolated repository tests if SQLite is used.

- [ ] **Step 4: Remove silent production fallback and verify GREEN**

Make configured database construction errors propagate. Keep in-memory storage only when `DATABASE_URL` is absent.

Run: `python -m pytest tests/unit/test_memory_stores.py tests/unit/test_gateway_dependencies.py -q`

Expected: PASS.

### Task 3: Request-scoped Bearer token dependency

**Files:**
- Modify: `after_sales_agent/app/api/dependencies.py`
- Modify: `after_sales_agent/app/api/routes.py`
- Modify: `after_sales_agent/tests/integration/test_chat_api.py`
- Modify: `after_sales_agent/tests/unit/test_gateway_dependencies.py`

- [ ] **Step 1: Write failing authentication propagation tests**

Add an async fake gateway dependency factory that records `Authorization`. Test `/api/chat` passes `Bearer user-token` into the gateway. Test malformed non-Bearer authorization returns 401. Keep no-header calls valid for dependency-overridden offline tests.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/integration/test_chat_api.py tests/unit/test_gateway_dependencies.py -q`

Expected: FAIL because the route ignores Authorization.

- [ ] **Step 3: Implement request-scoped dependency**

Add a parser returning the raw Bearer header or local fallback. Construct `MallEcommerceGateway(auth_header=authorization)` per request; do not cache gateways containing credentials. Change chat to `async def`, await repository operations and the agent turn.

- [ ] **Step 4: Verify GREEN**

Run: `python -m pytest tests/integration/test_chat_api.py tests/unit/test_gateway_dependencies.py -q`

Expected: PASS.

### Task 4: Asynchronous Mall gateway and Agent tool chain

**Files:**
- Modify: `after_sales_agent/app/adapters/ecommerce_gateway.py`
- Modify: `after_sales_agent/app/adapters/mall_gateway.py`
- Modify: `after_sales_agent/app/tools/order_tools.py`
- Modify: `after_sales_agent/app/tools/logistics_tools.py`
- Modify: `after_sales_agent/app/tools/refund_tools.py`
- Modify: `after_sales_agent/app/tools/after_sales_tools.py`
- Modify: `after_sales_agent/app/agent/nodes.py`
- Modify: `after_sales_agent/app/agent/graph.py`
- Modify: `after_sales_agent/tests/fakes.py`
- Modify: relevant unit/integration/eval tests

- [ ] **Step 1: Convert Mall gateway tests to desired async API**

Mark tests async, make fake client methods async, await gateway methods, and assert every request receives exactly `headers={"Authorization": "Bearer user-token"}`. Add 401 and 403 fake responses and assert typed authentication/permission errors.

- [ ] **Step 2: Verify RED**

Run: `python -m pytest tests/unit/test_mall_gateway.py -q`

Expected: FAIL because gateway calls are synchronous and token is stored as a shared default header.

- [ ] **Step 3: Implement async protocol and gateway**

Convert gateway protocol methods, Mall fetch helpers, tools, `tool_node`, and `run_agent_turn` to async. Use `httpx.AsyncClient`; attach the request-scoped authorization header on each `get`. Preserve all domain mapping and read-only behavior.

- [ ] **Step 4: Convert fakes and callers, then verify GREEN**

Run: `python -m pytest tests/unit/test_mall_gateway.py tests/unit/test_tools.py tests/integration tests/eval -q`

Expected: PASS.

### Task 5: Resource lifecycle, cleanup, and documentation

**Files:**
- Modify: `after_sales_agent/app/main.py`
- Modify: `after_sales_agent/.env.example`
- Modify: `after_sales_agent/README.md`
- Delete: `after_sales_agent/app/core/config.py`
- Delete: `after_sales_agent/app/core/database/postgre_pool.py`

- [ ] **Step 1: Add lifecycle/cleanup test where externally observable**

Test repository `close()` awaits engine disposal and Mall gateway `close()` closes only an internally owned AsyncClient.

- [ ] **Step 2: Verify RED, implement cleanup, verify GREEN**

Use FastAPI lifespan to close cached application resources. Document `DATABASE_URL=postgresql+asyncpg://...`, Mall login response extraction, and browser request header. Mark `MALL_AUTH_TOKEN` as local-only fallback. Remove obsolete files after `rg "core.config|PostgrePool"` returns no consumers.

Run: `python -m pytest -q`

Expected: all tests PASS.

Run: `python -m ruff check app tests`

Expected: exit code 0.

### Task 6: Completion assessment

**Files:**
- Create: `after_sales_agent/docs/system-completion-assessment-2026-07-11.md`

- [ ] **Step 1: Inspect implemented features against code and tests**

Rate API/Agent orchestration, Mall integration, authentication, memory, RAG ingestion/retrieval, write operations, observability, deployment, and evaluation separately. Distinguish implemented, tested, externally unverified, and missing states.

- [ ] **Step 2: Document the real JWT acquisition flow**

Include the concrete sequence: Mall `/sso/login` -> read `data.token` -> store in frontend memory/session storage -> call Agent with Bearer header -> Agent forwards it -> optionally validate identity using `/sso/info`. Include security cautions against placing user JWTs in `.env` or logging them.

- [ ] **Step 3: Final verification**

Run full tests and lint again, record exact counts/results, and list external smoke tests that could not run without live Mall/PostgreSQL/Milvus credentials.
