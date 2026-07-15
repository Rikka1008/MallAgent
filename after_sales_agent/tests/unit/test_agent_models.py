import pytest
from pydantic import ValidationError

import agent.models as agent_models
from agent.models import IntentDecision
from agent.state import AgentState


def test_intent_decision_validates_confidence():
    with pytest.raises(ValidationError):
        IntentDecision(intent="order_query", confidence=1.1, reason="订单", strategy="llm")


def test_agent_state_contains_only_cross_turn_business_context():
    state = AgentState(session_id="S1", user_id="U1")

    assert state.model_dump() == {
        "session_id": "S1",
        "user_id": "U1",
        "messages": [],
        "intent": None,
        "slots": {},
        "order_candidates": [],
        "tool_results": {},
        "missing_slots": [],
        "unresolved_count": 0,
    }


def test_agent_plan_rejects_unregistered_agent_name():
    assert hasattr(agent_models, "AgentPlan")
    with pytest.raises(ValidationError):
        agent_models.AgentPlan(
            intent="order_query",
            agent_name="mall_raw_http",
            slot_updates={},
            required_slots=[],
            needs_tool=True,
            reply_goal="查询订单",
            confidence=0.9,
        )


def test_agent_state_keeps_tool_results_without_credentials():
    state = AgentState(
        session_id="S1",
        user_id="U1",
        tool_results={"order": {"order_id": "O1"}},
    )

    assert state.model_dump()["tool_results"] == {"order": {"order_id": "O1"}}
