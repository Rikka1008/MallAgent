# 简约专业客服页面与登录态桥接 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 Agent 演示页重构为聚焦式客服工作台，并通过受验证的 HttpOnly Cookie 桥接 Mall 会员登录态。

**Architecture:** Mall 前台携带会员 Bearer Token 调用 Agent 会话交换接口，Agent 使用 `/sso/info` 验证后写入自身域下的 HttpOnly Cookie。Agent 页面只消费脱敏的认证状态接口，并以 `checking/authenticated/anonymous/error` 状态机控制界面和聊天能力。

**Tech Stack:** FastAPI、httpx、原生 HTML/CSS/JavaScript、pytest、Ruff。

## Global Constraints

- 页面采用已确认的 A“聚焦式客服工作台”方案，不引入 Vue、React 或 UI 组件库。
- JWT 不得进入 URL、DOM、调试输出、普通日志、错误响应或聊天内容。
- 管理员 Token 不得代替会员 Token 调用会员 `/sso/info`。
- 跨 Origin CORS 只允许配置中的 Mall Portal Origin，并启用 credentials。
- 所有新增提示文字和代码注释使用中文。
- 当前仓库没有可用 Git 元数据，执行任务时不创建提交。

---

### Task 1: 会员会话桥接与状态接口

**Files:**
- Modify: `D:/560/MallAgent/after_sales_agent/app/api/routes.py`
- Modify: `D:/560/MallAgent/after_sales_agent/app/api/schemas.py`
- Modify: `D:/560/MallAgent/after_sales_agent/app/config/mall.py`
- Test: `D:/560/MallAgent/after_sales_agent/tests/unit/test_auth_session.py`

**Interfaces:**
- Produces: `POST /api/auth/session`，输入 Bearer Header，输出脱敏会员状态并设置 `mall_access_token` Cookie。
- Produces: `GET /api/auth/status`，输出 `{"authenticated": bool, "user": object | null}`。
- Produces: `MallConfig.COOKIE_SECURE: bool` 和 `MallConfig.COOKIE_MAX_AGE_SECONDS: int`。

- [ ] **Step 1: 编写失败测试**

```python
def test_session_bridge_validates_member_and_sets_http_only_cookie(client, member_gateway):
    response = client.post(
        "/api/auth/session",
        headers={"Authorization": "Bearer member-token"},
    )
    assert response.json() == {
        "authenticated": True,
        "user": {"user_id": "U100", "username": "test"},
    }
    assert "mall_access_token=member-token" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]


def test_auth_status_returns_anonymous_without_cookie(client):
    assert client.get("/api/auth/status").json() == {
        "authenticated": False,
        "user": None,
    }
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m pytest tests/unit/test_auth_session.py -q`

Expected: FAIL，两个认证状态路由尚不存在。

- [ ] **Step 3: 实现响应模型和接口**

在 `schemas.py` 增加：

```python
class AuthenticatedUser(BaseModel):
    user_id: str
    username: str


class AuthSessionResponse(BaseModel):
    authenticated: bool
    user: AuthenticatedUser | None = None
```

在 `routes.py` 中，会话桥接必须校验 Bearer Header、调用 `gateway.get_current_member()`，并只把去掉 `Bearer ` 前缀后的原始 token 写入 Cookie。状态接口无 Cookie 时直接返回匿名；Cookie 无效时捕获 `AuthenticationError` 并返回匿名；Mall 超时或 5xx 保持服务错误。

- [ ] **Step 4: 运行认证测试**

Run: `python -m pytest tests/unit/test_auth_session.py tests/unit/test_gateway_auth.py -q`

Expected: PASS。

### Task 2: 精确 CORS 与 Mall 前台桥接文档

**Files:**
- Modify: `D:/560/MallAgent/after_sales_agent/app/main.py`
- Modify: `D:/560/MallAgent/after_sales_agent/app/config/mall.py`
- Modify: `D:/560/MallAgent/after_sales_agent/.env.example`
- Modify: `D:/560/MallAgent/after_sales_agent/docs/mall-portal-agent-integration.md`
- Test: `D:/560/MallAgent/after_sales_agent/tests/unit/test_cors_config.py`

**Interfaces:**
- Produces: `MallConfig.PORTAL_ORIGINS: list[str]`，默认仅包含 `http://localhost:8085`。
- Consumes: `POST /api/auth/session`。

