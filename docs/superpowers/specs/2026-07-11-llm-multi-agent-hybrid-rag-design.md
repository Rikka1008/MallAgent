# LLM 意图识别、主子智能体与混合 RAG 设计

## 目标

升级 `after_sales_agent`，使其使用 LLM 完成结构化意图识别，由主智能体路由到五个职责和工具集相互隔离的子智能体，并以 Milvus 向量召回、关键词召回、融合排序和 BGE reranker 构成可追溯的混合 RAG。所有外部智能能力都必须支持显式、可观测的自动降级。

## 范围

本次改造覆盖：

- LLM 结构化意图识别及规则降级。
- 主智能体路由、子智能体执行、共享状态和结果聚合。
- OrderAgent、LogisticsAgent、RefundAgent、AfterSalesAgent、PolicyAgent。
- Milvus 向量检索、关键词检索、候选融合、rerank 和来源追溯。
- 配置、依赖注入、单元测试、集成测试与降级测试。

不在本次范围内：多意图并行执行、人工坐席系统集成、管理后台 UI、在线训练、模型微调、异步批量知识库重建。

## 全局约束

- 保持现有 FastAPI 对话入口和 `AgentState` 主要字段兼容。
- 不允许 LLM、Milvus、embedding 或 reranker 故障导致客服主流程不可用。
- LLM 不可用或结构化输出无效时，降级到现有规则分类器。
- Milvus 或 embedding 不可用时，降级到关键词检索。
- reranker 不可用时，降级到融合分数排序。
- 每次降级必须记录能力名称、原因和最终采用的策略，不向用户暴露密钥、堆栈或内部连接信息。
- 业务工具调用继续执行用户身份和订单归属校验。

## 方案选择

采用“可插拔能力 + 显式降级”的渐进式方案。现有工具函数、API 和状态模型继续作为兼容边界，新增协议和服务封装 LLM、子智能体及检索能力。相比整体重写 LangGraph，该方案能用较小的回归面实现明确的智能体职责；相比单智能体动态调用所有工具，它能保持工具权限、提示词和结果类型可审计。

## 架构

### 意图识别

新增 `IntentDecision` 结构化模型：

- `intent`: 仅允许现有 `Intent` 枚举值。
- `confidence`: `0.0` 至 `1.0`。
- `reason`: 简短说明判定依据，不保存模型隐式思维过程。
- `strategy`: `llm` 或 `rule_fallback`。
- `fallback_reason`: 未降级时为 `None`，降级时为经过清理的错误类别。

`LlmIntentClassifier` 使用 OpenAI 兼容 HTTP 接口和 Pydantic JSON Schema约束输出。模型响应必须通过 Pydantic 校验。超时、网络错误、非 2xx、非法 JSON、非法枚举或置信度越界均调用 `RuleIntentClassifier`。规则分类器保留现有匹配逻辑，但也返回完整 `IntentDecision`。

主智能体使用置信度阈值控制路由：LLM 结果低于配置阈值时使用规则结果；若两者均为 `unknown`，进入统一未解决流程，不调用业务工具。

### 主子智能体

主智能体职责：

1. 获取最新用户消息和历史状态。
2. 调用意图分类器并写入 `intent_decision`。
3. 抽取、合并槽位并计算缺失槽位。
4. 根据意图从注册表选择一个子智能体。
5. 调用子智能体并聚合其结构化结果。
6. 生成最终响应或触发现有人工兜底逻辑。

五个子智能体通过统一协议执行：

```python
class SubAgent(Protocol):
    name: str
    supported_intents: frozenset[str]

    async def run(self, state: AgentState, context: AgentContext) -> AgentResult: ...
```

工具权限固定如下：

| 子智能体 | 意图 | 允许工具 |
|---|---|---|
| OrderAgent | `order_query` | `get_order` |
| LogisticsAgent | `logistics_query` | `get_logistics` |
| RefundAgent | `refund_query` | `get_refund_status` |
| AfterSalesAgent | `return_exchange` | `check_after_sales_policy`、`create_after_sales_request` |
| PolicyAgent | `policy_query` | `search_policy` |

每个子智能体拥有独立系统提示词，但业务事实只能来自其工具结果。第一阶段不让 LLM 自主决定工具参数或执行高风险操作；槽位和参数仍由确定性代码提供，避免模型越权或编造。

### 状态传递与结果聚合

在 `AgentState` 中新增：

- `intent_decision: IntentDecision | None`
- `active_agent: str | None`
- `agent_results: list[AgentResult]`
- `route_history: list[RouteRecord]`
- `degradation_events: list[DegradationEvent]`
- `retrieval_sources: list[RetrievalSource]`

