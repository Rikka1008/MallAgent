"""Agent 可调用的只读业务工具注册表；写操作不会出现在此处。"""

from tools.logistics_tools import get_logistics
from tools.order_tools import get_order, list_orders
from tools.policy_tools import search_policy
from tools.product_tools import search_products
from tools.refund_tools import get_refund_status

READ_ONLY_TOOLS = (
    list_orders,
    get_order,
    get_logistics,
    get_refund_status,
    search_policy,
    search_products,
)

__all__ = ["READ_ONLY_TOOLS"]
