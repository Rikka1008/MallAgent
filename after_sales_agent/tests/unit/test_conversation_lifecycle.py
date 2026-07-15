from datetime import datetime, timedelta, timezone

import pytest

from services.conversations.lifecycle import (
    ConversationBusyError,
    ConversationLifecycle,
    ConversationUnavailableError,
)
from services.conversations.models import (
    ConversationRecord,
    ConversationStatus,
    ConversationTurn,
    SummaryStatus,
)


NOW = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)


def record(*, user_id="U1", status=ConversationStatus.ACTIVE, last_active_at=NOW):
    return ConversationRecord(
        conversation_id="C-1",
        user_id=user_id,
        status=status,
        summary_status=SummaryStatus.NOT_STARTED,
        last_active_at=last_active_at,
        created_at=NOW,
        updated_at=NOW,
    )


class FakeRepository:
    def __init__(self, value=None):
        self.value = value
        self.touches = []
        self.created = []

    async def get_active(self, user_id, idle_after):
        if self.value and self.value.user_id == user_id and self.value.last_active_at > idle_after:
            return self.value
        return None

    async def get_owned(self, conversation_id, user_id):
        if self.value and self.value.conversation_id == conversation_id and self.value.user_id == user_id:
            return self.value
        return None

    async def create_active(self, user_id, now):
        self.created.append((user_id, now))
        self.value = record(user_id=user_id, last_active_at=now)
        return self.value

    async def touch(self, conversation_id, user_id, now, message_delta):
        self.touches.append((conversation_id, user_id, now, message_delta))
        return self.value

    async def list_recent_summaries(self, user_id, now, limit):
        return []


class FakeTurns:
    def __init__(self, lease_available=True):
        self.items = []
        self.lease_available = lease_available
        self.released = []

    async def acquire_lease(self, conversation_id):
        return "lease-1" if self.lease_available else None

    async def release_lease(self, conversation_id, token):
        self.released.append((conversation_id, token))

    async def append_turn(self, conversation_id, turn):
        self.items.append((conversation_id, turn))


@pytest.mark.asyncio
async def test_get_active_does_not_refresh_last_active_time():
    repository = FakeRepository(record())
    lifecycle = ConversationLifecycle(repository, FakeTurns(), clock=lambda: NOW)

    result = await lifecycle.get_active("U1")

    assert result.conversation_id == "C-1"
    assert repository.touches == []


@pytest.mark.asyncio
async def test_require_active_rejects_wrong_owner_or_expired_session():
    lifecycle = ConversationLifecycle(
        FakeRepository(record(last_active_at=NOW - timedelta(minutes=31))),
        FakeTurns(),
        clock=lambda: NOW,
    )

    with pytest.raises(ConversationUnavailableError):
        await lifecycle.require_active("C-1", "U1")
    with pytest.raises(ConversationUnavailableError):
        await lifecycle.require_active("C-1", "U2")


@pytest.mark.asyncio
async def test_record_successful_turn_persists_normalized_turn_and_touches_session():
    repository = FakeRepository(record())
    turns = FakeTurns()
    lifecycle = ConversationLifecycle(repository, turns, clock=lambda: NOW)
    turn = ConversationTurn(user_text="退款怎么样了", assistant_text="正在审核")

    await lifecycle.record_turn("C-1", "U1", turn)

    assert turns.items == [("C-1", turn)]
    assert repository.touches == [("C-1", "U1", NOW, 2)]


@pytest.mark.asyncio
async def test_begin_turn_refreshes_lease_without_incrementing_message_count():
    repository = FakeRepository(record())
    lifecycle = ConversationLifecycle(repository, FakeTurns(), clock=lambda: NOW)

    token = await lifecycle.begin_turn("C-1", "U1")

    assert token == "lease-1"
    assert repository.touches == [("C-1", "U1", NOW, 0)]


@pytest.mark.asyncio
async def test_create_new_rejects_closing_an_inflight_conversation():
    repository = FakeRepository(record())
    lifecycle = ConversationLifecycle(
        repository,
        FakeTurns(lease_available=False),
        clock=lambda: NOW,
    )

    with pytest.raises(ConversationBusyError):
        await lifecycle.create_new("U1")

    assert repository.created == []
