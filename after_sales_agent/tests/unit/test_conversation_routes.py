from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage

from api.dependencies import get_conversation_lifecycle, get_gateway
from api.routes import _process_chat_turn
from api.schemas import ChatRequest
from domain.models import CurrentMember
from main import app
from services.conversations.models import ConversationRecord, ConversationStatus, SummaryStatus


NOW = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)


def session():
    return ConversationRecord(
        conversation_id="C-1",
        user_id="U1",
        status=ConversationStatus.ACTIVE,
        summary_status=SummaryStatus.NOT_STARTED,
        last_active_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


class Gateway:
    async def get_current_member(self):
        return CurrentMember(user_id="U1", username="member")


class Lifecycle:
    def __init__(self, active=None):
        self.active = active

    async def get_active(self, user_id):
        assert user_id == "U1"
        return self.active

    async def create_new(self, user_id):
        assert user_id == "U1"
        return session()


def test_get_active_conversation_returns_404_without_mutating():
    app.dependency_overrides[get_gateway] = Gateway
    app.dependency_overrides[get_conversation_lifecycle] = lambda: Lifecycle()
    try:
        response = TestClient(app).get("/api/conversations/active")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 404


def test_post_conversation_creates_server_owned_id():
    app.dependency_overrides[get_gateway] = Gateway
    app.dependency_overrides[get_conversation_lifecycle] = lambda: Lifecycle(session())
    try:
        response = TestClient(app).post("/api/conversations")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 201
    assert response.json()["conversation_id"] == "C-1"


@pytest.mark.asyncio
async def test_memory_persistence_failure_does_not_hide_agent_business_result():
    class Agent:
        async def ainvoke(self, _input, _config, context):
            assert context.user_id == "U1"
            return {"messages": [AIMessage(content="退款申请已提交，售后单号 AS1。")]}

    class MemoryStore:
        async def get(self, *_args):
            return None

    class CaseService:
        async def get_or_create(self, *_args):
            return object()

    class FailingMemoryLifecycle(Lifecycle):
        async def begin_turn(self, *_args):
            return "lease-1"

        async def release_turn(self, *_args):
            return None

        async def recall(self, _user_id):
            return []

        async def record_turn(self, *_args):
            raise RuntimeError("redis unavailable")

    response = await _process_chat_turn(
        ChatRequest(session_id="C-1", message="申请退款"),
        Agent(),
        Gateway(),
        MemoryStore(),
        object(),
        CaseService(),
        FailingMemoryLifecycle(session()),
    )

    assert response.reply == "退款申请已提交，售后单号 AS1。"
