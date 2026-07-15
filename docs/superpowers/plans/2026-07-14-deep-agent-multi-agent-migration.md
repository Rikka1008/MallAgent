# Deep Agent 多智能体协作迁移 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `after_sales_agent` 从手写规划器/注册表编排迁移为参考系统风格的 Deep Agent 主智能体 + 六个专业子智能体，并接入真实 LLM、Redis、Milvus 和 Mall 服务。

**Architecture:** `create_deep_agent` 负责理解用户请求、调用 `task()` 和生成最终回复；六个 `create_agent` 子智能体复用 DeepSeek 主模型，负责商品、订单、物流、退款、售后和政策业务工具。所有身份、网关、Case 和幂等依赖通过 `AgentRuntimeContext` 传入工具，不放入用户消息或 LLM 提示词。

**Tech Stack:** Python 3.13、FastAPI、LangChain、DeepAgents、LangGraph、LangGraph Redis Checkpointer、DeepSeek、Qwen/DashScope、Redis、Milvus、PostgreSQL、httpx、pytest、Ruff。

## Global Constraints

- 主智能体必须通过 `task()` 调用六个专业子智能体。
- 子智能体只调用职责范围内工具并整理业务上下文，不直接生成最终客服话术。
- `user_id` 只能来自 Mall 当前登录态；请求体中的 `user_id` 不得覆盖运行时身份。
- 生产模式缺少必要的 LLM、Redis、Milvus 或 Mall 配置时必须拒绝 ready，不得静默使用 Fake 或内存服务。
- 售后写操作必须保留订单归属、商品匹配、政策检查、幂等和审计校验。
- JWT 不得进入 LLM 提示词、Agent 输出、缓存 value、普通日志或错误响应。
- 单元测试使用 Fake Gateway/内存依赖；生产联调测试使用真实配置和真实服务。
- 每个任务先写失败测试，再实现最小改动，再运行该任务的专项测试。
- 当前工作区 `.git` 目录为空，执行阶段不能假设可以提交；每个任务仍保留建议提交点，若 Git 恢复后再提交。

---

## 文件与模块地图

| 模块 | 文件 | 责任 |
|---|---|---|
| 配置 | `app/config/llm.py`, `app/config/storage.py`, `app/config/rag.py`, `app/config/mall.py`, `app/config/app.py` | 生产 LLM、Redis、Milvus、Mall 配置与模式校验 |
| Agent 上下文 | `app/agent/context.py` | 定义 `AgentRuntimeContext`，承载身份和运行时依赖 |
| 主 Agent | `app/agent/main_agent.py` | 构造 `create_deep_agent` 和主系统提示词 |
| 子 Agent | `app/agent/subagents.py` | 构造六个 `create_agent` 子智能体 |
| 图入口 | `app/agent/graph.py` | 暴露主 Agent、checkpoint 和单轮测试入口 |
| 工具 | `app/tools/*.py` | 通过 `ToolRuntime[AgentRuntimeContext]` 访问真实业务依赖 |
| 生产依赖 | `app/core/database/*.py`, `app/services/memory/checkpoint.py`, `app/diagnostics/readiness.py` | Redis/Milvus 生命周期、健康检查和 readiness |
| API | `app/api/dependencies.py`, `app/api/routes.py`, `app/services/chat_service.py` | 构造 Agent、SSE、认证和最终状态落库 |
| 测试 | `tests/unit`, `tests/integration`, `tests/eval` | Agent 协作、安全边界、真实服务联调 |

## Task 1: 生产配置与依赖基线

**Files:**
- Modify: `D:/560/MallAgent/after_sales_agent/pyproject.toml`
- Modify: `D:/560/MallAgent/after_sales_agent/app/config/app.py`
- Modify: `D:/560/MallAgent/after_sales_agent/app/config/llm.py`
- Modify: `D:/560/MallAgent/after_sales_agent/app/config/storage.py`
- Modify: `D:/560/MallAgent/after_sales_agent/app/config/rag.py`
- Modify: `D:/560/MallAgent/after_sales_agent/app/config/mall.py`
- Create: `D:/560/MallAgent/after_sales_agent/.env.example`
- Test: `D:/560/MallAgent/after_sales_agent/tests/unit/test_config.py`

**Interfaces:**
- Produces `AppConfig.require_external_services() -> None`.
- Produces `LlmConfig.main_model_config() -> dict` and `LlmConfig.subagent_model_config() -> dict`.
- Produces `RedisConfig.require_url() -> str`, `MilvusConfig.require_uri() -> str`, and `MallConfig.require_portal_url() -> str`.

