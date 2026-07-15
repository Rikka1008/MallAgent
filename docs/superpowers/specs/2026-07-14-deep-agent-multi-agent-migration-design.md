# Deep Agent 多智能体协作迁移设计

## 背景

当前 `after_sales_agent` 使用手写 `MainAgent`、意图分类器、规划器、注册表和多个 Agent 类组成编排链路。该结构能够完成售后 MVP，但主智能体和子智能体之间主要是显式 Python 调用，不符合参考系统中“主智能体理解与汇总、子智能体专业执行”的协作方式。

参考系统 `ecommerce601` 使用 `create_deep_agent` 构建主智能体，使用 `create_agent` 构建职责明确的子智能体，并通过 `task()` 传递业务目标。此次改造将整体迁移为该风格，旧的编排风格允许删除。

## 目标与非目标

### 目标

- 使用 `create_deep_agent` 构建主智能体。
- 使用 `create_agent` 构建六个专业子智能体：商品、订单、物流、退款、售后、政策。
- 主智能体负责意图理解、子智能体选择、上下文传递和最终客服回复。
- 子智能体负责工具调用和业务信息整理，不直接生成最终客服话术。
- 保留现有 Mall 身份隔离、订单归属校验、售后政策校验、幂等和审计能力。
- 保留 LangGraph checkpoint、多轮会话、长期记忆、RAG 和 SSE 能力。
- 接入真实生产 LLM、Redis、Milvus 和 Mall 服务，提供可配置的启动校验与联调路径。
- 让代码结构适合学习主智能体—子智能体协作原理。

### 非目标

- 本次不扩展真实 Mall 的新业务接口。
- 本次不重做前端页面和数据库业务模型。
- 不将安全校验交给 LLM 或系统提示词单独保证。

## 设计方案

### 1. 整体架构

```text
用户请求
  |
  v
主智能体 DeepSeek
  |-- 直接回答闲聊和无需业务数据的问题
  |-- task("product_agent", ...)       商品检索与推荐
  |-- task("order_agent", ...)         订单查询
  |-- task("logistics_agent", ...)     物流查询
  |-- task("refund_agent", ...)        退款查询
  |-- task("after_sales_agent", ...)   退换货与售后申请
  |-- task("policy_agent", ...)        售后政策检索
  |
  v
子智能体调用业务工具
  |
  v
主智能体汇总业务上下文并生成最终中文回复
  |
  v
SSE 只输出主智能体回复，checkpoint 保存会话状态
```

主智能体不直接访问订单数据库或执行售后写操作。所有业务数据访问通过工具完成，工具从运行时上下文取得当前身份和网关依赖。

### 2. 主智能体

主智能体使用 `create_deep_agent` 构建，配置主模型、系统提示词、通用工具、六个子智能体、checkpoint 和运行时上下文。

主系统提示词沿用参考系统的组织方式，并针对本项目优化：

- 商品咨询遵循“先搜索，再追问”。
- 商品无结果时直接告知暂无相关商品，不泄露用户画像偏好。
- 订单、物流、退款和售后问题必须使用真实工具结果。
- `user_id` 只使用运行时上下文，不从消息文本解析。
- 不编造商品、订单、物流、退款、政策和售后结果。
- 用户透露个人偏好时可以更新用户记忆，但不得影响安全校验。
- 售后写操作只能通过后端工具完成。
- 最终回复使用中文、简洁，通常不超过三段。
- 子智能体返回的是业务上下文，主智能体负责面向用户组织话术。

### 3. 子智能体

#### `product_agent`

负责商品目录检索、商品推荐和商品比较。使用商品检索工具返回商品名称、SKU、价格、品牌、分类和卖点。不得访问订单、物流、退款或售后工具。

#### `order_agent`

负责订单列表和订单详情查询。根据订单号查询指定订单；没有订单号时查询当前用户订单。订单归属由工具层校验。

#### `logistics_agent`

负责物流状态、承运商和运单号查询。支持订单号或运单号作为查询条件，不自行推断物流结果。

#### `refund_agent`

负责退款状态、退款金额、售后单号和预计到账时间查询。无结果时返回明确的未找到上下文。

#### `after_sales_agent`

负责收集退货/换货所需信息，调用政策检查工具，并通过现有安全执行入口创建售后申请。必须保留订单归属、商品匹配、售后类型、原因长度、幂等和审计检查。

#### `policy_agent`

负责检索售后政策、退换货规则、运费说明和流程。只返回检索证据，不执行商城写操作。

所有子智能体的提示词均要求：只调用职责范围内工具；不要重复查询已有结果；不要生成最终客服回复；不要编造工具未返回的信息；返回简洁、结构化、供主智能体汇总的上下文。

## 运行时上下文

新增统一的 `AgentRuntimeContext`，由 API 层在每次请求中构造：

```python
@dataclass
class AgentRuntimeContext:
    user_id: str
    session_id: str
    gateway: EcommerceGateway
    authorization: str | None = None
    case_context: AfterSalesCase | None = None
    long_term_memory: UserMemory | None = None
    idempotency_store: object | None = None
```

