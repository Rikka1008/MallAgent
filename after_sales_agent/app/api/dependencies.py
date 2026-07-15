import os
import asyncio
from typing import Annotated

from fastapi import Cookie, Header, HTTPException, status
from fastapi import Depends

from adapters.ecommerce_gateway import EcommerceGateway
from adapters.mall_gateway import MallEcommerceGateway
from agent.main_agent import build_main_agent
from tools.after_sales_tools import get_redis_idempotency_store
from config import AppConfig, MallConfig
from core.database.redis_client import RedisClient
from core.database.SQLAlchemy import SqlAlchemyPool
from core.database.milvus_client import MilvusClient
from knowledge.ingestion.models import DocumentChunk
from knowledge.ingestion.vectorizer import BgeM3Vectorizer
from services.memory.checkpoint import checkpoint_manager
from services.memory.semantic import (
    ConversationCompressor,
    OpenAIConversationSummarizer,
    SemanticMemoryService,
)
from services.memory.stores import MilvusBaseStore
from config import EmbeddingConfig, MilvusConfig
from services.memory.stores import PostgresBaseStore
from services.cases.store import CaseService, PostgresCaseStore, RedisCaseStore


_gateway: EcommerceGateway | None = None
_memory_store: PostgresBaseStore | None = None
_semantic_memory_service: SemanticMemoryService | None = None
_case_service: CaseService | None = None


def _resolve_auth_header(authorization: str | None, cookie_token: str | None) -> str | None:
    """Prefer an explicit integration header, then use the HttpOnly Mall login cookie."""

    if authorization:
        return authorization
    if cookie_token:
        return f"Bearer {cookie_token}"
    return None


def get_gateway(
    authorization: Annotated[str | None, Header()] = None,
    mall_access_token: Annotated[str | None, Cookie()] = None,
) -> EcommerceGateway:
    """提供电商网关依赖。
    当前只支持真实 mall HTTP 适配器，避免售后 Agent 继续依赖本地模拟数据。
    """

    gateway_name = os.getenv("ECOMMERCE_GATEWAY", AppConfig.ECOMMERCE_GATEWAY).strip().lower()
    if gateway_name == "mall":
        auth_header = _resolve_auth_header(authorization, mall_access_token)
        if auth_header and not auth_header.startswith("Bearer "):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Authorization 必须使用 Bearer token",
            )
        if not auth_header and MallConfig.AUTH_TOKEN:
            auth_header = f"Bearer {MallConfig.AUTH_TOKEN}"
        return MallEcommerceGateway(auth_header=auth_header)
    else:
        raise ValueError(f"不支持的电商网关配置：{gateway_name}")


def get_idempotency_store():
    return get_redis_idempotency_store()


def reset_gateway_cache() -> None:
    """测试或运行时切换配置后，清理已创建的网关实例。"""
    global _gateway
    _gateway = None


async def get_memory_store() -> PostgresBaseStore:
    """提供用户长期记忆仓储。
    配置 `DATABASE_URL` 时使用 PostgreSQL；未配置时使用内存仓储。
    """

    global _memory_store
    if _memory_store is None:
        engine = await SqlAlchemyPool.get()
        _memory_store = PostgresBaseStore(engine)
    return _memory_store


async def get_case_service() -> CaseService:
    """提供独立于用户偏好的售后 Case 存储服务。"""

    global _case_service
    if _case_service is None:
        engine = await SqlAlchemyPool.get()
        _case_service = CaseService(
            hot_store=RedisCaseStore(),
            durable_store=PostgresCaseStore(engine),
        )
    return _case_service


async def get_checkpointer():
    return await checkpoint_manager.start()


async def get_main_agent(checkpointer=Depends(get_checkpointer)):
    """构建使用 Redis 检查点的 Deep Agent 主图。"""

    return build_main_agent(checkpointer)


async def get_semantic_memory_service() -> SemanticMemoryService:
    global _semantic_memory_service
    if _semantic_memory_service is None:
        client = await MilvusClient.get_client()
        vectorizer = BgeM3Vectorizer()

        async def embed(text: str) -> list[float]:
            records = await asyncio.to_thread(
                vectorizer.vectorize, [DocumentChunk(text=text, metadata={})]
            )
            return records[0].embedding

        _semantic_memory_service = SemanticMemoryService(
            store=MilvusBaseStore(
                client=client,
                collection_name=MilvusConfig.MEMORY_COLLECTION,
                dimension=EmbeddingConfig.DIMENSION,
            ),
            embed=embed,
            compressor=ConversationCompressor(OpenAIConversationSummarizer()),
        )
    return _semantic_memory_service


async def close_dependencies() -> None:
    """关闭所有依赖资源。"""
    global _memory_store, _semantic_memory_service, _case_service
    await SqlAlchemyPool.close()
    await RedisClient.close()
    await MilvusClient.close()
    _memory_store = None
    _semantic_memory_service = None
    _case_service = None
