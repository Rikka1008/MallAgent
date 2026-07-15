# LLM Multi-Agent Hybrid RAG Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the after-sales service with structured LLM intent classification, maintainable main/sub-agent routing, and traceable hybrid retrieval with automatic fallback.

**Architecture:** Preserve the existing API and business tools while inserting small protocol-driven services at the intent, routing, and retrieval boundaries. External model and database clients are constructor-injected, lazily initialized, and wrapped by deterministic fallback coordinators.

**Tech Stack:** Python 3.13, Pydantic 2, FastAPI, httpx, LangGraph-compatible state, pymilvus, FlagEmbedding, pytest, pytest-asyncio.

## Global Constraints

- Preserve the current FastAPI chat endpoint and the existing `AgentState` compatibility fields.
- LLM, Milvus, embedding, and reranker failures must not make the customer-service flow unavailable.
- LLM fallback is the rule classifier; vector fallback is keyword retrieval; reranker fallback is RRF order.
- Record sanitized degradation categories without secrets, stack traces, or complete model responses.
- One user turn routes to at most one sub-agent.
- Business facts and mutations come only from the existing tool layer.

---

## File Structure

- `app/agent/models.py`: shared intent, routing, result, source, and degradation Pydantic models.
- `app/agent/intent.py`: rule classifier and slot extraction only.
- `app/agent/llm_intent.py`: OpenAI-compatible structured classifier and fallback coordinator.
- `app/agent/subagents/base.py`: sub-agent protocol and execution context.
- `app/agent/subagents/*.py`: one focused implementation per business domain.
- `app/agent/registry.py`: intent-to-sub-agent registration and validation.
- `app/agent/orchestrator.py`: main-agent classify, route, aggregate flow.
- `app/agent/graph.py`: compatibility entry points and optional LangGraph wiring.
- `app/knowledge/retrieval/models.py`: normalized retrieval candidate/source models.
- `app/knowledge/retrieval/vector_retriever.py`: Milvus-only retrieval adapter.
- `app/knowledge/retrieval/fusion.py`: stable IDs, deduplication, and RRF.
- `app/knowledge/retrieval/reranker.py`: BGE reranker and pass-through fallback.
- `app/knowledge/retrieval/hybrid_retriever.py`: orchestration and degradation policy.

### Task 1: Structured Agent Models and Configuration

**Files:**
- Create: `after_sales_agent/app/agent/models.py`
- Modify: `after_sales_agent/app/agent/state.py`
- Modify: `after_sales_agent/app/config/llm.py`
- Modify: `after_sales_agent/app/config/rag.py`
- Test: `after_sales_agent/tests/unit/test_agent_models.py`
- Test: `after_sales_agent/tests/unit/test_config.py`

**Interfaces:**
- Produces: `IntentDecision`, `DegradationEvent`, `RouteRecord`, `RetrievalSource`, `AgentResult`.
- Produces: new backward-compatible `AgentState` fields using those models.

- [ ] **Step 1: Write failing model tests**

```python
from pydantic import ValidationError
from agent.models import IntentDecision

def test_intent_decision_rejects_out_of_range_confidence():
    with pytest.raises(ValidationError):
        IntentDecision(intent="order_query", confidence=1.1, reason="订单", strategy="llm")

def test_agent_state_has_empty_observability_collections():
    state = AgentState(session_id="S1", user_id="U1")
    assert state.agent_results == []
    assert state.route_history == []
    assert state.degradation_events == []
    assert state.retrieval_sources == []
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/unit/test_agent_models.py tests/unit/test_config.py -v`
Expected: FAIL because `agent.models` and new config attributes do not exist.

- [ ] **Step 3: Implement minimal models and configuration**

Use Pydantic models with `Field(ge=0, le=1)` for confidence, `Literal["llm", "rule", "rule_fallback"]` for strategy, and `default_factory=list` for all state collections. Add exact environment-backed settings from the design, including timeout `10`, confidence threshold `0.65`, RRF constant `60`, and reranker model `BAAI/bge-reranker-v2-m3`.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python -m pytest tests/unit/test_agent_models.py tests/unit/test_config.py -v`
Expected: PASS.

### Task 2: LLM Intent Classification with Rule Fallback

**Files:**
- Modify: `after_sales_agent/app/agent/intent.py`
- Create: `after_sales_agent/app/agent/llm_intent.py`
- Modify: `after_sales_agent/app/agent/prompts.py`
- Test: `after_sales_agent/tests/unit/test_intent.py`
- Create: `after_sales_agent/tests/unit/test_llm_intent.py`

**Interfaces:**
- Produces: `RuleIntentClassifier.classify(message: str) -> IntentDecision`.
- Produces: `LlmIntentClassifier.classify(message: str) -> IntentDecision`.
- Produces: `FallbackIntentClassifier.classify(message: str) -> IntentDecision`.
- Preserves: `classify_intent(message: str) -> str` compatibility wrapper.

- [ ] **Step 1: Write failing async classifier tests**

```python
async def test_valid_llm_json_returns_structured_decision():
    transport = FakeIntentTransport({'intent':'logistics_query','confidence':0.92,'reason':'询问快递'})
    result = await LlmIntentClassifier(transport=transport).classify("快递到哪了")
    assert result.intent == "logistics_query"
    assert result.strategy == "llm"

