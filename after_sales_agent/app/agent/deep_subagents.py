"""Deep Agent 使用的六个受限业务子智能体。"""

from typing import Any

from langchain.agents import create_agent

from tools.after_sales_tools import submit_after_sales_request
from tools.logistics_tools import get_logistics
from tools.order_tools import get_order, list_orders
from tools.policy_tools import search_policy
from tools.product_tools import search_products
from tools.refund_tools import get_refund_status


_COMMON_RULES = """
你只负责收集和整理业务上下文，不要生成面向用户的最终答复。
只依据工具返回的数据工作，不得编造商品、订单、物流、退款、政策或处理结果。
信息缺失时明确列出缺失字段和建议追问项；不要猜测身份信息，也不要输出令牌或内部配置。
"""

_QUERY_REWRITE_RULES = """
调用知识检索工具前，先把用户问题直接改写为独立、明确、适合检索的书面 Query。
结合任务中的最近对话消除“这个、那个、上次那双”等指代，修正常见错别字；保留核心意图、限制条件、订单号、SKU、金额、时间和售后单号。
不得增加对话中不存在的品牌、商品、政策或结论。指代无法唯一确定时先列出缺失信息，不要调用工具猜测。
改写结果只作为工具的 `query` 参数，不要展示内部改写过程。
"""


def create_product_subagent(model: Any) -> dict:
    return _create_subagent(
        model=model,
        name="product_agent",
        description="根据用户需求检索商品，整理可推荐的商品候选和匹配依据。",
        prompt=f"""你是商品推荐信息整理助手。
先调用 `search_products` 检索，再根据真实结果整理商品候选、卖点和适用需求。
检索为空时只说明未找到匹配商品，不得补造推荐。
{_QUERY_REWRITE_RULES}
{_COMMON_RULES}""",
        tools=[search_products],
    )


def create_order_subagent(model: Any) -> dict:
    return _create_subagent(
        model=model,
        name="order_agent",
        description="查询当前登录用户的指定订单，并整理订单状态和商品信息。",
        prompt=f"""你是订单信息整理助手。
用户询问“我有哪些订单”、最近订单或某类状态的订单时调用 `list_orders`；其中 -1 表示全部、0 表示待付款、1 表示待发货、2 表示已发货、3 表示已完成、4 表示已关闭。
用户提供明确订单号并查询详情时调用 `get_order`。
订单归属由服务端校验，不得要求或相信用户在消息中声称的用户编号。
{_COMMON_RULES}""",
        tools=[list_orders, get_order],
    )


def create_logistics_subagent(model: Any) -> dict:
    return _create_subagent(
        model=model,
        name="logistics_agent",
        description="查询当前登录用户的物流状态、承运商和轨迹。",
        prompt=f"""你是物流信息整理助手。
优先使用订单号或运单号调用 `get_logistics`，再整理物流状态和关键轨迹。
没有订单号和运单号时说明需要补充其中一项。
{_COMMON_RULES}""",
        tools=[get_logistics],
    )


def create_refund_subagent(model: Any) -> dict:
    return _create_subagent(
        model=model,
        name="refund_agent",
        description="查询当前登录用户的退款或售后单状态。",
        prompt=f"""你是退款信息整理助手。
使用订单号或售后单号调用 `get_refund_status`，整理退款状态、原价、优惠金额、实付金额和申请退款金额及处理说明。
申请退款金额等于实付金额时，明确说明“退款金额与实付金额一致”；原价与实付金额之间的促销优惠差额不是金额不匹配。
不得将原价与申请退款金额直接比较。只有申请退款金额与实付金额确实不同时，才能提示金额差异。
缺少两个编号时说明需要补充订单号或售后单号。
{_COMMON_RULES}""",
        tools=[get_refund_status],
    )


def create_after_sales_subagent(model: Any) -> dict:
    return _create_subagent(
        model=model,
        name="after_sales_agent",
        description="在用户明确申请后，安全提交退款、退货或换货申请。",
        prompt=f"""你是售后申请信息整理助手。
仅当订单号、商品编号、售后类型和原因完整且经过校验后，才调用 `submit_after_sales_request`。
售后类型仅限退款、退货或换货；工具会执行订单归属、商品归属、政策、幂等和审计校验。
字段不完整、用户意图不明确或工具拒绝时，只整理原因和缺失信息，不得承诺申请成功。
工具成功后只整理售后单号、申请类型、当前状态以及“等待后台审核”；申请提交成功不代表退款到账，不得承诺退款金额或到账结果。
{_COMMON_RULES}""",
        tools=[submit_after_sales_request],
    )


def create_policy_subagent(model: Any) -> dict:
    return _create_subagent(
        model=model,
        name="policy_agent",
        description="检索售后政策，整理与用户问题直接相关的政策依据。",
        prompt=f"""你是售后政策信息整理助手。
先调用 `search_policy` 检索政策依据，再提取与问题直接相关的规则和来源。
没有检索依据时明确说明需要人工确认，不得自行解释政策。
{_QUERY_REWRITE_RULES}
{_COMMON_RULES}""",
        tools=[search_policy],
    )


def build_subagents(model: Any) -> list[dict]:
    """按固定顺序构建主智能体可委派的专业子智能体。"""

    return [
        create_product_subagent(model),
        create_order_subagent(model),
        create_logistics_subagent(model),
        create_refund_subagent(model),
        create_after_sales_subagent(model),
        create_policy_subagent(model),
    ]


def _create_subagent(
    *, model: Any, name: str, description: str, prompt: str, tools: list
) -> dict:
    return {
        "name": name,
        "description": description,
        "runnable": create_agent(
            model=model,
            system_prompt=prompt,
            tools=tools,
            name=name,
        ),
    }
