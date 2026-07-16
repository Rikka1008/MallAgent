from agent.context import AgentRuntimeContext
from langchain.tools import ToolRuntime
from langchain_core.tools import tool
from tools.runtime import get_runtime_context


_STATUS_ORDER = {
    "退款处理中": 0,
    "售后处理中": 1,
    "退货中": 2,
    "换货处理中": 3,
    "待付款": 10,
    "待发货": 11,
    "已发货": 12,
    "已完成": 13,
    "已关闭": 14,
    "无效订单": 15,
}


@tool
async def list_orders(
    runtime: ToolRuntime[AgentRuntimeContext],
    status: int = -1,
    limit: int = 10,
) -> dict:
    """查询当前登录用户最近的订单列表。

    status：-1 全部、0 待付款、1 待发货、2 已发货、3 已完成、4 已关闭；
    limit 默认 10，最大 20。用户身份由服务端会话提供。
    """

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
            "rendered_markdown": "",
        }
    rendered_markdown = _render_orders_markdown(orders)
    return {
        "found": True,
        "message": rendered_markdown,
        "count": len(orders),
        "orders": [order.model_dump() for order in orders],
        "rendered_markdown": rendered_markdown,
    }


def _render_orders_markdown(orders: list) -> str:
    """确定性渲染完整订单列表，避免生成式回复遗漏某个状态分组的明细。"""

    groups: dict[str, list] = {}
    for order in orders:
        groups.setdefault(order.status, []).append(order)

    lines = [f"以下是您的最近订单（共 {len(orders)} 笔）："]
    sorted_groups = sorted(
        groups.items(), key=lambda item: (_STATUS_ORDER.get(item[0], 99), item[0])
    )
    for status, status_orders in sorted_groups:
        lines.extend(
            [
                "",
                f"**{status}（{len(status_orders)}笔）**",
                "| 订单号 | 商品 | 金额 | 订单状态 | 售后状态 |",
                "|---|---|---:|---|---|",
            ]
        )
        for order in status_orders:
            product_text = " + ".join(
                f"{_escape_table_text(item.product_name)} ×{item.quantity}"
                for item in order.items
            ) or "商品信息未提供"
            total = sum(item.price * item.quantity for item in order.items)
            lines.append(
                "| {order_id} | {products} | {amount} | {order_status} | {after_sales_status} |".format(
                    order_id=_escape_table_text(order.order_id),
                    products=product_text,
                    amount=_format_amount(total),
                    order_status=_escape_table_text(order.order_status or order.status),
                    after_sales_status=_escape_table_text(order.after_sales_status or "-"),
                )
            )
    return "\n".join(lines)


def _escape_table_text(value: str) -> str:
    return str(value).replace("|", "\\|").replace("\n", " ")


def _format_amount(amount: float) -> str:
    formatted = f"{amount:,.2f}"
    if formatted.endswith(".00"):
        formatted = formatted[:-3]
    return f"¥{formatted}"


@tool
async def get_order(
    order_id: str | None,
    runtime: ToolRuntime[AgentRuntimeContext],
) -> dict:
    """查询订单信息。

    输入订单号并使用服务端会话身份查询，返回结构化字典；查不到时不抛异常，便于 Agent 继续追问或转人工。
    """

    if not order_id:
        return {"found": False, "message": "请提供订单号。", "order": None}

    context = get_runtime_context(runtime)
    order = await context.gateway.get_order(order_id=order_id, user_id=context.user_id)
    if order is None:
        return {"found": False, "message": "未找到该订单，或该订单不属于当前用户。", "order": None}

    return {"found": True, "message": "订单查询成功。", "order": order.model_dump()}
