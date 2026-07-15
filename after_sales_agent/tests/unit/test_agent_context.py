from dataclasses import dataclass

from agent.context import AgentRuntimeContext
from tests.fakes import FakeEcommerceGateway


@dataclass
class FakeRuntime:
    context: AgentRuntimeContext


def test_agent_runtime_context_keeps_request_scoped_dependencies():
    gateway = FakeEcommerceGateway()
    context = AgentRuntimeContext(
        user_id="U100",
        session_id="S100",
        gateway=gateway,
        authorization="Bearer test-token",
        case_context={"case_id": "CASE100"},
        long_term_memory={"preferred_category": "运动鞋"},
        idempotency_store=object(),
    )

    runtime = FakeRuntime(context=context)

    assert runtime.context.user_id == "U100"
    assert runtime.context.gateway is gateway
    assert runtime.context.case_context["case_id"] == "CASE100"
    assert runtime.context.long_term_memory["preferred_category"] == "运动鞋"
