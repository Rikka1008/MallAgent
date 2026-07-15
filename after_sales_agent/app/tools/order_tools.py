from agent.context import AgentRuntimeContext
from langchain.tools import ToolRuntime
from langchain_core.tools import tool
from tools.runtime import get_runtime_context


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
        }
    return {
        "found": True,
        "message": f"已查询到 {len(orders)} 笔订单。",
        "count": len(orders),
        "orders": [order.model_dump() for order in orders],
    }


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