async def test_invalid_llm_json_falls_back_to_rules():
    result = await FallbackIntentClassifier(
        primary=ExplodingClassifier(ValueError("bad json")),
        fallback=RuleIntentClassifier(),
    ).classify("查询订单 ORD1001")
    assert result.intent == "order_query"
    assert result.strategy == "rule_fallback"
    assert result.fallback_reason == "invalid_response"
```

Add equivalent tests for timeout, disabled LLM, illegal enum, and confidence below `0.65`.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/unit/test_intent.py tests/unit/test_llm_intent.py -v`
Expected: FAIL because classifier classes do not exist.

- [ ] **Step 3: Implement classifiers**

Define an `IntentClassifier` protocol with async `classify`. `LlmIntentClassifier` sends a chat-completions request through an injected transport, asks for the `IntentDecision` JSON schema, and validates only the parsed content. Map exceptions to the fixed categories from the design. `FallbackIntentClassifier` applies the threshold and returns the rule decision with sanitized fallback metadata. Keep slot extraction unchanged.

- [ ] **Step 4: Run focused and legacy tests**

Run: `python -m pytest tests/unit/test_intent.py tests/unit/test_llm_intent.py -v`
Expected: PASS, including legacy string-returning wrapper assertions.

### Task 3: Isolated Sub-Agents and Registry

**Files:**
- Create: `after_sales_agent/app/agent/subagents/__init__.py`
- Create: `after_sales_agent/app/agent/subagents/base.py`
- Create: `after_sales_agent/app/agent/subagents/order.py`
- Create: `after_sales_agent/app/agent/subagents/logistics.py`
- Create: `after_sales_agent/app/agent/subagents/refund.py`
- Create: `after_sales_agent/app/agent/subagents/after_sales.py`
- Create: `after_sales_agent/app/agent/subagents/policy.py`
- Create: `after_sales_agent/app/agent/registry.py`
- Modify: `after_sales_agent/app/agent/prompts.py`
- Create: `after_sales_agent/tests/unit/test_subagents.py`
- Create: `after_sales_agent/tests/unit/test_agent_registry.py`

**Interfaces:**
- Consumes: existing tool functions and `AgentState`.
- Produces: `AgentContext(gateway, policy_retriever)` and `SubAgent.run(...) -> AgentResult`.
- Produces: `AgentRegistry.resolve(intent: str) -> SubAgent | None`.

- [ ] **Step 1: Write failing permission and behavior tests**

```python
async def test_order_agent_calls_only_order_tool():
    tools = FakeOrderTools()
    result = await OrderAgent(tools=tools).run(order_state(), fake_context())
    assert tools.calls == [("get_order", "ORD1001", "U1")]
    assert result.agent_name == "OrderAgent"

def test_registry_rejects_duplicate_intent_registration():
    with pytest.raises(ValueError, match="order_query"):
        AgentRegistry([FakeAgent("order_query"), FakeAgent("order_query")])
```

Cover all five agents, missing slots, ineligible after-sales handoff, and policy sources.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/unit/test_subagents.py tests/unit/test_agent_registry.py -v`
Expected: FAIL because sub-agent modules do not exist.

- [ ] **Step 3: Implement minimal agents**

Each file defines one class, one supported intent, one immutable allowed tool bundle, and one domain prompt constant. Agents receive typed tool bundles rather than a general dictionary, so an OrderAgent cannot access refund or mutation tools. Return `AgentResult`; never write directly to unrelated state fields.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python -m pytest tests/unit/test_subagents.py tests/unit/test_agent_registry.py -v`
Expected: PASS.

### Task 4: Main-Agent Orchestration and Compatibility Graph

**Files:**
- Create: `after_sales_agent/app/agent/orchestrator.py`
- Modify: `after_sales_agent/app/agent/graph.py`
- Modify: `after_sales_agent/app/agent/nodes.py`
- Modify: `after_sales_agent/app/api/dependencies.py`
- Modify: `after_sales_agent/app/api/routes.py`
- Test: `after_sales_agent/tests/integration/test_agent_graph.py`
- Test: `after_sales_agent/tests/integration/test_chat_api.py`

