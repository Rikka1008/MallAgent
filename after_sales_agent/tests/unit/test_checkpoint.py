import pytest

from langgraph.checkpoint.memory import InMemorySaver

from config import AppConfig
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
