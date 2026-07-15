from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any
import asyncio

from core.database.milvus_client import MilvusClient as AsyncMilvusClientFactory


@dataclass(eq=True)
class SmokeResult:
    component: str
    ok: bool
    detail: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return redact(asdict(self))


def redact(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            key: "***" if key.lower() in {"token", "password", "secret", "api_key"} else redact(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact(item) for item in value]
    return value


async def run_rag_check(retriever, query: str) -> SmokeResult:
    hits = await retriever.search(query, limit=3)
    return SmokeResult(
        component="rag",
        ok=bool(hits),
        detail={
            "hit_count": len(hits),
            "titles": [str(hit.get("title") or "知识库片段") for hit in hits],
        },
    )


async def run_with_timeout(
    component: str,
    operation,
    timeout_seconds: float = 10,
) -> SmokeResult:
    try:
        return await asyncio.wait_for(operation, timeout=timeout_seconds)
    except TimeoutError:
        return SmokeResult(component, False, {"error": "timeout"})


async def check_postgres(database_url: str) -> SmokeResult:
    from sqlalchemy import text
    from sqlalchemy.ext.asyncio import create_async_engine

    from core.database.url import normalize_async_database_url

    engine = create_async_engine(normalize_async_database_url(database_url))
    try:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))
            revision = await connection.scalar(text("SELECT version_num FROM alembic_version"))
            conversation_table = await connection.scalar(
                text("SELECT to_regclass('public.agent_conversations')")
            )
        schema_ready = conversation_table == "agent_conversations"
        return SmokeResult(
            "postgres",
            schema_ready,
            {
                "alembic_revision": revision,
                "agent_conversations": schema_ready,
            },
        )
    except Exception as exc:
        return SmokeResult("postgres", False, {"error": type(exc).__name__})
    finally:
        await engine.dispose()


async def check_redis(redis_url: str) -> SmokeResult:
    try:
        from redis.asyncio import from_url

        client = from_url(redis_url)
        try:
            ok = bool(await client.ping())
        finally:
            await client.aclose()
        return SmokeResult("redis", ok, {"ping": ok})
    except Exception as exc:
        return SmokeResult("redis", False, {"error": type(exc).__name__})


def check_milvus(
    uri: str,
    token: str | None,
    db_name: str,
    collection: str,
    expected_dimension: int | None = None,
    client=None,
) -> SmokeResult:
    try:
        from pymilvus import MilvusClient

        client = client or MilvusClient(uri=uri, token=token, db_name=db_name, timeout=2)
        exists = bool(client.has_collection(collection_name=collection))
        detail: dict[str, Any] = {"collection": collection, "exists": exists}
        if exists:
            description = client.describe_collection(collection_name=collection)
            detail["dimension"] = next(
                (
                    field.get("params", {}).get("dim")
                    for field in description.get("fields", [])
                    if field.get("name") == "embedding"
                ),
                None,
            )
            if expected_dimension is not None:
                detail["expected_dimension"] = expected_dimension
        dimension_matches = expected_dimension is None or detail.get("dimension") == expected_dimension
        return SmokeResult("milvus", exists and dimension_matches, detail)
    except Exception as exc:
        return SmokeResult("milvus", False, {"error": type(exc).__name__})


async def check_milvus_async(
    uri: str,
    token: str | None,
    db_name: str,
    collection: str,
    expected_dimension: int | None = None,
    client=None,
) -> SmokeResult:
    try:
        client = client or AsyncMilvusClientFactory.create(
            uri=uri,
            token=token,
            db_name=db_name,
            timeout=2,
        )
        exists = bool(await client.has_collection(collection_name=collection))
        detail: dict[str, Any] = {"collection": collection, "exists": exists}
        if exists:
            description = await client.describe_collection(collection_name=collection)
            detail["dimension"] = next(
                (
                    field.get("params", {}).get("dim")
                    for field in description.get("fields", [])
                    if field.get("name") == "embedding"
                ),
                None,
            )
            if expected_dimension is not None:
                detail["expected_dimension"] = expected_dimension
        dimension_matches = expected_dimension is None or detail.get("dimension") == expected_dimension
        return SmokeResult("milvus", exists and dimension_matches, detail)
    except Exception as exc:
        return SmokeResult("milvus", False, {"error": type(exc).__name__})
