# Query 直接改写与会员会话状态 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用中文提示词约束商品与政策检索 Query 直接改写，并提供可退出、可切换账号的 Mall 会员状态。

**Architecture:** Query 改写只发生在主智能体委派描述和知识检索子智能体的工具参数中，不增加模型调用。会员退出由后端删除 HttpOnly Cookie，前端状态机根据 `/api/auth/status` 和 `/api/auth/logout` 控制用户名、退出按钮与对话可用性。

**Tech Stack:** Python 3.13、FastAPI、Deep Agents、pytest、原生 JavaScript、HTML/CSS。

## Global Constraints

- 先实现提示词 Query 改写，再实现会员退出与状态 UI。
- 新增提示词和代码注释使用中文。
- 不实现独立 Query Rewriter、额外模型调用或 HyDE。
- 不改写订单号、SKU、金额、时间和售后单号等精确实体。
- 不恢复旧用户名密码登录表单。
- 当前目录没有有效 Git 仓库，不执行提交、分支或工作树操作。

---

### Task 1: 提示词内直接改写 Query

**Files:**
- Modify: `after_sales_agent/app/agent/main_agent.py`
- Modify: `after_sales_agent/app/agent/deep_subagents.py`
- Test: `after_sales_agent/tests/unit/test_main_agent.py`
- Test: `after_sales_agent/tests/unit/test_deep_subagents.py`

**Interfaces:**
- Consumes: 主智能体最近对话和当前用户问题。
- Produces: `product_agent` 与 `policy_agent` 调用检索工具时使用的独立 Query。

- [ ] **Step 1: 写失败测试**

```python
def test_main_prompt_requires_context_complete_retrieval_tasks():
    assert "消除指代" in MAIN_SYSTEM_PROMPT
    assert "保留订单号、SKU、金额和时间" in MAIN_SYSTEM_PROMPT

def test_knowledge_subagents_rewrite_query_before_search(monkeypatch):
    agents = build_subagents_with_fake_create_agent(monkeypatch)
    for index in (0, 5):
        prompt = agents[index]["runnable"]["system_prompt"]
        assert "直接改写" in prompt
        assert "只作为工具的 `query` 参数" in prompt
        assert "指代无法唯一确定" in prompt
```

- [ ] **Step 2: 确认测试因规则缺失而失败**

Run: `python -m pytest tests/unit/test_main_agent.py tests/unit/test_deep_subagents.py -q`

Expected: FAIL，提示词中尚无直接改写规则。

- [ ] **Step 3: 增加中文提示词规则**

主智能体委派规则增加：商品和政策检索任务必须携带必要最近对话，消除指代，保留精确实体，不得补造事实。

在 `deep_subagents.py` 增加共享常量：

```python
_QUERY_REWRITE_RULES = """
调用知识检索工具前，先把用户问题直接改写为独立、明确、适合检索的书面 Query。
结合任务中的最近对话消除“这个、那个、上次那双”等指代，修正常见错别字；保留核心意图、限制条件、订单号、SKU、金额、时间和售后单号。
不得增加对话中不存在的品牌、商品、政策或结论。指代无法唯一确定时先列出缺失信息，不要调用工具猜测。
改写结果只作为工具的 `query` 参数，不要展示内部改写过程。
"""
```

只将该规则加入 `product_agent` 和 `policy_agent`。

- [ ] **Step 4: 运行提示词聚焦测试**

Run: `python -m pytest tests/unit/test_main_agent.py tests/unit/test_deep_subagents.py -q`

Expected: PASS。

### Task 2: 后端会员退出与无效 Cookie 清理

**Files:**
- Modify: `after_sales_agent/app/api/routes.py`
- Test: `after_sales_agent/tests/unit/test_auth_session.py`

**Interfaces:**
- Produces: `POST /api/auth/logout -> AuthSessionResponse(authenticated=False)`。
- Modifies: `GET /api/auth/status` 在 `AuthenticationError` 时删除 `mall_access_token`。

- [ ] **Step 1: 写失败测试**

