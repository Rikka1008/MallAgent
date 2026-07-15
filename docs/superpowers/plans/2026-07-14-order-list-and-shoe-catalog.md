# 用户订单列表与鞋类商品知识库 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 让订单子智能体能够列出当前登录用户的真实 Mall 订单，并让商品推荐子智能体从鞋类演示知识文档中检索商品。

**Architecture:** 在现有 `EcommerceGateway` 防腐层增加分页订单列表契约，由 `MallEcommerceGateway` 统一转换 Mall 响应；LangChain 只读工具从 `ToolRuntime` 获取用户身份。鞋类商品以单个 Markdown 目录进入现有 products 加载、切片和 Milvus 检索链路。

**Tech Stack:** Python 3.13、FastAPI、Pydantic、LangChain tools、Deep Agents、pytest、Markdown、Milvus/BGE-M3。

## Global Constraints

- 新增提示词与代码注释使用中文。
- 不接收客户端或模型提供的 `user_id`，只使用运行时认证身份。
- `list_orders` 仅只读，默认 10 条，最大 20 条。
- 演示商品不修改 Mall 数据库，不声明真实库存或可下单状态。
- 当前目录没有有效 Git 仓库，因此不执行提交、分支或工作树操作。

---

### Task 1: 扩展订单列表网关契约

**Files:**
- Modify: `after_sales_agent/app/adapters/ecommerce_gateway.py`
- Modify: `after_sales_agent/app/adapters/mall_gateway.py`
- Modify: `after_sales_agent/tests/fakes.py`
- Test: `after_sales_agent/tests/unit/test_mall_gateway.py`
- Test: `after_sales_agent/tests/unit/test_ecommerce_gateway_protocol.py`

**Interfaces:**
- Consumes: Mall 会员接口 `GET /order/list?status=-1&pageNum=1&pageSize=10`。
- Produces: `EcommerceGateway.list_orders(user_id: str, status: int = -1, page_num: int = 1, page_size: int = 10) -> list[Order]`。

- [ ] **Step 1: 写失败的 Mall 网关测试**

```python
async def test_list_orders_uses_member_portal_and_maps_recent_orders():
    client = FakeMallClient()
    gateway = MallEcommerceGateway(
        portal_base_url="http://mall-portal",
        auth_header="Bearer member-token",
        http_client=client,
    )

    orders = await gateway.list_orders("U100", status=-1, page_num=1, page_size=10)

    assert [order.order_id for order in orders] == ["ORD1001"]
    assert orders[0].user_id == "U100"
    assert ("GET", "http://mall-portal/order/list", {
        "status": -1,
        "pageNum": 1,
        "pageSize": 10,
    }, None) in client.requests
```

- [ ] **Step 2: 运行测试并确认因方法缺失而失败**

Run: `python -m pytest tests/unit/test_mall_gateway.py::test_list_orders_uses_member_portal_and_maps_recent_orders tests/unit/test_ecommerce_gateway_protocol.py -q`

Expected: FAIL，`MallEcommerceGateway` 尚无 `list_orders`，协议检查也不再满足新增契约。

- [ ] **Step 3: 实现契约、适配器与测试网关**

```python
# adapters/ecommerce_gateway.py
async def list_orders(
    self,
    user_id: str,
    status: int = -1,
    page_num: int = 1,
    page_size: int = 10,
) -> list[Order]:
    ...

# adapters/mall_gateway.py
async def list_orders(
    self,
    user_id: str,
    status: int = -1,
    page_num: int = 1,
    page_size: int = 10,
) -> list[Order]:
    safe_page = max(1, page_num)
    safe_size = min(max(1, page_size), 20)
    data = await self._get_common_result(
        f"{self.portal_base_url}/order/list",
        params={"status": status, "pageNum": safe_page, "pageSize": safe_size},
    )
    items = (data or {}).get("list") or []
    return [self._map_order(item, user_id) for item in items]
```

将 `_map_order` 的 `order_id` 改为 `orderSn` 优先、`id` 回退；`orderItemList` 缺失时映射为空列表。给 `FakeEcommerceGateway` 增加同签名方法，按用户过滤并按创建时间倒序截取。

- [ ] **Step 4: 运行网关聚焦测试**

Run: `python -m pytest tests/unit/test_mall_gateway.py tests/unit/test_ecommerce_gateway_protocol.py -q`

Expected: PASS。

### Task 2: 新增 list_orders 工具并交给订单子智能体

**Files:**
- Modify: `after_sales_agent/app/tools/order_tools.py`
- Modify: `after_sales_agent/app/tools/__init__.py`
- Modify: `after_sales_agent/app/agent/deep_subagents.py`
- Test: `after_sales_agent/tests/unit/test_tools.py`
- Test: `after_sales_agent/tests/unit/test_tool_runtime.py`
- Test: `after_sales_agent/tests/unit/test_readonly_tool_registration.py`
- Test: `after_sales_agent/tests/unit/test_deep_subagents.py`

**Interfaces:**
- Consumes: Task 1 的 `EcommerceGateway.list_orders(...)`。
- Produces: LangChain 工具 `list_orders(status: int = -1, limit: int = 10, runtime=...) -> dict`。

- [ ] **Step 1: 写工具与子智能体失败测试**

```python
async def test_list_orders_tool_returns_current_users_orders():
    result = await list_orders.coroutine(status=-1, limit=10, runtime=_runtime())
    assert result["found"] is True
    assert result["count"] == 2
    assert result["orders"][0]["order_id"] == "ORD1002"

def test_order_subagent_has_list_and_detail_tools(monkeypatch):
    monkeypatch.setattr(deep_subagents, "create_agent", lambda **kwargs: kwargs)
    order_agent = deep_subagents.build_subagents(object())[1]
    assert [tool.name for tool in order_agent["runnable"]["tools"]] == [
        "list_orders",
        "get_order",
    ]
    assert "我有哪些订单" in order_agent["runnable"]["system_prompt"]
```

