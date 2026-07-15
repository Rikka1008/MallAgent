from dataclasses import dataclass

from agent.context import AgentRuntimeContext
from tests.fakes import FakeEcommerceGateway
from agent.models import AgentPlan
from agent.state import AgentState
from domain.models import CurrentMember
from tools.after_sales_tools import (
    MemoryIdempotencyStore,
    RedisIdempotencyStore,
    ToolExecutionResult,
    check_after_sales_policy,
    create_after_sales_request,
    execute_after_sales_plan,
    submit_after_sales_request,
)
from tools.logistics_tools import get_logistics
from tools import order_tools
from tools.order_tools import get_order
from tools.policy_tools import search_policy
from tools import product_tools
from tools.refund_tools import get_refund_status
import pytest
from config import MilvusConfig


@dataclass
class FakeRuntime:
    context: AgentRuntimeContext


def _runtime(gateway=None) -> FakeRuntime:
    return FakeRuntime(
        context=AgentRuntimeContext(
            user_id="U100",
            session_id="STOOL1",
            gateway=gateway or FakeEcommerceGateway(),
        )
    )


@pytest.fixture(autouse=True)
def disable_external_milvus(monkeypatch):
    monkeypatch.setattr(MilvusConfig, "URI", None)


async def test_order_tool_returns_order():
    result = await get_order.coroutine(order_id="ORD1001", runtime=_runtime())

    assert result["found"] is True
    assert result["order"]["order_id"] == "ORD1001"


async def test_list_orders_tool_returns_current_users_recent_orders():
    result = await order_tools.list_orders.coroutine(
        status=-1,
        limit=10,
        runtime=_runtime(),
    )

    assert result["found"] is True
    assert result["count"] == 2
    assert [order["order_id"] for order in result["orders"]] == [
        "ORD1002",
        "ORD1001",
    ]


async def test_list_orders_tool_filters_by_mall_order_status():
    result = await order_tools.list_orders.coroutine(
        status=2,
        limit=10,
        runtime=_runtime(),
    )

    assert result["count"] == 1
    assert result["orders"][0]["order_id"] == "ORD1002"


async def test_logistics_tool_returns_status():
    result = await get_logistics.coroutine(
        order_id="ORD1002", tracking_no=None, runtime=_runtime()
    )

    assert result["found"] is True
    assert result["logistics"]["current_status"] == "运输中"


async def test_refund_tool_returns_status():
    result = await get_refund_status.coroutine(
        order_id="ORD1001", after_sales_id=None, runtime=_runtime()
    )

    assert result["found"] is True
    assert "退款" in result["refund"]["status"]


async def test_policy_tool_returns_snippets():
    result = await search_policy.coroutine(
        query="七天无理由退货", limit=3, runtime=_runtime()
    )

    assert result["found"] is True
    assert result["snippets"]


def test_default_product_retriever_uses_local_product_knowledge_as_fallback():
    retriever = product_tools._build_product_retriever()

    results = retriever.keyword_retriever.search("宽脚 健步鞋", limit=3)

    assert results
    assert "SHOE-DEMO-008" in results[0].title
    assert "宽楦" in results[0].content


async def test_after_sales_policy_and_create_request():
    gateway = FakeEcommerceGateway()
    decision = await check_after_sales_policy(
        order_id="ORD1001",
        product_id="SKU1001",
        after_sales_type="return",
        reason="七天无理由退货",
        user_id="U100",
        gateway=gateway,
    )

    assert decision["eligible"] is True

    created = await create_after_sales_request(
        order_id="ORD1001",
        product_id="SKU1001",
        after_sales_type="return",
        reason="七天无理由退货",
        user_id="U100",
        gateway=gateway,
    )

    assert created["created"] is True
    assert created["after_sales_request"]["after_sales_id"].startswith("AS")


async def test_after_sales_runtime_tool_uses_server_context_for_safe_submission():
    result = await submit_after_sales_request.coroutine(
        order_id="ORD1001",
        product_id="SKU1001",
        after_sales_type="return",
        reason="七天无理由退货",
        runtime=FakeRuntime(
            context=AgentRuntimeContext(
                user_id="U100",
                session_id="SAFE1",
                gateway=FakeEcommerceGateway(),
                idempotency_store=MemoryIdempotencyStore(),
            )
        ),
    )

    assert result["status"] == "success"
    assert result["data"]["after_sales_id"].startswith("AS")