**Interfaces:**
- Consumes: `IntentClassifier`, `AgentRegistry`, `AgentContext`.
- Produces: `MainAgent.run_turn(state: AgentState) -> AgentState`.
- Preserves: `run_agent_turn(state, gateway=None, policy_retriever=None, classifier=None, registry=None)`.

- [ ] **Step 1: Write failing routing and fallback integration tests**

```python
async def test_main_agent_records_route_and_result():
    state = AgentState(session_id="S1", user_id="U1", messages=["查订单 ORD1001"])
    result = await run_agent_turn(state, classifier=StaticClassifier("order_query"), registry=registry)
    assert result.active_agent == "OrderAgent"
    assert result.route_history[-1].intent == "order_query"
    assert result.agent_results[-1].status == "success"

async def test_missing_slots_does_not_run_subagent():
    result = await run_agent_turn(order_query_without_id(), classifier=StaticClassifier("order_query"))
    assert result.active_agent is None
    assert result.missing_slots == ["order_id"]
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/integration/test_agent_graph.py tests/integration/test_chat_api.py -v`
Expected: FAIL on missing orchestration fields and injected classifier support.

- [ ] **Step 3: Implement orchestration**

Move classify-route-aggregate control into `MainAgent`. Keep deterministic response formatting in a dedicated compatibility function in `nodes.py`. `graph.py` becomes a thin construction adapter. API dependencies cache only stateless/shared model clients; request-specific gateway authorization remains request-scoped.

- [ ] **Step 4: Run graph and API tests**

Run: `python -m pytest tests/integration/test_agent_graph.py tests/integration/test_chat_api.py -v`
Expected: PASS with existing response text and new routing metadata.

### Task 5: Traceable Retrieval Models, Stable IDs, and RRF

**Files:**
- Create: `after_sales_agent/app/knowledge/retrieval/models.py`
- Create: `after_sales_agent/app/knowledge/retrieval/fusion.py`
- Modify: `after_sales_agent/app/knowledge/ingestion/splitter.py`
- Modify: `after_sales_agent/app/knowledge/ingestion/milvus_store.py`
- Create: `after_sales_agent/tests/unit/test_retrieval_fusion.py`
- Modify: `after_sales_agent/tests/unit/test_rag_ingestion.py`

**Interfaces:**
- Produces: `RetrievalCandidate`, `RetrievalSource`.
- Produces: `stable_document_id(source_path: str) -> str`, `stable_chunk_id(...) -> str`.
- Produces: `reciprocal_rank_fusion(keyword, vector, k=60) -> list[RetrievalCandidate]`.

- [ ] **Step 1: Write failing provenance and fusion tests**

```python
def test_rrf_deduplicates_and_preserves_both_channels():
    fused = reciprocal_rank_fusion([candidate("c1", .8, "keyword")], [candidate("c1", .9, "vector")])
    assert len(fused) == 1
    assert fused[0].retrieval_channels == {"keyword", "vector"}
    assert fused[0].keyword_score == .8
    assert fused[0].vector_score == .9

def test_stable_chunk_id_is_repeatable():
    assert stable_chunk_id("policy/a.md", "same") == stable_chunk_id("policy/a.md", "same")
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/unit/test_retrieval_fusion.py tests/unit/test_rag_ingestion.py -v`
Expected: FAIL because normalized retrieval models and fusion do not exist.

- [ ] **Step 3: Implement models and pure fusion functions**

Use SHA-256 truncated to 32 hex characters for stable IDs, normalized POSIX-style paths, rank positions starting at one, and `1 / (k + rank)`. Preserve raw channel scores and calculate `fusion_score` as the sum of channel contributions. Ensure ingestion metadata always includes source name/path, document ID, and chunk ID.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python -m pytest tests/unit/test_retrieval_fusion.py tests/unit/test_rag_ingestion.py -v`
Expected: PASS.

### Task 6: Vector Adapter, BGE Reranker, and Hybrid Retrieval

**Files:**
- Create: `after_sales_agent/app/knowledge/retrieval/vector_retriever.py`
- Modify: `after_sales_agent/app/knowledge/retrieval/keyword_retriever.py`
- Modify: `after_sales_agent/app/knowledge/retrieval/reranker.py`
- Modify: `after_sales_agent/app/knowledge/retrieval/hybrid_retriever.py`
- Modify: `after_sales_agent/tests/unit/test_hybrid_retriever.py`
- Create: `after_sales_agent/tests/unit/test_reranker.py`

**Interfaces:**
- Produces: `MilvusVectorRetriever.search(query, limit) -> list[RetrievalCandidate]`.
- Produces: `BgeReranker.rerank(query, candidates) -> list[RetrievalCandidate]`.
- Produces: `HybridSearchResult(candidates, degradation_events, strategy)`.

- [ ] **Step 1: Write failing hybrid and reranker tests**

```python
def test_hybrid_search_combines_keyword_and_vector_candidates():
    result = HybridRetriever(keyword=FakeKeyword([kw]), vector=FakeVector([vec]), reranker=Identity()).search("退货", 5)
    assert [item.chunk_id for item in result.candidates] == ["shared", "keyword-only", "vector-only"]
    assert result.strategy == "hybrid_rrf"