同步更新只读工具注册断言，确认 schema 不包含 `user_id`、`gateway` 或 `runtime`。

- [ ] **Step 2: 运行测试并确认因工具缺失而失败**

Run: `python -m pytest tests/unit/test_tools.py tests/unit/test_tool_runtime.py tests/unit/test_readonly_tool_registration.py tests/unit/test_deep_subagents.py -q`

Expected: FAIL，无法导入或注册 `list_orders`。

- [ ] **Step 3: 实现最小只读工具与中文提示词**

```python
@tool
async def list_orders(
    status: int = -1,
    limit: int = 10,
    runtime: ToolRuntime[AgentRuntimeContext] = None,
) -> dict:
    """查询当前登录用户最近的订单列表。"""
    context = get_runtime_context(runtime)
    safe_limit = min(max(1, limit), 20)
    orders = await context.gateway.list_orders(
        user_id=context.user_id,
        status=status,
        page_num=1,
        page_size=safe_limit,
    )
    if not orders:
        return {
            "found": False,
            "message": "当前账号暂无符合条件的订单。",
            "count": 0,
            "orders": [],
        }
    return {
        "found": True,
        "message": f"已查询到 {len(orders)} 笔订单。",
        "count": len(orders),
        "orders": [order.model_dump() for order in orders],
    }
```

订单子智能体提示词明确：“我有哪些订单、最近订单、待发货订单”调用 `list_orders`；明确订单号调用 `get_order`。`READ_ONLY_TOOLS` 中按 `list_orders`、`get_order`、其他只读工具的稳定顺序注册。

- [ ] **Step 4: 运行工具和子智能体聚焦测试**

Run: `python -m pytest tests/unit/test_tools.py tests/unit/test_tool_runtime.py tests/unit/test_readonly_tool_registration.py tests/unit/test_deep_subagents.py -q`

Expected: PASS。

### Task 3: 创建鞋类商品知识目录并验证加载

**Files:**
- Create: `after_sales_agent/app/data/rag_sources/products/鞋类商品目录.md`
- Modify: `after_sales_agent/tests/unit/test_rag_ingestion.py`

**Interfaces:**
- Consumes: 现有 `load_source_documents`、`split_documents` 与 `search_products`。
- Produces: source category 为 `products` 的鞋类商品知识文档，SKU 为 `SHOE-DEMO-001` 至 `SHOE-DEMO-010`。

- [ ] **Step 1: 写知识文档失败测试**

```python
def test_demo_shoe_catalog_is_loaded_as_product_knowledge():
    source_dir = Path("app/data/rag_sources")
    documents = load_source_documents(source_dir)
    catalog = next(
        document
        for document in documents
        if document.metadata["source_name"] == "鞋类商品目录.md"
    )
    assert catalog.metadata["source_category"] == "products"
    assert catalog.text.count("## ") >= 10
    assert "SHOE-DEMO-001" in catalog.text
    assert "学习测试用演示数据" in catalog.text
```

- [ ] **Step 2: 运行测试并确认因文档不存在而失败**

Run: `python -m pytest tests/unit/test_rag_ingestion.py::test_demo_shoe_catalog_is_loaded_as_product_knowledge -q`

Expected: FAIL，找不到 `鞋类商品目录.md`。

- [ ] **Step 3: 创建十款演示商品文档**

文档开头明确：

```markdown
# 鞋类演示商品目录

> 本文档仅用于智能体学习、知识库检索和商品推荐测试。商品、价格、SKU 与库存均为演示数据，不代表 Mall 真实在售状态。
```

随后建立 `SHOE-DEMO-001` 至 `SHOE-DEMO-010` 十个二级标题，每款包含品类、演示价格、尺码、颜色、材质、卖点、适用人群、场景、尺码建议、选购提醒和检索关键词。品类覆盖轻量跑鞋、缓震跑鞋、休闲板鞋、商务通勤鞋、篮球鞋、低帮徒步鞋、防水户外鞋、健步鞋、训练鞋和儿童运动鞋。

- [ ] **Step 4: 运行知识加载与切片测试**

Run: `python -m pytest tests/unit/test_rag_ingestion.py -q`

Expected: PASS，文档分类为 `products` 且可以被切片。

### Task 4: 整体回归与本地知识库验证

**Files:**
- Verify: `after_sales_agent/app/**`
- Verify: `after_sales_agent/tests/unit/**`
- Verify: `after_sales_agent/app/data/rag_sources/products/鞋类商品目录.md`

**Interfaces:**
- Consumes: Tasks 1～3 的全部产物。
- Produces: 可运行、可测试的订单列表与商品知识检索能力。

- [ ] **Step 1: 运行代码检查**

Run: `python -m ruff check app tests/unit`

Expected: `All checks passed!`

- [ ] **Step 2: 运行全量单元测试**

Run: `python -m pytest tests/unit -q`

Expected: 0 failed。

- [ ] **Step 3: 运行不写 Milvus 的知识库构建验证**

Run: `python scripts/ingest_rag_sources.py --source-dir app/data/rag_sources/products --collection after_sales_products --dry-run`

Expected: `loaded_documents` 至少为 1，`created_chunks` 与 `inserted_vectors` 大于 0。

- [ ] **Step 4: 核对最终约束**

确认 `list_orders` schema 不暴露用户身份；订单子智能体没有写工具；商品推荐提示词仍要求先调用 `search_products`；演示文档没有真实库存承诺；所有新增提示词和注释为中文。