- [ ] **Step 1: Write failing configuration tests**

```python
def test_production_rejects_missing_external_services(monkeypatch):
    monkeypatch.setattr(AppConfig, "APP_ENV", "production")
    monkeypatch.setattr(AppConfig, "REQUIRE_EXTERNAL_SERVICES", True)
    monkeypatch.setattr(RedisConfig, "REDIS_URL", None)
    with pytest.raises(RuntimeError, match="REDIS_URL"):
        AppConfig.require_external_services()


def test_llm_config_exposes_separate_main_and_subagent_models():
    assert "model" in LlmConfig.main_model_config()
    assert "model" in LlmConfig.subagent_model_config()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/unit/test_config.py -q`

Expected: FAIL because production validation and separate model configuration are not implemented.

- [ ] **Step 3: Add production dependencies and configuration**

Add `deepagents`, `langchain`, and `langchain-deepseek` to `pyproject.toml`. Add configuration for:

```text
APP_ENV
REQUIRE_EXTERNAL_SERVICES
DEEPSEEK_API_KEY / DEEPSEEK_BASE_URL / DEEPSEEK_CHAT_MODEL
REDIS_URL / REDIS_MAX_CONNECTIONS / SESSION_TTL_SECONDS
MILVUS_URI / MILVUS_TOKEN / MILVUS_DB_NAME
MILVUS_PRODUCT_COLLECTION / MILVUS_POLICY_COLLECTION / MILVUS_MEMORY_COLLECTION
MALL_PORTAL_BASE_URL / MALL_ADMIN_BASE_URL / MALL_REQUEST_TIMEOUT_SECONDS
```

`require_external_services()` must raise a named `RuntimeError` for every missing production dependency and must never print secret values. `.env.example` contains names and safe placeholder text only.

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/unit/test_config.py -q`

Expected: all configuration tests pass.

- [ ] **Step 5: Check dependency importability**

Run: `python -c "import deepagents, langchain, langchain_deepseek; print('agent dependencies ok')"`

Expected: `agent dependencies ok`. If packages are missing, install the project editable package with the already-approved command `python -m pip install -e .`.

## Task 2: Runtime Context and Tool Boundary

**Files:**
- Create: `D:/560/MallAgent/after_sales_agent/app/agent/context.py`
- Modify: `D:/560/MallAgent/after_sales_agent/app/tools/order_tools.py`
- Modify: `D:/560/MallAgent/after_sales_agent/app/tools/logistics_tools.py`
- Modify: `D:/560/MallAgent/after_sales_agent/app/tools/refund_tools.py`
- Modify: `D:/560/MallAgent/after_sales_agent/app/tools/after_sales_tools.py`
- Modify: `D:/560/MallAgent/after_sales_agent/app/tools/policy_tools.py`
- Create: `D:/560/MallAgent/after_sales_agent/app/tools/product_tools.py`
- Test: `D:/560/MallAgent/after_sales_agent/tests/unit/test_agent_context.py`
- Test: `D:/560/MallAgent/after_sales_agent/tests/unit/test_tool_runtime.py`

**Interfaces:**
- `AgentRuntimeContext` is a dataclass with `user_id: str`, `session_id: str`, `gateway: EcommerceGateway`, `authorization: str | None`, `case_context: AfterSalesCase | None`, `long_term_memory: UserMemory | None`, and `idempotency_store: object | None`.
- Each Agent-facing business tool accepts public business arguments plus an injected `ToolRuntime[AgentRuntimeContext]`; runtime is not exposed in the generated tool schema.
- `search_products(query: str, runtime: ToolRuntime[AgentRuntimeContext]) -> dict` returns `found`, `message`, `items`, and `degradations`.

- [ ] **Step 1: Write failing identity-isolation tests**

```python
@pytest.mark.asyncio
async def test_order_tool_uses_runtime_user_id_not_message_user_id(fake_gateway):
    context = AgentRuntimeContext(
        user_id="U100", session_id="S1", gateway=fake_gateway,
    )
    result = await lookup_order.ainvoke(
        {"order_id": "ORD1001", "runtime": ToolRuntime(context=context)}
    )
    assert result["order"]["user_id"] == "U100"
    assert "U999" not in json.dumps(result, ensure_ascii=False)