约束：

- `user_id` 只能来自 Mall 当前登录态。
- 请求体不接受可覆盖身份的 `user_id`。
- JWT 不写入 LLM 提示词、Agent 输出或普通日志。
- `task()` 的文本只描述业务目标，不携带不可信身份信息。
- 工具通过运行时上下文访问网关、当前用户和售后 Case。

## 生产服务接入

本次迁移不以 Fake 服务作为最终运行形态。Fake Gateway、内存 checkpoint 和本地检索器只用于单元测试；生产模式必须显式连接真实 LLM、Redis、Milvus 和 Mall 服务。

### 1. 生产 LLM

- 主智能体使用 DeepSeek 兼容接口，默认由 `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL` 和 `DEEPSEEK_CHAT_MODEL` 配置。
- 子智能体复用 DeepSeek 主模型配置，由 `DEEPSEEK_API_KEY`、`DEEPSEEK_BASE_URL` 和 `DEEPSEEK_CHAT_MODEL` 统一配置。
- Embedding 使用与商品知识库和长期记忆 collection 匹配的真实 Embedding 服务，维度必须与 Milvus schema 一致。
- API Key 只能从环境变量或生产密钥管理系统读取，不写入源码、提示词、日志和 SSE。
- 为主模型、子模型和 Embedding 分别配置超时、最大 token、重试次数和并发上限。
- 生产启动时校验必要配置；缺少密钥或模型配置时拒绝进入 production 模式，而不是静默回退到 Fake 或本地模型。

### 2. Redis

- Redis 用于 LangGraph checkpoint、售后 Case 热数据和跨进程幂等存储。
- 使用独立的 `REDIS_URL`、命名空间前缀、连接池大小、连接超时和 checkpoint TTL。
- 生产 Redis 支持密码、TLS 和数据库编号配置；连接池由应用生命周期统一创建和关闭。
- 启动健康检查执行 `PING`，运行时异常通过统一错误处理返回，不暴露连接串。
- checkpoint、Case 和幂等 key 使用不同前缀，避免数据互相覆盖。
- 生产环境禁止使用进程内 `MemoryIdempotencyStore` 作为写操作的最终存储。

### 3. Milvus

- Milvus 用于商品目录、售后政策和长期语义记忆检索。
- 配置 `MILVUS_URI`、token、database、TLS、collection 名称、Embedding 维度和检索参数。
- 启动时校验目标 collection、字段 schema、索引和维度；不匹配时阻止服务进入 ready 状态。
- 商品推荐必须连接真实商品 collection；政策 Agent 必须连接真实售后知识 collection；长期记忆按用户 namespace 或过滤条件隔离。
- 向量化调用放入线程池或异步封装，不能阻塞 FastAPI 事件循环。
- 生产模式关闭“空检索静默成功”行为；Milvus 不可用时明确标记能力不可用，并避免主智能体编造检索结果。

### 4. Mall 服务

- Agent 使用当前请求的 Mall JWT 调用 `/sso/info`，以 Mall 返回的会员 ID 作为唯一用户身份。
- 订单、物流、退款查询调用真实 Mall Portal/业务接口，并由 `MallEcommerceGateway` 统一封装。
- 生产环境不信任请求体中的 `user_id`、订单归属或用户自报信息。
- 真实售后写接口接入前，`after_sales_agent` 只能执行政策检查和资格判断；写入能力必须在接口、权限、幂等键和回滚策略验证完成后开放。
- Mall API 的 401、403、404、429、5xx 和超时分别映射为认证失败、权限不足、未找到、限流、服务不可用和网关超时。
- Mall JWT 不进入日志、LLM 上下文、缓存 value 或错误消息。

### 5. 配置与部署

配置按应用、LLM、Redis、Milvus、Mall 和安全分组，提供 `.env.example` 作为本地联调模板；生产使用密钥管理系统注入环境变量。

生产启动分为三个状态：

```text
配置校验 → 依赖健康检查 → ready
```

任一必要依赖未配置或健康检查失败时，健康接口必须区分 `live` 和 `ready`，避免将未连接真实服务的实例误判为可接收流量。

## 工具层设计

现有业务工具整理为 LangChain 工具，业务参数和基础设施依赖分离：

```python
@tool
async def lookup_order(
    order_id: str,
    runtime: ToolRuntime[AgentRuntimeContext],
) -> dict:
    gateway = runtime.context.gateway
    user_id = runtime.context.user_id
    ...
```

工具参数只暴露订单号、商品编号、售后类型和原因等业务字段；用户身份、网关、Case 和幂等存储均从运行时上下文读取。

必须保留的后端保护：

- Mall JWT 认证。
- 当前用户 ID 绑定。
- 订单归属校验。
- 商品是否属于订单校验。
- 售后政策检查。
- 售后写入幂等键。
- 审计事件记录。
- 工具结果脱敏。

## 会话图与流式响应

