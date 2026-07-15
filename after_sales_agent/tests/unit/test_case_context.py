from agent.state import AgentState
from services.cases.context import AfterSalesCase, CaseStage
from services.cases.resolver import resolve_product_reference
from services.cases.store import CaseService
from tests.fakes import FakeEcommerceGateway


async def test_product_reference_resolver_binds_a_named_item_from_selected_order():
    case = AfterSalesCase(
        case_id="CASE-1",
        user_id="U100",
        session_id="S100",
        order_id="ORD1001",
        stage=CaseStage.COLLECTING,
    )

    resolved = await resolve_product_reference(
        case, "就是刚刚那个轻量跑鞋", FakeEcommerceGateway()
    )

    assert resolved.product_id == "SKU1001"
    assert case.product_id == "SKU1001"
    assert case.product_name == "轻量跑鞋"


async def test_product_reference_resolver_selects_the_only_order_item_without_internal_id():
    case = AfterSalesCase(
        case_id="CASE-2",
        user_id="U100",
        session_id="S100",
        order_id="ORD1002",
    )

    resolved = await resolve_product_reference(case, "我不想要了", FakeEcommerceGateway())

    assert resolved.product_id == "SKU1002"
    assert resolved.requires_selection is False


def test_case_context_hydrates_business_slots_without_becoming_user_preference():
    case = AfterSalesCase(
        case_id="CASE-3",
        user_id="U100",
        session_id="S100",
        order_id="ORD1001",
        product_id="SKU1001",
        after_sales_type="return",
        reason="不想要了",
    )
    state = AgentState(session_id="S100", user_id="U100")

    case.hydrate_state(state)

    assert state.slots == {
        "order_id": "ORD1001",
        "product_id": "SKU1001",
        "after_sales_type": "return",
        "reason": "不想要了",
    }
    assert "preferences" not in case.model_dump_json()


async def test_case_service_restores_the_durable_case_when_hot_context_expires():
    class FakeStore:
        def __init__(self):
            self.values = {}
            self.events = []

        async def get(self, case_id):
            return self.values.get(case_id)

        async def put(self, case):
            self.values[case.case_id] = case.model_copy(deep=True)

        async def record_event(self, case_id, event_type, payload):
            self.events.append((case_id, event_type, payload))

    hot_store = FakeStore()
    durable_store = FakeStore()
    service = CaseService(hot_store=hot_store, durable_store=durable_store)
    case = await service.get_or_create(user_id="U100", session_id="S100")
    case.order_id = "ORD1001"
    await service.save(case)
    hot_store.values.clear()

    restored = await service.get_or_create(user_id="U100", session_id="S100")

    assert restored.case_id == case.case_id
    assert restored.order_id == "ORD1001"
    assert restored.case_id in hot_store.values
    assert durable_store.events[-1][1] == "case_saved"