```

- [ ] **Step 2: Run the focused test**

Run: `pytest tests/unit/test_tool_runtime.py -q`

Expected: FAIL because current tools receive gateway/user identity as ordinary injected arguments rather than the new runtime context.

- [ ] **Step 3: Implement the runtime context and tool adapters**

Move identity and gateway lookup into `runtime.context`. Keep tool-level checks unchanged: `gateway.get_order(order_id, user_id)`, product membership validation, policy validation, idempotency reservation and audit recording. Create `product_tools.py` using `HybridRetriever(collection_name=MilvusConfig.PRODUCT_COLLECTION)` and format each result as:

```python
{
    "name": item["title"],
    "sku": metadata.get("sku"),
    "brand": metadata.get("brand"),
    "price": metadata.get("price"),
    "category": metadata.get("category"),
    "selling_points": item["content"],
}
```

No product result may be synthesized when retrieval returns an empty list.

- [ ] **Step 4: Run the focused tests**

Run: `pytest tests/unit/test_agent_context.py tests/unit/test_tool_runtime.py tests/unit/test_readonly_tool_registration.py -q`

Expected: all pass, including the existing read-only tool registration checks.

## Task 3: Six Subagents

**Files:**
- Create: `D:/560/MallAgent/after_sales_agent/app/agent/subagents.py`
- Delete after replacement: `D:/560/MallAgent/after_sales_agent/app/agent/subagents/`
- Create: `D:/560/MallAgent/after_sales_agent/tests/unit/test_deep_subagents.py`

**Interfaces:**
- `create_product_subagent() -> dict`
- `create_order_subagent() -> dict`
- `create_logistics_subagent() -> dict`
- `create_refund_subagent() -> dict`
- `create_after_sales_subagent() -> dict`
- `create_policy_subagent() -> dict`
- Every returned dictionary has `name`, `description`, and `runnable`.

- [ ] **Step 1: Write failing registration tests**

```python
def test_six_subagents_have_disjoint_business_tools(monkeypatch):
    monkeypatch.setattr(LLMFactory, "llm_subagent", FakeChatModel())
    agents = build_subagents()
    assert [item["name"] for item in agents] == [
        "product_agent", "order_agent", "logistics_agent",
        "refund_agent", "after_sales_agent", "policy_agent",
    ]
    assert "search_products" in tool_names(agents[0])
    assert "lookup_order" in tool_names(agents[1])
    assert "search_policy" in tool_names(agents[5])
```

- [ ] **Step 2: Run the test to verify it fails**

Run: `pytest tests/unit/test_deep_subagents.py -q`

Expected: FAIL because `build_subagents()` and the six Deep Agent subagents do not exist.

- [ ] **Step 3: Implement the six subagents**

Use the reference system's `create_agent` pattern. The product prompt must say “先调用 `search_products`，只输出候选商品上下文”；the after-sales prompt must say that all write operations go through the safe tool and require complete validated slots; every prompt must forbid final customer-facing prose and invented data.

Tool assignment must be:

```text
product_agent      -> search_products
order_agent        -> lookup_orders, lookup_order
logistics_agent    -> lookup_logistics
refund_agent       -> lookup_refund
after_sales_agent  -> check_after_sales_policy, create_after_sales_request
policy_agent       -> search_policy
```

- [ ] **Step 4: Run registration and prompt tests**

Run: `pytest tests/unit/test_deep_subagents.py -q`

Expected: all six subagents register with the expected names, descriptions, tools and “context only” prompt rules.

## Task 4: Main Deep Agent and Graph Entry

**Files:**
- Create: `D:/560/MallAgent/after_sales_agent/app/agent/main_agent.py`
- Modify: `D:/560/MallAgent/after_sales_agent/app/agent/graph.py`
- Modify: `D:/560/MallAgent/after_sales_agent/app/config/llm.py`
- Create: `D:/560/MallAgent/after_sales_agent/tests/unit/test_main_agent.py`
- Create: `D:/560/MallAgent/after_sales_agent/tests/integration/test_deep_agent_graph.py`

**Interfaces:**
- `build_main_agent(checkpointer) -> CompiledStateGraph`.
- `MAIN_SYSTEM_PROMPT: str` includes product, order, logistics, refund, after-sales, identity and no-hallucination rules.
- `build_checkpointed_agent_graph(checkpointer)` returns the compiled main-agent graph used by the API.

- [ ] **Step 1: Write failing main-agent tests**

```python
def test_main_prompt_declares_all_six_task_targets():
    for name in (
        "product_agent", "order_agent", "logistics_agent",
        "refund_agent", "after_sales_agent", "policy_agent",
    ):
        assert f'task("{name}"' in MAIN_SYSTEM_PROMPT