async def test_after_sales_runtime_tool_accepts_refund_request():
    result = await submit_after_sales_request.coroutine(
        order_id="ORD1001",
        product_id="SKU1001",
        after_sales_type="refund",
        reason="未发货退款",
        runtime=FakeRuntime(
            context=AgentRuntimeContext(
                user_id="U100",
                session_id="REFUND1",
                gateway=FakeEcommerceGateway(),
                idempotency_store=MemoryIdempotencyStore(),
            )
        ),
    )

    assert result["status"] == "success"
    assert result["data"]["after_sales_request"]["after_sales_type"] == "refund"


def _return_plan():
    return AgentPlan(
        intent="return_exchange",
        agent_name="after_sales",
        slot_updates={},
        required_slots=[],
        needs_tool=True,
        reply_goal="提交退货申请",
        confidence=1.0,
    )


def _return_state():
    return AgentState(
        session_id="SWRITE1",
        user_id="U100",
        slots={
            "order_id": "ORD1001",
            "product_id": "SKU1001",
            "after_sales_type": "return",
            "reason": "七天无理由退货",
        },
    )


async def test_after_sales_write_rejects_order_belonging_to_another_user():
    class ForeignOrderGateway(FakeEcommerceGateway):
        async def get_current_member(self):
            return CurrentMember(user_id="U1", username="U1")

        async def get_order(self, order_id, user_id):
            order = self.orders.get("ORD1001")
            return order.model_copy(update={"user_id": "U2"}) if order else None

    result = await execute_after_sales_plan(
        _return_plan(),
        _return_state().model_copy(update={"user_id": "U1"}),
        ForeignOrderGateway(),
        MemoryIdempotencyStore(),
    )

    assert result.status == "rejected"
    assert "订单归属" in result.message


async def test_after_sales_write_deduplicates_same_idempotency_key():
    gateway = FakeEcommerceGateway()
    store = MemoryIdempotencyStore()

    first = await execute_after_sales_plan(_return_plan(), _return_state(), gateway, store)
    second = await execute_after_sales_plan(_return_plan(), _return_state(), gateway, store)

    assert first.status == "success"
    assert second.status == "success"
    assert first.data["after_sales_id"] == second.data["after_sales_id"]
    assert len(gateway.created_requests) == 1


async def test_after_sales_write_accepts_chinese_refund_type():
    gateway = FakeEcommerceGateway()
    state = _return_state().model_copy(
        update={
            "slots": {
                **_return_state().slots,
                "after_sales_type": "退款",
            }
        }
    )

    result = await execute_after_sales_plan(
        _return_plan(), state, gateway, MemoryIdempotencyStore()
    )

    assert result.status == "success"
    assert gateway.created_requests[0].after_sales_type == "refund"


async def test_after_sales_write_does_not_reject_generic_reason_without_policy_hit():
    gateway = FakeEcommerceGateway()
    state = _return_state().model_copy(
        update={
            "slots": {
                **_return_state().slots,
                "after_sales_type": "refund",
                "reason": "不想要了",
            }
        }
    )

    result = await execute_after_sales_plan(
        _return_plan(), state, gateway, MemoryIdempotencyStore()
    )

    assert result.status == "success"
    assert gateway.created_requests[0].reason == "不想要了"


async def test_after_sales_write_propagates_gateway_error():
    class FailingGateway(FakeEcommerceGateway):
        async def create_after_sales_request(self, *args, **kwargs):
            raise RuntimeError("Mall 写接口不可用")

    with pytest.raises(RuntimeError, match="Mall 写接口不可用"):
        await execute_after_sales_plan(
            _return_plan(), _return_state(), FailingGateway(), MemoryIdempotencyStore()
        )


async def test_redis_idempotency_store_uses_setnx_and_persists_result():
    class FakeRedis:
        def __init__(self):
            self.values = {}
            self.calls = []

        async def get(self, key):
            return self.values.get(key)

        async def set(self, key, value, ex, nx=False):
            self.calls.append((key, value, ex, nx))
            if nx and key in self.values:
                return False
            self.values[key] = value
            return True

    redis = FakeRedis()
    store = RedisIdempotencyStore(prefix="test:", ttl_seconds=60)

    async def fake_client():
        return redis

    store._client = fake_client

    assert await store.reserve("K1") is True
    assert await store.reserve("K1") is False
    await store.put("K1", ToolExecutionResult(status="success", message="已提交"))
    result = await store.get("K1")

    assert result.status == "success"
    assert redis.calls[0][3] is True
    assert redis.calls[0][2] == 60
