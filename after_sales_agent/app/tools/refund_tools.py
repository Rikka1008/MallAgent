from agent.context import AgentRuntimeContext
from langchain.tools import ToolRuntime
from langchain_core.tools import tool
from tools.runtime import get_runtime_context


@tool
async def get_refund_status(
    order_id: str | None,
    after_sales_id: str | None,
    runtime: ToolRuntime[AgentRuntimeContext],
) -> dict:
    """查询退款状态。

    支持用订单号或售后单号查询，满足用户自然表达中“查订单退款”和“查售后单”的两种习惯。
    """

    if not order_id and not after_sales_id:
        return {"found": False, "message": "请提供订单号或售后单号。", "refund": None}

    context = get_runtime_context(runtime)
    refund = await context.gateway.get_refund(
        order_id=order_id, after_sales_id=after_sales_id, user_id=context.user_id
    )
    if refund is None:
        return {"found": False, "message": "暂未查到退款记录。", "refund": None}

    return {"found": True, "message": "退款查询成功。", "refund": refund.model_dump()}