def test_main_agent_is_built_with_runtime_context_and_subagents(fake_checkpointer):
    agent = build_main_agent(fake_checkpointer)
    assert agent is not None
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_main_agent.py tests/integration/test_deep_agent_graph.py -q`

Expected: FAIL because the new Deep Agent builder is not present.

- [ ] **Step 3: Implement `main_agent.py` and replace `graph.py`**

Use `create_deep_agent(model=LLMFactory.llm_main, system_prompt=MAIN_SYSTEM_PROMPT, tools=[], subagents=build_subagents(), checkpointer=checkpointer, context_schema=AgentRuntimeContext, name="ecommerce_after_sales_agent")`. The graph wrapper must pass the runtime context unchanged and must not recreate the old planner, registry or `AgentPlan` flow.

Implement `LLMFactory.llm_main` with `ChatDeepSeek` and `LLMFactory.llm_subagent` with the configured Qwen-compatible `ChatOpenAI`. Do not initialize a provider without its configured key in production.

- [ ] **Step 4: Run the graph tests**

Run: `pytest tests/unit/test_main_agent.py tests/integration/test_deep_agent_graph.py -q`

Expected: pass with fake models/checkpointer and no network calls.

## Task 5: Real Redis, Milvus, Mall Lifecycle and Readiness

**Files:**
- Modify: `D:/560/MallAgent/after_sales_agent/app/core/database/redis_client.py`
- Modify: `D:/560/MallAgent/after_sales_agent/app/core/database/milvus_client.py`
- Modify: `D:/560/MallAgent/after_sales_agent/app/services/memory/checkpoint.py`
- Create: `D:/560/MallAgent/after_sales_agent/app/diagnostics/readiness.py`
- Modify: `D:/560/MallAgent/after_sales_agent/app/api/dependencies.py`
- Modify: `D:/560/MallAgent/after_sales_agent/app/api/routes.py`
- Modify: `D:/560/MallAgent/after_sales_agent/tests/unit/test_readiness.py`
- Create: `D:/560/MallAgent/after_sales_agent/tests/integration/test_production_dependencies.py`

**Interfaces:**
- `async check_readiness() -> dict[str, dict]` returns redacted status for `llm`, `redis`, `milvus`, and `mall`.
- `async require_ready() -> None` raises `RuntimeError` when any production dependency is not ready.
- `GET /health/live` returns process liveness without external calls.
- `GET /health/ready` returns readiness and HTTP 503 when required dependencies fail.

- [ ] **Step 1: Write failing readiness tests**

```python
@pytest.mark.asyncio
async def test_production_readiness_reports_each_required_dependency(monkeypatch):
    monkeypatch.setattr(AppConfig, "APP_ENV", "production")
    result = await check_readiness()
    assert set(result) == {"llm", "redis", "milvus", "mall"}
    assert all("secret" not in json.dumps(value).lower() for value in result.values())
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `pytest tests/unit/test_readiness.py -q`

Expected: FAIL because readiness endpoints and dependency probes do not exist.

- [ ] **Step 3: Implement lifecycle and readiness**

Update Redis to use a configured async pool and `PING`; update Milvus to use configured URI/token/database/TLS and verify the configured collections; keep Redis checkpoint setup fail-closed in production; use `MallEcommerceGateway` to call `/sso/info` with the request JWT and map 401/403/404/429/5xx/timeout errors to existing domain errors. Add `/health/live` and `/health/ready`; keep `/health` as a compatibility alias returning the readiness summary.

- [ ] **Step 4: Run local readiness tests**

Run: `pytest tests/unit/test_readiness.py tests/unit/test_gateway_auth.py tests/unit/test_milvus_pool.py tests/unit/test_checkpoint.py -q`

Expected: pass without requiring external services because the probes are injected/mocked.

- [ ] **Step 5: Run real dependency smoke tests when environment variables exist**

Run: `python scripts/smoke_test_services.py`

Expected in configured production environment: PostgreSQL, Redis and Milvus checks report `ok`; Mall `/sso/info` reports `ok` with a test JWT. The script must redact all credentials and report `not_configured` only for local mode.

## Task 6: Streaming Chat Service and API Integration

