from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Column, DateTime, MetaData, String, Table, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.dialects.postgresql import JSONB


@dataclass(frozen=True)
class MemoryItem:
    namespace: tuple[str, ...]
    key: str
    value: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class MilvusBaseStore:
    """Milvus-backed semantic memory store, scoped by LangGraph namespace."""

    def __init__(self, client, collection_name: str, dimension: int):
        self.client = client
        self.collection_name = collection_name
        self.dimension = dimension

    async def put(self, namespace: tuple[str, ...], key: str, value: dict[str, Any]) -> None:
        """将会话摘要存储到向量存储中"""
        await self._ensure_collection()
        now = datetime.now(timezone.utc).isoformat()
        await self.client.upsert(
            collection_name=self.collection_name,
            data=[{
                "memory_id": self._id(namespace, key), "namespace": list(namespace),
                "user_id": namespace[0], "key": key, "content": value["content"],
                "embedding": value["embedding"], "value": json.dumps(value, ensure_ascii=False),
                "updated_at": now,
            }],
        )

    async def search(self, namespace: tuple[str, ...], embedding: list[float], limit: int = 5):
        if not await self.client.has_collection(collection_name=self.collection_name):
            return []
        rows = await self.client.search(
            collection_name=self.collection_name, data=[embedding], anns_field="embedding",
            filter=f"user_id == '{namespace[0]}'",
            limit=limit,
            output_fields=["namespace", "key", "value", "updated_at"],
        )
        if rows and isinstance(rows[0], list):
            rows = rows[0]
        now = datetime.now(timezone.utc)
        items = []
        for row in rows:
            entity = row.get("entity", row)
            if tuple(entity.get("namespace", ())) != namespace:
                continue
            value = entity["value"]
            if isinstance(value, str):
                value = json.loads(value)
            items.append(MemoryItem(namespace, entity["key"], value, now, now))
        return items

    async def _ensure_collection(self):
        if await self.client.has_collection(collection_name=self.collection_name):
            return
        await self.client.create_collection(
            collection_name=self.collection_name, dimension=self.dimension,
            primary_field_name="memory_id", id_type="string", max_length=256,
            vector_field_name="embedding", metric_type="COSINE", auto_id=False,
            enable_dynamic_field=True,
        )

    @staticmethod
    def _id(namespace: tuple[str, ...], key: str) -> str:
        return ":".join((*namespace, key))


class PostgresBaseStore:
    """
    使用 SQLAlchemy AsyncEngine 进行异步数据库操作，依赖外部迁移创建 agent_memories 表。
    """

    def __init__(self, engine):
        self.engine = engine
        self.metadata = MetaData()
        self.table = Table(
            "agent_memories", self.metadata,
            Column("namespace", String(256), primary_key=True),
            Column("memory_key", String(128), primary_key=True),
            Column("value", JSONB, nullable=False),
            Column("updated_at", DateTime(timezone=True), nullable=False),
        )

    async def put(self, namespace: tuple[str, ...], key: str, value: dict[str, Any]) -> None:
        """存储或更新用户记忆。"""
        values = {
            "namespace": "/".join(namespace),
            "memory_key": key,
            "value": value,
            "updated_at": datetime.now(timezone.utc),
        }
        statement = insert(self.table).values(**values).on_conflict_do_update(
            index_elements=["namespace", "memory_key"],
            set_={"value": value, "updated_at": values["updated_at"]},
        )
        async with self.engine.begin() as connection:
            await connection.execute(statement)

    async def get(self, namespace: tuple[str, ...], key: str) -> MemoryItem | None:
        """读取用户记忆。"""
        async with self.engine.begin() as connection:
            result = await connection.execute(
                select(self.table).where(
                    self.table.c.namespace == "/".join(namespace),
                    self.table.c.memory_key == key,
                )
            )
            row = result.mappings().first()

        if row is None:
            return None

        return MemoryItem(
            namespace=namespace,
            key=key,
            value=row["value"],
            created_at=row["updated_at"],
            updated_at=row["updated_at"],
        )