def test_vector_failure_returns_keyword_results_and_event():
    result = HybridRetriever(keyword=FakeKeyword([kw]), vector=ExplodingVector(), reranker=Identity()).search("退货", 5)
    assert result.candidates == [kw]
    assert result.degradation_events[0].fallback_strategy == "keyword"

def test_bge_reranker_reorders_candidates():
    ranked = BgeReranker(model=FakeRerankModel([0.1, 0.9])).rerank("query", [first, second])
    assert [item.chunk_id for item in ranked] == [second.chunk_id, first.chunk_id]
```

Add separate embedding failure, missing collection, disabled reranker, and reranker exception cases.

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/unit/test_hybrid_retriever.py tests/unit/test_reranker.py -v`
Expected: FAIL because current retriever is vector-only and reranker is a no-op.

- [ ] **Step 3: Implement the retrieval pipeline**

Keep Milvus response normalization inside `vector_retriever.py`. Make keyword retrieval emit the same candidate model. `HybridRetriever` catches failures per capability, invokes both channels independently, fuses successful candidates, limits rerank input, and returns normalized scores and events. `BgeReranker` lazily imports `FlagReranker`, uses injected models in tests, and never swallows errors internally so the hybrid coordinator owns fallback policy.

- [ ] **Step 4: Run tests and verify GREEN**

Run: `python -m pytest tests/unit/test_hybrid_retriever.py tests/unit/test_reranker.py -v`
Expected: PASS.

### Task 7: Policy Integration, API Observability, and Full Regression

**Files:**
- Modify: `after_sales_agent/app/tools/policy_tools.py`
- Modify: `after_sales_agent/app/api/schemas.py`
- Modify: `after_sales_agent/app/api/routes.py`
- Modify: `after_sales_agent/app/config/__init__.py`
- Modify: `after_sales_agent/README.md`
- Modify: `after_sales_agent/tests/integration/test_agent_rag.py`
- Modify: `after_sales_agent/tests/integration/test_chat_api.py`

**Interfaces:**
- Consumes: `HybridSearchResult`.
- Produces: policy tool output with `snippets`, `sources`, `retrieval_strategy`, and `degradations`.
- Preserves existing `ChatResponse` fields while adding optional observability fields with defaults.

- [ ] **Step 1: Write failing end-to-end tests**

```python
async def test_policy_turn_exposes_traceable_source():
    result = await run_agent_turn(policy_state(), policy_retriever=traceable_retriever())
    assert result.retrieval_sources[0].source_name == "售后服务政策.md"
    assert result.retrieval_sources[0].chunk_id == "chunk-1"

async def test_chat_api_survives_all_model_fallbacks(client, overrides):
    response = await client.post("/api/chat", json={"session_id":"S1","message":"七天无理由退货规则"})
    assert response.status_code == 200
    assert response.json()["reply"]
```

- [ ] **Step 2: Run tests and verify RED**

Run: `python -m pytest tests/integration/test_agent_rag.py tests/integration/test_chat_api.py -v`
Expected: FAIL because provenance is not propagated to state/API.

- [ ] **Step 3: Complete integration and documentation**

Map retrieval candidates to policy snippets and state sources without discarding provenance. Document all environment variables, default fallback behavior, ingestion prerequisite, and local commands. Keep new API observability fields optional to avoid breaking old clients.

- [ ] **Step 4: Run focused integration tests**

Run: `python -m pytest tests/integration/test_agent_rag.py tests/integration/test_chat_api.py -v`
Expected: PASS.

- [ ] **Step 5: Run full verification**

Run: `python -m pytest -q`
Expected: all tests PASS with no warnings introduced by this change.

Run: `python -m ruff check app tests`
Expected: exit code 0.

Run: `python -m ruff format --check app tests`
Expected: exit code 0.

## Self-Review Result

- Spec coverage: all intent, routing, agent isolation, hybrid retrieval, reranking, provenance, and fallback requirements map to Tasks 1–7.
- Placeholder scan: no implementation placeholders remain.
- Type consistency: `IntentDecision`, `AgentResult`, `RetrievalCandidate`, `RetrievalSource`, and `DegradationEvent` are introduced before consumption.
- Scope: multi-intent routing and autonomous model-driven mutations remain explicitly excluded.

