import pytest

from langgraph.checkpoint.memory import InMemorySaver

from config import AppConfig, RedisConfig
from services.memory.checkpoint import RedisCheckpointManager


@pytest.mark.asyncio
async def test_local_checkpoint_falls_back_to_memory_when_redis_stack_is_unavailable(monkeypatch):
    async def fail_start(*_args, **_kwargs):
        raise RuntimeError("unknown command 'FT._LIST'")

    class FailingContext:
        async def __aenter__(self):
            raise RuntimeError("unknown command 'FT._LIST'")

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(AppConfig, "APP_ENV", "local")
    monkeypatch.setattr("services.memory.checkpoint.AsyncRedisSaver.from_conn_string", lambda *_args, **_kwargs: FailingContext())

    manager = RedisCheckpointManager()
    saver = await manager.start()

    assert isinstance(saver, InMemorySaver)
    await manager.close()


@pytest.mark.asyncio
async def test_checkpoint_ttl_is_passed_in_minutes(monkeypatch):
    captured = {}

    class FakeSaver:
        async def asetup(self):
            return None

    class FakeContext:
        async def __aenter__(self):
            return FakeSaver()

        async def __aexit__(self, *_args):
            return None

    def from_conn_string(_url, *, ttl):
        captured["ttl"] = ttl
        return FakeContext()

    monkeypatch.setattr(RedisConfig, "REDIS_URL", "redis://unit-test:6379/0")
    monkeypatch.setattr(RedisConfig, "CHECKPOINT_TTL_MINUTES", 120)
    monkeypatch.setattr(
        "services.memory.checkpoint.AsyncRedisSaver.from_conn_string",
        from_conn_string,
    )

    manager = RedisCheckpointManager()
    await manager.start()

    assert captured["ttl"] == {"default_ttl": 120, "refresh_on_read": True}
    await manager.close()
