from tools.logistics_tools import get_logistics
from tools.order_tools import get_order
from tools.policy_tools import search_policy
from tools.product_tools import search_products
from tools.refund_tools import get_refund_status
from tools import READ_ONLY_TOOLS


def test_readonly_tools_are_registered_for_llm_without_server_injected_arguments():
    tools = [get_order, get_logistics, get_refund_status, search_policy, search_products]

    assert [tool.name for tool in READ_ONLY_TOOLS] == [
        "list_orders",
        "get_order",
        "get_logistics",
        "get_refund_status",
        "search_policy",
        "search_products",
    ]
    assert tuple(tools) == READ_ONLY_TOOLS[1:]
    for tool in READ_ONLY_TOOLS:
        properties = tool.tool_call_schema.model_json_schema()["properties"]
        assert "user_id" not in properties
        assert "gateway" not in properties
        assert "runtime" not in properties

    assert "用户编号" not in get_order.description