```python
def test_logout_clears_http_only_member_cookie():
    response = client.post("/api/auth/logout")
    assert response.status_code == 200
    assert response.json() == {"authenticated": False, "user": None}
    assert "mall_access_token=" in response.headers["set-cookie"]
    assert "Max-Age=0" in response.headers["set-cookie"]

def test_invalid_cookie_is_cleared_during_status_check():
    response = client.get("/api/auth/status", cookies={"mall_access_token": "expired"})
    assert response.json()["authenticated"] is False
    assert "Max-Age=0" in response.headers["set-cookie"]
```

- [ ] **Step 2: 确认测试因路由和清理缺失而失败**

Run: `python -m pytest tests/unit/test_auth_session.py -q`

Expected: FAIL，logout 为 404，失效状态未发送清除 Cookie。

- [ ] **Step 3: 实现统一 Cookie 清理**

```python
def _clear_auth_cookie(response: Response) -> None:
    response.delete_cookie(
        key="mall_access_token",
        path="/",
        secure=MallConfig.COOKIE_SECURE,
        httponly=True,
        samesite="lax",
    )

@router.post("/api/auth/logout", response_model=AuthSessionResponse)
def logout(response: Response) -> AuthSessionResponse:
    _clear_auth_cookie(response)
    return AuthSessionResponse(authenticated=False)
```

为 `get_auth_status` 增加 `response: Response`，捕获 `AuthenticationError` 后调用 `_clear_auth_cookie`。

- [ ] **Step 4: 运行认证测试**

Run: `python -m pytest tests/unit/test_auth_session.py tests/unit/test_gateway_auth.py -q`

Expected: PASS。

### Task 3: 前端会员状态与退出按钮

**Files:**
- Modify: `after_sales_agent/app/web/index.html`
- Modify: `after_sales_agent/app/web/app.js`
- Modify: `after_sales_agent/app/web/styles.css`
- Test: `after_sales_agent/tests/unit/test_web_copy.py`

**Interfaces:**
- Consumes: `/api/auth/status` 与 `/api/auth/logout`。
- Produces: 已登录用户名、退出按钮、退出后的 anonymous 状态。

- [ ] **Step 1: 写失败的静态行为测试**

```python
assert 'id="logout-button"' in html
assert 'fetchWithTimeout("/api/auth/logout"' in script
assert 'method: "POST"' in script
assert 'logoutButton.addEventListener("click"' in script
assert 'setAuthState("anonymous")' in script
```

- [ ] **Step 2: 确认测试因 UI 缺失而失败**

Run: `python -m pytest tests/unit/test_web_copy.py -q`

Expected: FAIL，页面没有退出按钮和 logout 请求。

- [ ] **Step 3: 实现状态 UI**

在顶栏认证区域增加默认隐藏的 `退出`按钮；authenticated 状态显示，其他状态隐藏。点击后禁用按钮并 POST logout，成功调用 `setAuthState("anonymous")`，失败保留认证状态并在状态区域显示错误。

- [ ] **Step 4: 运行页面测试与 JavaScript 语法检查**

Run: `python -m pytest tests/unit/test_web_copy.py -q`

Run: `node --check app/web/app.js`

Expected: 全部 PASS。

### Task 4: 完整验证和服务重启

**Files:**
- Verify: `after_sales_agent/app/**`
- Verify: `after_sales_agent/tests/unit/**`

**Interfaces:**
- Consumes: Tasks 1～3。
- Produces: 可运行的 Query 改写提示词与会员状态闭环。

- [ ] **Step 1: 运行 Ruff**

Run: `python -m ruff check app tests/unit`

Expected: `All checks passed!`

- [ ] **Step 2: 运行全量单测**

Run: `python -m pytest tests/unit -q`

Expected: 0 failed。

- [ ] **Step 3: 重启 Uvicorn 并验证运行状态**

Run: `python -m uvicorn app.main:app --host 127.0.0.1 --port 8010`

Verify: `/health` 为 `ok`，首页包含 `logout-button`，无 Cookie 请求 `/api/auth/status` 返回 anonymous。
