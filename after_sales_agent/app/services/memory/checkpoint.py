from __future__ import annotations

import logging

from langgraph.checkpoint.redis.aio import AsyncRedisSaver
from langgraph.checkpoint.memory import InMemorySaver

from config import AppConfig
from config import RedisConfig


logger = logging.getLogger("after_sales.checkpoint")


class RedisCheckpointManager:
    def __init__(self):
        self._context = None
        self.saver: AsyncRedisSaver | None = None

    async def start(self) -> AsyncRedisSaver:
        if self.saver is not None:
            return self.saver
        if not RedisConfig.REDIS_URL:
            if AppConfig.APP_ENV == "local":
                logger.warning("REDIS_URL is not configured; using in-memory LangGraph checkpointing")
                self.saver = InMemorySaver()
                return self.saver
            raise RuntimeError("必须配置 REDIS_URL 才能启用 LangGraph 会话记忆")
        context = AsyncRedisSaver.from_conn_string(
            RedisConfig.REDIS_URL,
            ttl={"default_ttl": RedisConfig.CHECKPOINT_TTL_MINUTES, "refresh_on_read": True},
        )
        try:
            saver = await context.__aenter__()
        except Exception:
            if AppConfig.APP_ENV != "local":
                raise
            logger.warning(
                "Redis checkpoint setup failed in local environment; "
                "using in-memory checkpointing",
                exc_info=True,
            )
            self.saver = InMemorySaver()
            return self.saver
        self._context = context
        self.saver = saver
        await self.saver.asetup()
        return self.saver

    async def close(self) -> None:
        if self._context is not None:
            await self._context.__aexit__(None, None, None)
        self._context = None
        self.saver = None


checkpoint_manager = RedisCheckpointManager()
