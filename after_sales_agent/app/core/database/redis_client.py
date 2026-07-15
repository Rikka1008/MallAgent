from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config import RedisConfig


@dataclass
class RedisClient:
    """Redis 客户端连接池。
    这里保留一个很小的异步入口，方便后续在需要原始 Redis 客户端的模块中复用连接。
    业务侧短期记忆由 LangGraph `AsyncRedisSaver` 管理。
    """
    _pool: Any = None

    @classmethod
    async def get(cls, url: str | None = RedisConfig.REDIS_URL) -> Any:
        """获取单例 Redis 客户端。"""

        if not url:
            raise RuntimeError("请先配置 REDIS_URL，再使用 RedisClient。")
        if cls._pool is None: 
            try:
                from redis.asyncio import Redis
            except ImportError as exc:
                raise RuntimeError("请先安装 redis，再使用 RedisClient。") from exc
            cls._pool = Redis.from_url(url, decode_responses=True)
        return cls._pool

    @classmethod
    async def close(cls) -> None:
        """关闭 Redis 客户端连接池。"""

        if cls._pool is not None:
            await cls._pool.close()
            cls._pool = None
