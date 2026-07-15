from datetime import datetime, timezone

import pytest

from services.conversations.finalization import ConversationFinalizer, ConversationSummarizer
from services.conversations.models import (
    ConversationRecord,
    ConversationStatus,
    ConversationTurn,
    SummaryStatus,
)


NOW = datetime(2026, 7, 15, 12, 0, tzinfo=timezone.utc)


def claimed(attempts=1):
    return ConversationRecord(
        conversation_id="C-1",
        user_id="U1",
        status=ConversationStatus.CLOSED,
        summary_status=SummaryStatus.PROCESSING,
        close_reason="idle_timeout",
        summary_attempts=attempts,
        last_active_at=NOW,
        closed_at=NOW,
        expires_at=NOW,
        created_at=NOW,
        updated_at=NOW,
    )


SUMMARY = {
    "schema_version": 1,
    "session_intent": "查询退款",
    "order_ids": ["ORD1", "MADE-UP"],
    "after_sales_ids": ["AS1", "AS-FAKE"],
    "product_ids": [],
    "completed_actions": ["已提交申请"],
    "pending_actions": ["等待审核"],
    "explicit_preferences": [],
    "last_user_request": "查询 ORD1 的 AS1",
    "observed_at": NOW.isoformat(),
}


@pytest.mark.asyncio
async def test_summarizer_validates_and_removes_fabricated_identifiers():
    async def generate(_turns):
        return SUMMARY

    summarizer = ConversationSummarizer(generate=generate)
    turns = [ConversationTurn(user_text="查询 ORD1", assistant_text="售后单 AS1 审核中")]

    summary = await summarizer.summarize(turns)

    assert summary.order_ids == ["ORD1"]
    assert summary.after_sales_ids == ["AS1"]


class FakeRepository:
    def __init__(self, records, fail_complete=False):
        self.records = records
        self.fail_complete = fail_complete
        self.completed = []
        self.failed = []
        self.deleted_limit = None

    async def claim_due(self, now, idle_before, limit):
        return self.records

    async def complete_summary(self, conversation_id, summary, summary_text, now):
        if self.fail_complete:
            raise RuntimeError("postgres unavailable")
        self.completed.append((conversation_id, summary, summary_text, now))

    async def fail_summary(self, conversation_id, error, retry_at, now):
        self.failed.append((conversation_id, retry_at))

    async def delete_expired(self, now, limit):
        self.deleted_limit = limit
        return []


class FakeTurns:
    def __init__(self, fail_delete=False):
        self.deleted = []
        self.fail_delete = fail_delete

    async def list_turns(self, conversation_id):
        return [ConversationTurn(user_text="查询 ORD1", assistant_text="AS1 审核中")]

    async def delete_turns(self, conversation_id):
        if self.fail_delete:
            raise RuntimeError("redis unavailable")
        self.deleted.append(conversation_id)


@pytest.mark.asyncio
async def test_finalizer_deletes_redis_only_after_postgres_completion():
    repository = FakeRepository([claimed()])
    turns = FakeTurns()
    summarizer = ConversationSummarizer(generate=lambda _turns: _async_value(SUMMARY))
    finalizer = ConversationFinalizer(repository, turns, summarizer, clock=lambda: NOW)

    await finalizer.run_once()

    assert repository.completed
    assert turns.deleted == ["C-1"]
    assert repository.deleted_limit == 500


@pytest.mark.asyncio
async def test_postgres_completion_failure_keeps_redis_and_schedules_retry():
    repository = FakeRepository([claimed()], fail_complete=True)
    turns = FakeTurns()
    finalizer = ConversationFinalizer(
        repository,
        turns,
        ConversationSummarizer(generate=lambda _turns: _async_value(SUMMARY)),
        clock=lambda: NOW,
    )

    await finalizer.run_once()

    assert repository.failed
    assert turns.deleted == []


@pytest.mark.asyncio
async def test_redis_delete_failure_does_not_regress_completed_summary():
    repository = FakeRepository([claimed()])
    turns = FakeTurns(fail_delete=True)
    finalizer = ConversationFinalizer(
        repository,
        turns,
        ConversationSummarizer(generate=lambda _turns: _async_value(SUMMARY)),
        clock=lambda: NOW,
    )

    await finalizer.run_once()

    assert repository.completed
    assert repository.failed == []


@pytest.mark.asyncio
@pytest.mark.parametrize("attempts, delay", [(1, 60), (2, 300), (3, None)])
async def test_finalizer_retry_schedule_keeps_redis_turns(attempts, delay):
    async def fail(_turns):
        raise RuntimeError("model unavailable")

    repository = FakeRepository([claimed(attempts)])
    turns = FakeTurns()
    finalizer = ConversationFinalizer(
        repository,
        turns,
        ConversationSummarizer(generate=fail),
        clock=lambda: NOW,
    )

    await finalizer.run_once()

    retry_at = repository.failed[0][1]
    assert retry_at is None if delay is None else (retry_at - NOW).total_seconds() == delay
    assert turns.deleted == []


async def _async_value(value):
    return value
