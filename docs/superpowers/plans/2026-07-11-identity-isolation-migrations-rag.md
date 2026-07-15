# Identity Isolation, Migrations, and RAG Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind member chat identity to Mall Portal JWT, add versioned PostgreSQL migrations, provide safe service/RAG smoke tests, and add an isolated admin Agent workspace to `mall-admin-web`.

**Architecture:** The member route resolves identity through Portal `/sso/info` before touching session or memory state. Alembic exclusively owns database schema changes. Admin UI and member chat use separate API modules and authentication domains; service smoke tests default to read-only checks.

**Tech Stack:** FastAPI, httpx, SQLAlchemy async, Alembic, PostgreSQL, Redis, Milvus, pytest, Vue 3, Pinia, Axios, TypeScript, Vite.

---

### Task 1: Portal JWT member identity

**Files:**
- Modify: `after_sales_agent/app/adapters/ecommerce_gateway.py`
- Modify: `after_sales_agent/app/adapters/mall_gateway.py`
- Modify: `after_sales_agent/app/api/dependencies.py`
- Modify: `after_sales_agent/app/api/routes.py`
- Modify: `after_sales_agent/app/api/schemas.py`
- Modify: `after_sales_agent/tests/unit/test_mall_gateway.py`
- Modify: `after_sales_agent/tests/integration/test_chat_api.py`

- [ ] Write a failing gateway test where `/sso/info` returns `{"id": 100, "username": "member"}` and assert `await gateway.get_current_member()` returns stable ID `"100"`.
- [ ] Run `python -m pytest tests/unit/test_mall_gateway.py -q`; expect failure because `get_current_member` does not exist.
- [ ] Add `CurrentMember` and async `get_current_member()` to the gateway contract/implementation, reusing `_get_common_result` and current Bearer header.
- [ ] Write a failing API test that omits `user_id`, injects a gateway resolving member `100`, and asserts session/memory use `100`; add a payload containing `user_id=999` and assert validation rejects the extra field.
- [ ] Remove `user_id` from `ChatRequest`, configure it with `extra="forbid"`, resolve member before session access, and map authentication/domain failures to HTTP 401/403.
- [ ] Run `python -m pytest tests/unit/test_mall_gateway.py tests/integration/test_chat_api.py -q`; expect all pass.

### Task 2: Alembic schema ownership

**Files:**
- Create: `after_sales_agent/alembic.ini`
- Create: `after_sales_agent/migrations/env.py`
- Create: `after_sales_agent/migrations/script.py.mako`
- Create: `after_sales_agent/migrations/versions/20260711_01_create_user_memories.py`
- Create: `after_sales_agent/app/services/user_memory_schema.py`
- Modify: `after_sales_agent/app/services/user_memory.py`
- Modify: `after_sales_agent/pyproject.toml`
- Create: `after_sales_agent/tests/unit/test_migrations.py`

- [ ] Add a failing test asserting repository initialization no longer calls `metadata.create_all`, and the migration revision contains create/drop operations for `user_memories`.
- [ ] Run `python -m pytest tests/unit/test_migrations.py -q`; expect missing migration modules/files.
- [ ] Move table metadata to `user_memory_schema.py`, add `alembic>=1.14`, configure migrations from `DATABASE_URL` normalized to a synchronous Alembic-compatible URL, and create the initial revision.
- [ ] Remove runtime schema creation; make repository database operations surface a message containing `alembic upgrade head` when the table is absent.
- [ ] Run `python -m pytest tests/unit/test_migrations.py tests/unit/test_memory_stores.py -q`; expect all pass.

### Task 3: Read-only service and RAG smoke testing

**Files:**
- Create: `after_sales_agent/app/diagnostics/service_smoke.py`
- Create: `after_sales_agent/app/diagnostics/__init__.py`
- Create: `after_sales_agent/scripts/smoke_test_services.py`
- Create: `after_sales_agent/tests/unit/test_service_smoke.py`

- [ ] Add failing tests with fake PostgreSQL, Redis, Milvus, retriever, and Mall clients; assert a structured result per component and no secret values in serialized output.
- [ ] Run `python -m pytest tests/unit/test_service_smoke.py -q`; expect module import failure.
- [ ] Implement checks for PostgreSQL `SELECT 1` plus Alembic revision, Redis ping, Milvus collection/description, one RAG query, and optional Portal `/sso/info`.
- [ ] Add a CLI whose default is read-only and requires explicit `--mall-token`; do not perform RAG ingestion from the smoke command.
- [ ] Run `python -m pytest tests/unit/test_service_smoke.py -q`; expect all pass.

### Task 4: Member demo integration contract

**Files:**
- Modify: `after_sales_agent/app/web/app.js`
- Modify: `after_sales_agent/app/web/index.html`
- Create: `after_sales_agent/docs/mall-portal-agent-integration.md`
- Modify: `after_sales_agent/tests/integration/test_chat_api.py`

- [ ] Add an API regression test proving member requests require Authorization and cannot submit `user_id`.
- [ ] Change the demo to accept a JWT via an explicit login integration hook/session-only input, send Authorization, and remove fixed `U100`.
- [ ] Document the exact Portal store/Axios helper contract, including cross-origin restrictions and token redaction.
- [ ] Run Agent tests and verify the static page contains no fixed user ID.

### Task 5: Isolated admin Agent workspace

**Files:**
- Create: `mall-admin-web/src/apis/agent.ts`
- Create: `mall-admin-web/src/types/agent.d.ts`
- Create: `mall-admin-web/src/views/agent/index.vue`
- Modify: `mall-admin-web/src/router/index.ts`
- Modify: `mall-admin-web/vite.config.ts`

- [ ] Add TypeScript API types and a read-only admin client using the existing Axios instance, targeting `/agent-admin/sessions` and `/agent-admin/handoffs` only.
- [ ] Add a lazy-loaded `/agent` route and a page that lists session/handoff summaries, clearly labels backend-unavailable responses, and never calls `/api/chat`.
- [ ] Add Vite development proxy configuration for `/agent-admin` using `VITE_AGENT_API_BASE_URL`.
- [ ] Run `npm run type-check` and `npm run build`; expect both pass.

### Task 6: External smoke execution and completion report

**Files:**
- Modify: `after_sales_agent/docs/system-completion-assessment-2026-07-11.md`
- Modify: `after_sales_agent/README.md`

- [ ] Run `python -m pytest -q`, `python -m ruff check app tests scripts`, and `python -m compileall -q app`.
- [ ] Run the read-only smoke CLI against the current `.env`; record reachable/unreachable components without printing credentials.
- [ ] Run `alembic current` read-only; do not run `upgrade head` until the target is confirmed non-production or the user explicitly authorizes schema writes.
- [ ] Update the completion report with exact verification evidence and remaining blockers.