**Files:**
- Create: `D:/560/MallAgent/after_sales_agent/app/services/chat_service.py`
- Modify: `D:/560/MallAgent/after_sales_agent/app/api/routes.py`
- Modify: `D:/560/MallAgent/after_sales_agent/app/api/dependencies.py`
- Modify: `D:/560/MallAgent/after_sales_agent/app/api/schemas.py`
- Create: `D:/560/MallAgent/after_sales_agent/tests/unit/test_chat_service.py`
- Modify: `D:/560/MallAgent/after_sales_agent/tests/integration/test_chat_api.py`

**Interfaces:**
- `ChatService.stream(message: str, thread_id: str, context: AgentRuntimeContext) -> AsyncIterator[str]` yields SSE-ready events.
- `_last_ai_content(messages: list) -> str` returns the last main-agent AI text.
- API route uses `get_main_agent()` and does not invoke `MainAgent`, `planner`, `classifier` or `registry`.

- [ ] **Step 1: Write failing streaming tests**

```python
@pytest.mark.asyncio
async def test_stream_emits_main_agent_tokens_but_not_subagent_tokens(fake_agent):
    ChatService.main_agent = fake_agent
    events = [item async for item in ChatService.stream("查订单", "S1", context)]
    body = "".join(events)
    assert "主智能体回复" in body
    assert "子智能体内部结果" not in body
```

- [ ] **Step 2: Run the focused test to verify it fails**

Run: `pytest tests/unit/test_chat_service.py -q`

Expected: FAIL because the new stream service is not implemented.

- [ ] **Step 3: Implement streaming and route integration**

Use `astream_events(..., version="v2")` or the installed DeepAgents stream object after verifying its runtime type. Filter events using run metadata/tags identifying the root main Agent; model-name matching is only a fallback. Collect the final state, emit `message_end`, save only the original user message and final main-agent response, and trigger semantic memory after the response has been delivered.

The route must construct `AgentRuntimeContext` from Mall authentication, Case service, memory and idempotency dependencies. Reject client-supplied `user_id` with 422 and map Mall auth failures to the existing SSE error schema.

- [ ] **Step 4: Run API tests**

Run: `pytest tests/unit/test_chat_service.py tests/integration/test_chat_api.py -q`

Expected: all streaming, auth, reset-session and identity-isolation tests pass with fake dependencies.

## Task 7: Remove Legacy Orchestration and Migrate Tests

**Files:**
- Delete: `D:/560/MallAgent/after_sales_agent/app/agent/orchestrator.py`
- Delete: `D:/560/MallAgent/after_sales_agent/app/agent/llm_intent.py`
- Delete: `D:/560/MallAgent/after_sales_agent/app/agent/registry.py`
- Delete: `D:/560/MallAgent/after_sales_agent/app/agent/nodes.py`
- Delete: `D:/560/MallAgent/after_sales_agent/app/agent/models.py` after removing all imports
- Delete: `D:/560/MallAgent/after_sales_agent/app/agent/intent.py` after removing all imports
- Modify/Delete: tests that assert old `AgentPlan`, `AgentResult`, classifier or registry behavior
- Modify: `D:/560/MallAgent/after_sales_agent/app/agent/__init__.py`

**Interfaces:**
- No runtime module imports `MainAgent`, `AgentPlan`, `AgentResult`, `AgentRegistry`, `build_default_planner`, or `build_default_classifier`.
- `run_agent_turn` remains available for deterministic integration tests but calls the Deep Agent graph with injected fake dependencies.

- [ ] **Step 1: Write the import-boundary check**

```python
def test_runtime_has_no_legacy_orchestrator_imports():
    text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in Path("app/api").rglob("*.py")
    )
    assert "build_default_planner" not in text
    assert "AgentRegistry" not in text
```

- [ ] **Step 2: Run the import search before deletion**

Run: `rg -n "MainAgent|AgentPlan|AgentResult|AgentRegistry|build_default_planner|build_default_classifier" app tests`

Expected: output lists every remaining import that must be migrated before deletion.

- [ ] **Step 3: Delete only unused legacy modules and migrate tests**

Remove old planner/classifier/registry assertions. Replace them with tests that assert task routing, tool boundaries, runtime identity, and final main-agent response. Do not delete shared domain, memory, adapter or tool code.

- [ ] **Step 4: Verify no legacy imports remain**

Run: `rg -n "MainAgent|AgentPlan|AgentResult|AgentRegistry|build_default_planner|build_default_classifier" app tests`

Expected: no output and exit code 1.

