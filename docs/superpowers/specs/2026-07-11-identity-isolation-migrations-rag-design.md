# 双入口身份隔离、数据库迁移与 RAG 验证设计

## 目标

把售后 Agent 的会员身份从客户端请求体中移除，改为以 Mall Portal JWT 调用 `/sso/info` 得到的会员身份为准；同时为 PostgreSQL 长期记忆引入 Alembic 迁移、验证 RAG 实际服务，并为现有后台前端提供与会员入口隔离的客服工作台。

## 身份边界

系统保留两类互不混用的身份：

- **会员入口**：Mall Portal `/sso/login` 签发的会员 JWT。Agent 的会员聊天接口只接受该 JWT，并通过 Portal `/sso/info` 解析会员编号和用户名。请求体不再接受或信任 `user_id`。
- **后台入口**：`mall-admin-web` 的 `/admin/login` 管理员 JWT。后台工作台只调用 Agent 的管理员接口；管理员 JWT 不允许访问会员聊天接口，也不能作为订单归属判断依据。

会员聊天接口为 `POST /api/chat`，请求体只包含 `session_id` 与 `message`。Agent 通过依赖项读取 Authorization Header，调用 Portal `/sso/info`，将解析出的稳定会员 ID 写入会话、长期记忆和 Mall 查询。

管理员工作台初期提供只读“查看 Agent 会话/转人工记录”入口；不读取会员对话内容之外的数据，也不代替会员发起聊天。管理员接口在本轮只建立前端 API client、路由和页面骨架，后端管理员鉴权端点以明确的待接入接口契约表示，避免伪造安全能力。

## Portal 身份解析

`MallEcommerceGateway` 新增 `get_current_member()`，使用当前请求 JWT 调用 `GET {MALL_PORTAL_BASE_URL}/sso/info`。将 Mall 返回的 `id` 作为内部 `user_id`；若 API 只提供用户名，则明确拒绝会员聊天而不是回退到客户端输入。

Authorization Header 缺失、格式错误、Portal 返回 401/403、或用户信息中缺少稳定 ID 时，会员聊天统一返回 401/403，不会执行查询、写入记忆或创建会话状态。成功解析的 JWT 仍按请求级透传给后续 Mall 调用，永不写入日志、Redis、PostgreSQL 或共享 HTTP 客户端。

## 前端集成

当前工作区只包含 `mall-admin-web`，没有 Portal 前端源码，因此交付两个独立产物：

1. `after_sales_agent/app/web` 的本地会员演示页移除固定 `U100`，要求由同源 Portal 容器或显式接入适配器提供 JWT；它不尝试跨域读取 Mall 浏览器存储。
2. `mall-admin-web` 新增售后 Agent 页面和 API 模块，复用其 Pinia 管理员 token 与 Axios 拦截器，访问管理员工作台 API。页面明确标注“客服后台”，不调用会员聊天接口。

Portal 的实际 Vue/React 项目到位后，只需复用其现有 JWT store，在 Agent 请求上添加 Authorization Header；接口契约文档和可复制 API helper 将随本轮交付。

## PostgreSQL 迁移

引入 Alembic，并将当前 `user_memories` 表从运行时 `metadata.create_all()` 改为版本化迁移。首个 revision 创建：`user_id` 主键、最近订单、意图、摘要和带时区的更新时间。应用启动不再建表；在未运行迁移时，带数据库配置的环境启动失败并给出迁移命令。

迁移在真实 PostgreSQL 目标库上只能由显式命令 `alembic upgrade head` 执行，Agent API 不会自行修改 schema。测试使用临时 SQLite 异步数据库或 Alembic SQL 生成验证，不连接生产数据库。

## RAG 验证

新增 `scripts/smoke_test_services.py`：

- 验证 PostgreSQL 连接与当前 Alembic revision；
- 验证 Redis ping；
- 验证 Milvus 连接、collection 存在与维度；
- 运行指定 RAG 测试查询并输出命中文档元数据，不输出敏感 token；
- 验证 Mall Portal 的 `/sso/info` 仅在显式提供短期测试 JWT 时执行。

默认 smoke test 是只读；RAG 入库保留独立的写命令，必须传入 `--write-rag` 才能执行。真实环境测试由用户 `.env` 中的服务地址决定；连接失败将报告组件与原因，不自动写入或重置远端数据。

## 错误处理和审计

- 会员接口拒绝管理员 token 的方式是 Portal `/sso/info` 认证失败；不尝试解析 token 签名。
- 管理员接口与会员接口使用独立路由前缀、依赖和 OpenAPI 标签。
- 审计仅记录认证结果、Mall 会员 ID、操作类别和请求关联 ID；不记录 JWT、密码或完整对话内容。
- 迁移失败阻止数据库模式依赖功能启动；开发环境可显式不配置 DATABASE_URL 使用内存仓储。

## 测试

1. 会员 JWT 成功绑定身份、缺失 ID、401、403、请求体伪造 user_id 的 API 测试。
2. Mall `/sso/info` 映射和 Bearer 透传单元测试。
3. Alembic upgrade/downgrade 与异步仓储契约测试。
4. 管理员前端 API 模块的类型检查与构建。
5. RAG smoke 脚本的 fake-service 单元测试；只有显式执行时才连真实服务。

## 范围外

- 不将管理员 JWT 转换、交换或冒充会员 JWT。
- 不实现真实售后申请写操作。
- 不尝试从不同域的 Portal 页面读取 localStorage/sessionStorage。
- 没有 Portal 前端源码时，不虚构其页面或登录状态管理实现。
