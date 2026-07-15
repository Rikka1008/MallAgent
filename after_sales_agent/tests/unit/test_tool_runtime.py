from dataclasses import dataclass

from agent.context import AgentRuntimeContext
from tests.fakes import FakeEcommerceGateway
from tools import READ_ONLY_TOOLS
from tools.logistics_tools import get_logistics
from tools.order_tools import get_order
from tools.policy_tools import search_policy
from tools.product_tools import search_products
from tools.refund_tools import get_refund_status


@dataclass
class FakeRuntime:
    context: AgentRuntimeContext


class FakeRetriever:
    degradation_events = []

    async def search(self, query: str, limit: int):
        return [
            {
                "title": "轻量跑鞋",
                "content": f"商品匹配：{query}",
                "score": 0.98,
                "metadata": {"product_id": "SKU1001"},
            }
        ][:limit]


def _runtime() -> FakeRuntime:
    return FakeRuntime(
        context=AgentRuntimeContext(
            user_id="U100",
            session_id="S100",
            gateway=FakeEcommerceGateway(),
            case_context={
                "policy_retriever": FakeRetriever(),
                "product_retriever": FakeRetriever(),
            },
        )
    )


async def test_business_tools_read_identity_and_gateway_from_runtime_context():
    runtime = _runtime()

    order = await get_order.coroutine(order_id="ORD1001", runtime=runtime)
    logistics = await get_logistics.coroutine(
        order_id="ORD1002", tracking_no=None, runtime=runtime
    )
    refund = await get_refund_status.coroutine(
        order_id="ORD1001", after_sales_id=None, runtime=runtime
    )

    assert order["found"] is True
    assert logistics["found"] is True
    assert refund["found"] is True


async def test_retrieval_tools_use_request_scoped_retrievers():
    runtime = _runtime()

    policy = await search_policy.coroutine(
        query="七天无理由退货", limit=3, runtime=runtime
    )
    products = await search_products.coroutine(query="轻量跑鞋", limit=3, runtime=runtime)

    assert policy["found"] is True
    assert policy["snippets"][0]["title"] == "轻量跑鞋"
    assert products["found"] is True
    assert products["items"][0]["metadata"]["product_id"] == "SKU1001"


def test_tool_schemas_do_not_expose_runtime_dependencies():
    expected_names = [
        "list_orders",
        "get_order",
        "get_logistics",
        "get_refund_status",
        "search_policy",
        "search_products",
    ]

    assert [tool.name for tool in READ_ONLY_TOOLS] == expected_names
    for tool in READ_ONLY_TOOLS:
        properties = tool.tool_call_schema.model_json_schema()["properties"]
        assert "user_id" not in properties
        assert "gateway" not in properties
        assert "runtime" not in properties