## Task 8: Real Production Integration and RAG Data Validation

**Files:**
- Modify: `D:/560/MallAgent/after_sales_agent/scripts/smoke_test_services.py`
- Create: `D:/560/MallAgent/after_sales_agent/scripts/smoke_test_production_agent.py`
- Modify: `D:/560/MallAgent/after_sales_agent/app/diagnostics/readiness.py`
- Test: `D:/560/MallAgent/after_sales_agent/tests/integration/test_production_agent.py`

**Interfaces:**
- `smoke_test_production_agent.py` runs a product recommendation, order lookup and policy retrieval with real configured services and prints only redacted summaries.
- Production smoke tests return nonzero on missing required configuration, dependency failure, or an empty result where the test fixture expects data.

- [ ] **Step 1: Write the production smoke contract test**

```python
def test_production_smoke_requires_explicit_production_configuration(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    completed = run_smoke_script()
    assert completed.returncode != 0
    assert "API_KEY" in completed.stdout
    assert "sk-" not in completed.stdout
```

- [ ] **Step 2: Run the contract test to verify it fails**

Run: `pytest tests/integration/test_production_agent.py -q`

Expected: FAIL because the real-agent smoke script does not exist.

- [ ] **Step 3: Implement real-service smoke flow**

The script must:

1. Validate LLM, Redis, Milvus and Mall settings.
2. Run readiness probes.
3. Invoke the main Agent with a product query and verify that the product path calls `product_agent`.
4. Invoke a read-only order query with a real Mall JWT and verify user ownership.
5. Invoke a policy query and verify Milvus-backed source metadata.
6. Avoid after-sales write calls unless an explicit production feature flag and validated endpoint are present.
7. Redact tokens, URLs with credentials, prompt contents and raw upstream responses.

- [ ] **Step 4: Run production smoke tests in the configured environment**

Run: `python scripts/smoke_test_production_agent.py`

Expected: exit code 0 and redacted `llm=ok`, `redis=ok`, `milvus=ok`, `mall=ok`, `product_agent=ok`, `order_agent=ok`, `policy_agent=ok`.

## Task 9: Full Verification and Handoff

**Files:**
- Modify: `D:/560/MallAgent/after_sales_agent/docs/工程结构.md`
- Modify: `D:/560/MallAgent/after_sales_agent/docs/system-completion-assessment-2026-07-11.md` with the new verification date/results
- Modify: `D:/560/MallAgent/docs/superpowers/specs/2026-07-14-deep-agent-multi-agent-migration-design.md` only if implementation evidence changes an explicit requirement

- [ ] **Step 1: Run unit and integration tests**

Run: `pytest -q`

Expected: all configured local tests pass; tests requiring unavailable production services must be marked/skipped by explicit configuration, not silently ignored.

- [ ] **Step 2: Run static checks**

Run: `ruff check app tests`

Expected: zero Ruff errors.

Run: `python -m compileall -q app`

Expected: exit code 0.

- [ ] **Step 3: Run configured real-service checks**

Run: `python scripts/smoke_test_services.py` and `python scripts/smoke_test_production_agent.py`

Expected: all required production services report `ok`, or the final handoff explicitly records the exact service that is not configured and does not claim production readiness.

- [ ] **Step 4: Verify requirement coverage**

Run: `rg -n "create_deep_agent|create_agent|product_agent|order_agent|logistics_agent|refund_agent|after_sales_agent|policy_agent|ToolRuntime|health/ready" app tests`

Expected: the new architecture and production readiness path are present, and no old planner/registry runtime path remains.

- [ ] **Step 5: Record the handoff**

Report the changed files, test commands and real-service results. Separate “local tests pass” from “production dependencies verified”; never infer production readiness from local Fake Gateway tests.

## Plan Self-Review

- Spec coverage: main/subagent architecture is covered by Tasks 2–4; production LLM, Redis, Milvus and Mall integration is covered by Tasks 1, 5 and 8; streaming and checkpoint behavior is covered by Task 6; legacy removal is covered by Task 7; testing and acceptance are covered by Task 9.
- Placeholder scan: every task names concrete files, interfaces, tests, commands and expected outcomes; no unfinished implementation instructions remain.
- Type consistency: `AgentRuntimeContext`, `build_main_agent`, `build_checkpointed_agent_graph`, `ChatService.stream`, `check_readiness`, and `require_ready` are defined before later tasks consume them.
- Production safety: missing real dependencies fail closed in production; local fakes are restricted to tests.
