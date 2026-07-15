from agent.context import AgentRuntimeContext
from langchain.tools import ToolRuntime
from langchain_core.tools import tool
from tools.runtime import get_runtime_context


@tool
async def get_logistics(
    order_id: str | None,
    tracking_no: str | None,
    runtime: ToolRuntime[AgentRuntimeContext],
) -> dict:
    """查询物流信息。

    物流可能通过订单号或运单号查询；两个参数都为空时，直接返回缺参提示。
    """

    if not order_id and not tracking_no:
        return {"found": False, "message": "请提供订单号或运单号。", "logistics": None}

    context = get_runtime_context(runtime)
    logistics = await context.gateway.get_logistics(
        order_id=order_id, tracking_no=tracking_no, user_id=context.user_id
    )
    if logistics is None:
        return {"found": False, "message": "暂未查到物流信息。", "logistics": None}

    return {"found": True, "message": "物流查询成功。", "logistics": logistics.model_dump()}
