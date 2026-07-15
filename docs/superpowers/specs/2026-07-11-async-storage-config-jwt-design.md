# 售后 Agent 异步存储、配置与 JWT 集成设计

## 目标

在不改变现有售后业务行为的前提下，修复 RAG 配置契约，建立可扩展的独立配置包，将 PostgreSQL 长期记忆链路改为真正的异步访问，并让 Agent 使用 Mall 用户当前登录态的 JWT 调用受保护接口。

## 现状与判断

- `core/database/postgre_pool.py` 创建了 `asyncpg` 池，但没有业务代码使用它。
- `SqlAlchemyUserMemoryRepository` 使用同步引擎，FastAPI 聊天路由也是同步函数；现有 PostgreSQL 请求会占用工作线程。
- `core/config.py` 同时承载应用、LLM、RAG、Redis、PostgreSQL、Mall、Embedding 和 Milvus 配置，职责过多。
- RAG 配置类已改名为 `RetrievalConfig`，调用方和测试仍使用 `RagConfig`，导致测试收集失败。
- `MallEcommerceGateway` 在实例创建时读取单个静态 `MALL_AUTH_TOKEN`，无法表达不同登录用户的身份。

因此采用端到端异步方案，并拆分配置包。静态 Mall token 仅保留为显式启用的本地联调回退，不作为生产身份来源。

## 架构

### 配置边界

新增顶层 `app/config/` 包：

- `app.py`：运行环境和网关选择。
- `llm.py`：LLM 参数。
- `rag.py`：切片、检索、Embedding、Milvus 参数。
- `storage.py`：Redis、PostgreSQL 和连接池参数。
- `mall.py`：Mall 服务地址、超时和本地 token 回退策略。
- `__init__.py`：对外导出稳定配置名称。

业务代码只从 `config` 包的公共入口导入。删除 `core/config.py`，避免新旧配置源并存。环境变量仍使用当前名称，保持部署兼容。

`RagConfig` 作为正式检索配置名称，包含 `RETRIEVER`、`SEARCH_LIMIT` 和 `ENABLE_RERANK`，从而修复当前调用契约。配置测试覆盖用户新增的 RAG 环境变量。

### PostgreSQL 异步链路

长期记忆仓储改用 SQLAlchemy `create_async_engine`。SQLAlchemy 引擎自身负责连接池，不再维护独立 `asyncpg.create_pool` 单例，避免两套池的生命周期和参数不一致。

数据库 URL 规范化规则：

- `postgresql://...` 转为 `postgresql+asyncpg://...`。
- `postgresql+psycopg://...` 转为 `postgresql+asyncpg://...`。
- 已是 `postgresql+asyncpg://...` 时保持不变。
- SQLite 测试可使用 `sqlite+aiosqlite://...`，但生产路径只承诺 PostgreSQL。

`UserMemoryRepository` 的 `get` 和 `upsert` 变为 awaitable；聊天路由相应改成 `async def`。应用启动时初始化数据表，关闭时释放异步引擎。初始化失败不得静默切换到内存仓储：配置了数据库却不可用时应明确报错，防止生产数据悄然丢失。未配置数据库时仍可使用内存仓储进行本地运行。

### Mall JWT 数据流

Mall Portal 的登录入口为 `POST /sso/login`。成功响应的 `data.token` 是裸 JWT，`data.tokenHead` 通常为 `Bearer `。前端保存裸 token，调用 Agent 时发送：

```http
Authorization: Bearer <data.token>
```

Agent 的 `/api/chat` 通过 FastAPI `Header` 读取该请求头，只接受 Bearer 格式。它不使用 Mall 用户密码登录、不在 Agent 中签发用户 JWT，也不依赖共享 JWT 密钥解析身份。请求级 token 被传给 Mall 网关，再由网关原样设置到每次 Mall HTTP 请求中。

用户身份以 Mall 返回的受保护用户信息为准。客户端提交的 `user_id` 不能单独作为授权依据；本次改造先确保 token 透传和订单归属校验，后续可调用 `/sso/info` 将 JWT 对应会员 ID 与请求体身份绑定。

未提供 JWT 时：

- 若显式配置本地 `MALL_AUTH_TOKEN`，仅用于开发联调回退。
- 否则调用需要 Mall 鉴权的数据接口时返回清晰的未认证错误。

### HTTP 与资源生命周期

Mall 网关改用 `httpx.AsyncClient`，业务网关协议及调用它的 Agent 工具链改为异步。客户端按应用生命周期复用并在关闭时释放，避免每个请求重复建连。

请求级 JWT 不写入共享客户端默认 headers，防止并发用户之间串 token；它只作为当前请求调用参数设置。

## 错误处理

- 配置值类型错误在导入/启动阶段给出包含变量名的明确异常。
- PostgreSQL 配置存在但初始化失败时启动失败，不静默降级。
- Mall 返回 401/403 时映射成可识别的认证或权限错误，不伪装成“订单不存在”。
- Bearer 请求头格式不合法时，Agent API 返回 401。
- RAG 的默认检索模式保持 `keyword`，未配置 Milvus 时不强制连接 Milvus。

## 测试策略

按 TDD 顺序实施：

1. 配置包导出、RAG 环境变量和数据库 URL 规范化测试。
2. 异步长期记忆仓储协议和数据库操作测试。
3. `/api/chat` Bearer token 读取及请求级网关注入测试。
4. Mall 网关异步请求、JWT 透传、401/403 映射测试。
5. 现有 Agent、RAG、API、评估测试全量回归。

测试不依赖真实 Mall、PostgreSQL 或 Milvus。真实服务连通性作为部署后的独立 smoke test，不把外部服务可用性混入单元测试。

## 范围外事项

- 不修改 Mall Java 服务签发 JWT 的实现。
- 不实现刷新 token、Cookie 会话或 OAuth2。
- 不在本轮启用真实售后写操作。
- 不重构与配置、数据库异步化、JWT 透传无关的 Agent 业务逻辑。
- 完成度评估是实施与测试后的交付报告，不作为运行时代码模块。
