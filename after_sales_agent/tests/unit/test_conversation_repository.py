import pytest

from services.conversations.models import ConversationTurn
from services.conversations.repository import (
    RedisConversationRepository,
    sanitize_summary_error,
)


class FakePipeline:
    def __init__(self, redis):
        self.redis = redis
        self.commands = []

    def rpush(self, key, value):
        self.commands.append(("rpush", key, value))
        return self

    def expire(self, key, ttl):
        self.commands.append(("expire", key, ttl))
        return self

    async def execute(self):
        for command, *args in self.commands:
            await getattr(self.redis, command)(*args)


class FakeRedis:
    def __init__(self):
        self.values = {}
        self.ttls = {}

    def pipeline(self, transaction=True):
        assert transaction is True
        return FakePipeline(self)

    async def rpush(self, key, value):
        self.values.setdefault(key, []).append(value)

    async def expire(self, key, ttl):
        self.ttls[key] = ttl

    async def lrange(self, key, _start, _end):
        return self.values.get(key, [])

    async def delete(self, key):
        self.values.pop(key, None)

    async def set(self, key, value, ex=None, nx=False):
        if nx and key in self.values:
            return False
        self.values[key] = value
        self.ttls[key] = ex
        return True

    async def eval(self, _script, _count, key, token):
        if self.values.get(key) == token:
            self.values.pop(key, None)
            return 1
        return 0


@pytest.mark.asyncio
async def test_redis_conversation_turns_keep_order_and_refresh_ttl():
    redis = FakeRedis()
    repository = RedisConversationRepository(client=redis, ttl_seconds=7200)
    first = ConversationTurn(user_text="退款", assistant_text="请提供订单号")
    second = ConversationTurn(user_text="ORD1", assistant_text="正在处理")

    await repository.append_turn("C-1", first)
    await repository.append_turn("C-1", second)

    turns = await repository.list_turns("C-1")
    assert [turn.user_text for turn in turns] == ["退款", "ORD1"]
    assert redis.ttls["after_sales:conversation:C-1:turns"] == 7200


@pytest.mark.asyncio
async def test_redis_delete_only_targets_one_conversation():
    redis = FakeRedis()
    repository = RedisConversationRepository(client=redis, ttl_seconds=7200)
    turn = ConversationTurn(user_text="退款", assistant_text="处理中")
    await repository.append_turn("C-1", turn)
    await repository.append_turn("C-2", turn)

    await repository.delete_turns("C-1")

    assert await repository.list_turns("C-1") == []
    assert len(await repository.list_turns("C-2")) == 1


@pytest.mark.asyncio
async def test_conversation_lease_has_single_owner_and_token_safe_release():
    redis = FakeRedis()
    repository = RedisConversationRepository(client=redis, ttl_seconds=7200)

    first = await repository.acquire_lease("C-1")
    second = await repository.acquire_lease("C-1")
    await repository.release_lease("C-1", "wrong-token")

    assert first is not None
    assert second is None
    assert "after_sales:conversation:C-1:inflight" in redis.values

    await repository.release_lease("C-1", first)
    assert "after_sales:conversation:C-1:inflight" not in redis.values


def test_summary_error_is_single_line_and_bounded():
    error = sanitize_summary_error(RuntimeError("secret\n" + "x" * 2000))

    assert "\n" not in error
    assert len(error) <= 1000
    assert "secret" not in error


def test_conversation_repository_source_uses_owned_filters_and_skip_locked():
    from pathlib import Path

    source = (
        Path(__file__).resolve().parents[2]
        / "app/services/conversations/repository.py"
    ).read_text(encoding="utf-8")

    assert "self.table.c.conversation_id == conversation_id" in source
    assert "self.table.c.user_id == user_id" in source
    assert "with_for_update(skip_locked=True)" in source
    assert "pg_advisory_xact_lock" in source
    assert "SummaryStatus.PROCESSING.value" in source
    assert "stale_claim_before" in source
    assert "else_=None" in source