- [ ] **Step 1: 编写 CORS 失败测试**

```python
def test_cors_allows_configured_portal_with_credentials():
    response = client.options(
        "/api/auth/session",
        headers={
            "Origin": "http://localhost:8085",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert response.headers["access-control-allow-origin"] == "http://localhost:8085"
    assert response.headers["access-control-allow-credentials"] == "true"
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m pytest tests/unit/test_cors_config.py -q`

Expected: FAIL，应用尚未安装 CORS 中间件。

- [ ] **Step 3: 增加精确 CORS 和桥接示例**

`main.py` 使用：

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=MallConfig.PORTAL_ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)
```

文档提供 Mall 会员前台入口函数：先用会员 JWT 请求 `/api/auth/session`，成功后再打开 Agent 页面。明确说明 `mall-admin-web` 的管理员 token 不适用。

- [ ] **Step 4: 运行 CORS 测试**

Run: `python -m pytest tests/unit/test_cors_config.py tests/unit/test_config.py -q`

Expected: PASS。

### Task 3: 聚焦式客服工作台与认证状态机

**Files:**
- Modify: `D:/560/MallAgent/after_sales_agent/app/web/index.html`
- Modify: `D:/560/MallAgent/after_sales_agent/app/web/styles.css`
- Modify: `D:/560/MallAgent/after_sales_agent/app/web/app.js`
- Modify: `D:/560/MallAgent/after_sales_agent/tests/unit/test_web_copy.py`

**Interfaces:**
- Consumes: `GET /api/auth/status` 和 `POST /api/chat/stream`。
- Produces: `setAuthState(state, user?)`、`checkAuthStatus()`、`fetchWithTimeout(url, options, timeoutMs)`。

- [ ] **Step 1: 更新静态失败测试**

```python
def test_web_uses_auth_status_instead_of_password_form():
    html = WEB_INDEX.read_text(encoding="utf-8")
    script = WEB_APP.read_text(encoding="utf-8")
    assert 'id="login-form"' not in html
    assert 'id="auth-status"' in html
    assert 'id="quick-actions"' in html
    assert "details" in html
    assert 'fetchWithTimeout("/api/auth/status"' in script
```

- [ ] **Step 2: 运行测试并确认失败**

Run: `python -m pytest tests/unit/test_web_copy.py -q`

Expected: FAIL，旧页面仍包含账号密码表单。

- [ ] **Step 3: 实现页面和状态机**

`index.html` 按 A 方案组织为顶部品牌栏、认证状态、居中聊天卡片、快捷问题、输入区和默认折叠的调试详情。`app.js` 启动时进入 `checking` 并调用状态接口；401 切换 `anonymous`，成功切换 `authenticated`，超时和 5xx 切换 `error`。所有按钮状态必须在 `finally` 中恢复。

`fetchWithTimeout` 的核心实现：

```javascript
async function fetchWithTimeout(url, options = {}, timeoutMs = 8000) {
  const controller = new AbortController();
  const timer = window.setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    window.clearTimeout(timer);
  }
}
```

- [ ] **Step 4: 运行页面测试**

Run: `python -m pytest tests/unit/test_web_copy.py -q`

Expected: PASS。

### Task 4: 回归验证与浏览器验收

**Files:**
- Modify if required: `D:/560/MallAgent/after_sales_agent/tests/unit/test_auth_session.py`
- Modify if required: `D:/560/MallAgent/after_sales_agent/tests/unit/test_web_copy.py`

**Interfaces:**
- Consumes: Task 1 至 Task 3 的接口和页面。
- Produces: 可运行、可回归的最终页面。

- [ ] **Step 1: 运行专项测试和静态检查**

Run: `python -m pytest tests/unit/test_auth_session.py tests/unit/test_cors_config.py tests/unit/test_web_copy.py -q`

Expected: PASS。

Run: `python -m ruff check app tests/unit`

Expected: `All checks passed!`

- [ ] **Step 2: 运行全部单元测试**

Run: `python -m pytest tests/unit -q`

Expected: 所有测试通过；仅允许现有第三方弃用警告。

- [ ] **Step 3: 浏览器验收**

检查桌面和窄屏布局，并验证：已桥接会话显示“Mall 已连接”；无 Cookie 显示“前往 Mall 登录”；Mall 服务错误显示可重试状态；发送期间输入禁用且完成后恢复；调试详情默认折叠。
