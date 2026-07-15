"""生产依赖就绪检查。"""

from __future__ import annotations

from config import AppConfig, LlmConfig, MallConfig, MilvusConfig, RedisConfig
from core.database.milvus_client import MilvusClient
from core.database.redis_client import RedisClient


async def check_readiness() -> dict[str, dict]:
    """返回不含凭据的外部依赖状态。"""

    return {
        "llm": await _check_llm(),
        "redis": await _check_redis(),
        "milvus": await _check_milvus(),
        "mall": await _check_mall(),
    }


async def require_ready() -> None:
    """生产环境发现任一依赖失败时阻止服务就绪。"""

    if AppConfig.APP_ENV != "production":
        return
    result = await check_readiness()
    failed = [name for name, item in result.items() if item["status"] != "ok"]
    if failed:
        raise RuntimeError(f"生产依赖未就绪：{', '.join(failed)}")


async def _check_llm() -> dict:
    try:
        LlmConfig.require_main_model()
        return {"status": "ok"}
    except RuntimeError as exc:
        return {"status": "failed", "detail": str(exc)}


async def _check_redis() -> dict:
    try:
        RedisConfig.require_url()
        await (await RedisClient.get()).ping()
        return {"status": "ok"}
    except Exception:
        return {"status": "failed", "detail": "Redis 不可用"}


async def _check_milvus() -> dict:
    try:
        MilvusConfig.require_uri()
        client = await MilvusClient.get_client()
        for collection in (MilvusConfig.PRODUCT_COLLECTION, MilvusConfig.POLICY_COLLECTION):
            if hasattr(client, "has_collection") and not await client.has_collection(
                collection_name=collection
            ):
                return {"status": "failed", "detail": f"集合不存在：{collection}"}
        return {"status": "ok"}
    except Exception:
        return {"status": "failed", "detail": "Milvus 不可用"}


async def _check_mall() -> dict:
    try:
        MallConfig.require_portal_url()
        MallConfig.require_admin_url()
        return {"status": "ok"}
    except RuntimeError as exc:
        return {"status": "failed", "detail": str(exc)}
