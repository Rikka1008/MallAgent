from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from config import MilvusConfig


@dataclass
class MilvusClient:
    """Milvus 异步客户端连接池。
    
    提供单例异步客户端，与项目整体异步架构保持一致。
    所有业务代码应通过此类获取 Milvus 客户端，统一连接生命周期管理。
    """
    _client: Any = None

    @classmethod
    async def get_client(cls) -> Any:
        """获取异步 Milvus 客户端。"""
        if cls._client is None:
            try:
                from pymilvus import AsyncMilvusClient
            except ImportError as exc:
                raise RuntimeError("请先安装 pymilvus，再使用 MilvusPool。") from exc
            cls._client = AsyncMilvusClient(
                uri=MilvusConfig.URI,
                token=MilvusConfig.TOKEN,
                db_name=MilvusConfig.DB_NAME,
                timeout=1,
            )
        return cls._client

    @classmethod
    async def close(cls) -> None:
        """关闭 Milvus 客户端连接。"""
        if cls._client is not None:
            await cls._client.close()
            cls._client = None