`AgentResult` 包含 `agent_name`、`status`、`data`、`response`、`sources` 和 `handoff_required`。主智能体只接受注册表中与当前意图匹配的子智能体结果。子智能体异常会转换为失败结果并进入现有未解决计数，不把异常对象写入响应。

单轮只路由一个子智能体。历史 `slots` 和长期记忆沿用现有逻辑；每轮新增不可变的路由记录，便于审计实际分类、路由和降级路径。

## 混合检索

### 候选模型

统一使用 `RetrievalCandidate`：

- `chunk_id`、`document_id`
- `title`、`content`
- `metadata`
- `source_name`、`source_path`
- `retrieval_channels`
- `keyword_score`、`vector_score`、`fusion_score`、`rerank_score`
- `final_score`

来源字段在知识入库阶段写入 Milvus，并在关键词路径中从文档 metadata 原样继承。对缺少标识的旧数据，使用稳定的内容哈希生成 `chunk_id`，以规范化后的来源路径生成 `document_id`。

### 召回和融合

`HybridRetriever.search(query, limit)` 执行：

1. 校验并规范化查询。
2. 以大于最终 `limit` 的候选数分别执行关键词和 Milvus 向量召回。
3. 用 `chunk_id` 去重；旧数据无 `chunk_id` 时使用来源路径与内容哈希作为去重键。
4. 使用 Reciprocal Rank Fusion 合并两路排名：`1 / (60 + rank)`。
5. 将融合后的前 N 个候选交给 reranker。
6. 返回前 `limit` 个结果，并保留各阶段分数和来源字段。

如果向量路径失败，关键词结果的 `retrieval_channels` 仅包含 `keyword`；如果关键词路径无结果，向量结果仍可单独返回。只有两路都无结果时返回空列表。

### Reranker

使用 `FlagEmbedding` 的 BGE reranker，对 `(query, candidate.content)` 批量评分。模型惰性加载，避免应用启动时强制下载或占用内存。模型名、批大小、最大候选数和启用开关由配置控制。

reranker 加载或推理失败时，保留 RRF 顺序，将 `rerank_score` 设为 `None`，`final_score` 使用归一化后的 `fusion_score`，并记录降级事件。成功时，`final_score` 使用 reranker 分数，RRF 分数作为稳定的次级排序键。

## 配置与依赖注入

新增配置项：

- `LLM_INTENT_ENABLED=true`
- `LLM_INTENT_CONFIDENCE_THRESHOLD=0.65`
- `LLM_REQUEST_TIMEOUT_SECONDS=10`
- `RAG_RETRIEVER=hybrid`
- `RAG_KEYWORD_CANDIDATE_LIMIT=20`
- `RAG_VECTOR_CANDIDATE_LIMIT=20`
- `RAG_RERANK_CANDIDATE_LIMIT=20`
- `RAG_ENABLE_RERANK=true`
- `RERANK_MODEL_NAME=BAAI/bge-reranker-v2-m3`
- `RERANK_BATCH_SIZE=8`

API 依赖模块负责构造并缓存分类器、子智能体注册表和检索器。测试通过构造函数注入 fake，不连接真实 LLM、Milvus 或模型仓库。

## 错误处理与可观测性

降级错误被归类为 `disabled`、`timeout`、`connection_error`、`invalid_response`、`missing_collection`、`model_error` 或 `unexpected_error`。日志记录 session ID、能力、类别和采用的后备策略，不记录 API key、完整模型响应或用户敏感字段。

结构化状态保存同样的类别，供 API 测试和后续监控使用。用户最终响应保持业务语义，不因正常降级附加技术提示。

## 测试策略

### 意图识别

- 合法 LLM JSON 能生成完整 `IntentDecision`。
- 非法 JSON、非法意图、超时和低置信度分别触发规则降级。
- 降级结果包含策略和经过清理的原因。

### 智能体路由

- 每种意图只路由到对应子智能体。
- 每个子智能体只能访问声明的工具。
- 缺失槽位时不调用子智能体工具。
- 子智能体异常会形成失败结果并进入人工兜底计数。
- 现有订单、物流、退款、政策和售后集成用例保持通过。

### 混合检索

- 关键词和向量候选正确去重并按 RRF 融合。
- 两路来源和阶段分数完整保留。
- reranker 成功时改变最终排序。
- Milvus、embedding 和 reranker 分别故障时采用指定后备策略。
- 缺少来源字段的旧 Milvus 记录能生成稳定标识。

### 验收标准

- 全部新增单元测试和现有测试通过。
- 五类业务意图均经主智能体路由到正确子智能体。
- 任一外部智能能力不可用时，仍能通过规则和关键词路径完成对应的可用回答。
- 政策检索响应能够追溯至具体文件与片段，并能区分关键词、向量及混合命中。

