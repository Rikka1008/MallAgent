from __future__ import annotations

from typing import Protocol
from uuid import uuid4

from sqlalchemy import Column, DateTime, Integer, MetaData, String, Table, select
from sqlalchemy.dialects.postgresql import JSONB, insert
from sqlalchemy.sql import func

from config import RedisConfig
from core.database.redis_client import RedisClient
from services.cases.context import AfterSalesCase


class CaseStore(Protocol):
    async def get(self, case_id: str) -> AfterSalesCase | None: ...

    async def put(self, case: AfterSalesCase) -> None: ...


class RedisCaseStore:
    """短期 Case 热存储，用于跨消息保留当前售后事项。"""

    def __init__(self, prefix: str = "after_sales:case:", ttl_seconds: int | None = None):
        self.prefix = prefix
        self.ttl_seconds = ttl_seconds or RedisConfig.SESSION_TTL_SECONDS

    async def _client(self):
        return await RedisClient.get()

    def _key(self, case_id: str) -> str:
        return f"{self.prefix}{case_id}"

    async def get(self, case_id: str) -> AfterSalesCase | None:
        raw = await (await self._client()).get(self._key(case_id))
        return AfterSalesCase.model_validate_json(raw) if raw else None

    async def put(self, case: AfterSalesCase) -> None:
        await (await self._client()).set(
            self._key(case.case_id),
            case.model_dump_json(),
            ex=self.ttl_seconds,
        )


class PostgresCaseStore:
    """售后 Case 的可恢复快照；与用户偏好表完全隔离。"""

    def __init__(self, engine):
        self.engine = engine
        self.metadata = MetaData()
        self.table = Table(
            "after_sales_cases",
            self.metadata,
            Column("case_id", String(128), primary_key=True),
            Column("user_id", String(128), nullable=False),
            Column("session_id", String(128), nullable=False),
            Column("status", String(48), nullable=False),
            Column("snapshot", JSONB, nullable=False),
            Column("version", Integer, nullable=False),
            Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
            Column("updated_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
        )
        self.events_table = Table(
            "after_sales_case_events",
            self.metadata,
            Column("event_id", String(36), primary_key=True),
            Column("case_id", String(128), nullable=False),
            Column("event_type", String(64), nullable=False),
            Column("payload", JSONB, nullable=False),
            Column("created_at", DateTime(timezone=True), nullable=False, server_default=func.now()),
        )

    async def get(self, case_id: str) -> AfterSalesCase | None:
        async with self.engine.begin() as connection:
            result = await connection.execute(
                select(self.table.c.snapshot).where(self.table.c.case_id == case_id)
            )
            snapshot = result.scalar_one_or_none()
        return AfterSalesCase.model_validate(snapshot) if snapshot else None

    async def put(self, case: AfterSalesCase) -> None:
        snapshot = case.model_dump(mode="json")
        values = {
            "case_id": case.case_id,
            "user_id": case.user_id,
            "session_id": case.session_id,
            "status": case.stage.value,
            "snapshot": snapshot,
            "version": case.version,
        }
        statement = insert(self.table).values(**values).on_conflict_do_update(
            index_elements=["case_id"],
            set_={
                "status": values["status"],
                "snapshot": values["snapshot"],
                "version": values["version"],
                "updated_at": func.now(),
            },
        )
        async with self.engine.begin() as connection:
            await connection.execute(statement)

    async def record_event(
        self, case_id: str, event_type: str, payload: dict
    ) -> None:
        async with self.engine.begin() as connection:
            await connection.execute(
                insert(self.events_table).values(
                    event_id=str(uuid4()),
                    case_id=case_id,
                    event_type=event_type,
                    payload=payload,
                )
            )


class CaseService:
    """Redis 优先、PostgreSQL 兜底的 Case 协调器。"""

    def __init__(self, hot_store: CaseStore, durable_store: CaseStore):
        self.hot_store = hot_store
        self.durable_store = durable_store

    @staticmethod
    def case_id_for(user_id: str, session_id: str) -> str:
        return f"active:{user_id}:{session_id}"

    async def get_or_create(self, user_id: str, session_id: str) -> AfterSalesCase:
        case_id = self.case_id_for(user_id, session_id)
        case = await self.hot_store.get(case_id)
        if case is not None:
            return case
        case = await self.durable_store.get(case_id)
        if case is not None:
            await self.hot_store.put(case)
            return case
        return AfterSalesCase(case_id=case_id, user_id=user_id, session_id=session_id)

    async def save(self, case: AfterSalesCase) -> None:
        case.version += 1
        await self.durable_store.put(case)
        record_event = getattr(self.durable_store, "record_event", None)
        if record_event is not None:
            await record_event(
                case.case_id,
                "case_saved",
                {"stage": case.stage.value, "version": case.version},
            )
        await self.hot_store.put(case)
