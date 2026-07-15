# 简约专业客服页面与 Mall 登录态桥接设计

## 目标

将现有演示页改造成 A 方案“聚焦式客服工作台”，并解决用户已在 Mall 前台登录、Agent 页面仍显示登录表单或停留在“正在登录”的问题。页面继续使用原生 HTML、CSS 和 JavaScript，不引入新的前端框架。

## 已确认的视觉方向

- 页面使用低饱和蓝灰色、白色卡片和克制阴影，强调可信、专业和清晰。
- 顶部显示品牌、服务范围和 Mall 连接状态；对话区域是唯一视觉中心。
- 常用问题使用轻量快捷按钮，输入框固定在对话卡片底部。
- 调试信息默认隐藏在可折叠抽屉中，不占用主布局。
- 桌面端限制内容宽度，移动端改为单列并保证输入区可操作。

## 登录态边界

Mall 前台与 Agent 页面位于不同 Origin 时，Agent JavaScript 不能直接读取 Mall 前台的 `localStorage`、`sessionStorage` 或 Cookie。页面不得根据外观猜测登录成功，也不得通过 URL 传递 JWT。

采用登录态桥接：

1. Mall 前台从自身认证存储读取会员 JWT。
2. Mall 前台携带 `Authorization: Bearer <token>` 请求 Agent 的 `POST /api/auth/session`。
3. Agent 使用该 JWT 调用 Mall `/sso/info` 验证会员身份。
4. 验证成功后，Agent 只把 JWT 写入自己域下的 HttpOnly Cookie；响应仅返回脱敏后的会员信息。
5. Agent 页面启动时调用 `GET /api/auth/status`。后端通过 HttpOnly Cookie 再次调用 `/sso/info`，返回 `authenticated`、`user_id` 和 `username`，不返回 JWT。
6. 聊天请求继续使用 Agent 域下的 HttpOnly Cookie，JWT 不进入页面状态、URL、日志或聊天内容。

如果用户直接打开 Agent 页面且尚未完成桥接，页面显示“前往 Mall 登录”，不再显示重复的账号密码输入框。Mall 前台后续应在进入智能客服入口前执行一次会话桥接。

## 页面状态机

页面只有以下认证状态：

- `checking`：页面加载后正在调用 `/api/auth/status`，顶部显示中性加载状态，聊天输入暂时禁用。
- `authenticated`：顶部显示绿色“Mall 已连接”和会员名称，隐藏登录提示，启用聊天。
- `anonymous`：显示简洁的未登录说明和“前往 Mall 登录”按钮，禁用聊天。
- `error`：显示可重试提示，不把网络故障误报为未登录。

所有认证和聊天请求使用 `AbortController` 设置超时。无论成功、失败或超时，都必须在 `finally` 中恢复按钮、状态文字和输入控件，避免永久停留在“正在登录”。

## 后端接口

### `POST /api/auth/session`

- 只接受 Bearer Authorization Header。
- 使用请求级 `MallEcommerceGateway` 调用 `/sso/info` 验证令牌。
- 成功后设置 `mall_access_token` HttpOnly Cookie，建议 `SameSite=Lax`；生产 HTTPS 开启 `Secure`。
- 返回 `{authenticated: true, user: {user_id, username}}`。
- 401、403、超时和 Mall 5xx 使用现有领域错误映射；错误响应不得包含 JWT。

### `GET /api/auth/status`

- 读取 Agent 域下的 HttpOnly Cookie。
- Cookie 有效时返回脱敏会员信息；无 Cookie或 Mall 返回 401 时返回 `{authenticated: false}`。
- Mall 服务超时或 5xx 返回 503，前端进入 `error`，不得将其显示为“未登录”。

## Mall 前台集成

在实际持有会员 JWT 的 Mall 前台增加一个进入智能客服的动作：先调用会话桥接接口，再打开 Agent 页面。跨 Origin 本地开发需要 Agent 配置精确的 Portal Origin CORS，并允许 credentials；生产环境只允许实际 Portal 域名。

管理员 Token 与会员 Token 不可混用。`mall-admin-web` 的管理员登录态不能用于调用会员 `/sso/info` 或查询会员订单。

## 前端组件

- `app/web/index.html`：品牌头部、连接状态、对话卡片、快捷问题、未登录提示、折叠调试区。
- `app/web/styles.css`：设计令牌、响应式布局、消息气泡、状态标签、加载和禁用状态。
- `app/web/app.js`：认证状态机、状态检查、快捷问题、SSE 消费、超时与错误恢复。

不使用内联事件，不在 DOM、控制台或调试面板保存 JWT。

## 错误处理

- 401：显示未登录状态和前往 Mall 按钮。
- 403：显示当前账号无权访问。
- 超时或 5xx：显示“服务暂时不可用”和重试按钮。
- SSE 中断：保留已接收文本，在消息气泡中显示可重试状态。
- 重复提交：发送期间禁用输入和发送按钮，结束后恢复。

## 测试与验收

- 后端单元测试覆盖会话桥接成功、缺少 Header、无效 JWT、状态检查成功与匿名状态。
- 前端静态测试确认旧账号密码表单已删除，存在认证状态、快捷按钮和可折叠调试区。
- JavaScript 测试或可测试函数覆盖请求超时后状态恢复、401 状态切换和 SSE 错误处理。
- 手工验收：从 Mall 前台进入 Agent 后直接显示“Mall 已连接”；直接无凭据打开 Agent 时不显示账号密码框；断开 Mall 服务时不会一直显示“正在登录”。

## 范围外

- 不改造 Mall 的账号体系或 JWT 格式。
- 不允许管理员身份代替会员身份查询订单。
- 不在本次设计中引入 Vue、React 或新的 UI 组件库。