`graph.py` 改为负责构建和暴露主智能体，不再承载旧的手写规划流程。API 层执行流程为：

1. 获取当前 Mall 会员和用户 ID。
2. 获取会话 Case、长期记忆和业务网关。
3. 构造 `AgentRuntimeContext`。
4. 使用当前 `thread_id` 调用主智能体。
5. 通过 Agent 流式接口只输出主智能体的文本 token。
6. 子智能体工具调用、中间结果和内部提示词不直接输出给用户。
7. 结束后从最终状态提取 AI 回复并保存需要的对话记录。
8. 保存 checkpoint、语义记忆和 Case 状态。

流式实现优先采用参考系统的 `astream_events` 模式，并通过主智能体运行标识或主模型事件过滤子智能体输出；不得依赖未经验证的模型名称字符串作为唯一过滤条件。

## 错误处理与降级

- 子智能体失败：主智能体说明当前查询暂时不可用，不编造结果。
- 工具无结果：返回明确的未找到信息。
- 缺少业务槽位：主智能体追问缺失字段。
- 售后操作被拒绝：返回工具层业务原因，不绕过校验。
- Mall 服务认证失败：返回认证错误，不继续执行订单或售后操作。
- 外部依赖异常：返回服务暂不可用，记录脱敏审计信息。
- 流式异常：发送统一 SSE 错误事件，不泄露堆栈、token 或内部配置。

## 文件迁移范围

### 新增或重写

- `app/agent/main_agent.py`
- `app/agent/subagents.py`
- `app/agent/context.py`
- `app/agent/graph.py`
- 必要的 `app/services/chat_service.py`
- LLM 配置和 Agent 相关依赖
- 主 Agent、子 Agent、工具和流式响应测试

### 删除旧编排

- `app/agent/orchestrator.py`
- `app/agent/llm_intent.py`
- `app/agent/registry.py`
- `app/agent/nodes.py`
- 旧的 `app/agent/subagents/` 手写 Agent 类
- 旧的 `AgentPlan`、`AgentResult` 规划执行体系
- 仅服务旧规划流程的意图和响应生成代码

### 保留

- `adapters/`
- `domain/`
- `tools/` 中的 Mall、订单、物流、退款、售后和政策能力
- `services/cases/`
- `services/memory/`
- `core/database/`
- RAG、Milvus、Redis、PostgreSQL 和审计设施

删除范围以实际引用关系为准；若某个模块仍被记忆、API 或工具使用，不会因名称相似而删除。

## 测试策略

### 单元测试

- 六个子智能体名称、描述和工具集合正确。
- 商品 Agent 只拥有商品检索工具。
- 售后 Agent 只拥有允许的售后和政策工具。
- 工具从运行时上下文取得用户身份和网关。
- 用户输入中的伪造 `user_id` 不会覆盖运行时身份。
- 售后幂等、订单归属和商品匹配仍然有效。

### 集成测试

- 商品推荐路径能调用 `product_agent` 并生成最终回复。
- 订单、物流、退款、政策和售后路径能调用对应子智能体。
- 多轮会话能从 checkpoint 继续使用订单号和 Case 上下文。
- 子智能体中间内容不会泄漏到最终 SSE 文本。
- 工具失败、无结果、认证失败和售后拒绝能正确降级。

### API 测试

- SSE 能返回开始、增量、结束和错误事件。
- `/api/chat` 请求体不允许客户端伪造 `user_id`。
- 会话重置仍能清除 checkpoint。
- 真实 Mall 未配置时，测试使用 Fake Gateway，不触发外部网络。

### 生产联调测试

- 使用真实主 LLM 完成一次闲聊和一次需要子智能体的请求。
- 使用真实子 Agent LLM 完成商品推荐、订单查询和售后政策检索。
- Redis `PING`、checkpoint 持久化、跨进程幂等和 TTL 行为验证通过。
- Milvus collection、schema、索引、Embedding 维度和真实检索链路验证通过。
- 使用真实 Mall JWT 验证 `/sso/info`、订单归属和至少一条只读业务链路。
- 对 Mall 401、403、限流、超时和服务异常执行脱敏错误联调。
- 生产 readiness 检查能够阻止缺少必要依赖的实例接收流量。

## 验收标准

- 主智能体通过 `task()` 调用六个专业子智能体。
- 旧的规划器、注册表和手写 Agent 编排不再参与运行路径。
- 商品推荐成为一等业务路径。
- 子智能体只做专业执行和上下文整理。
- 主智能体生成最终回复并负责跨领域协作。
- 生产模式能够连接真实 LLM、Redis、Milvus 和 Mall 服务，不依赖 Fake 服务运行。
- 生产启动能够校验配置并完成必要依赖的健康检查。
- 原有身份、安全、幂等、记忆和审计测试不被无意破坏。
- 新增测试覆盖六条子智能体路径和关键错误分支。
- 运行 Ruff、pytest 和 Python 编译检查，并根据实际环境记录未配置的外部服务。
