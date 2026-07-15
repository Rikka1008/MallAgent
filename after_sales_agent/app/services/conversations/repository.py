from __future__ import annotations

import logging
import re
from datetime import datetime, timedelta
from uuid import uuid4

from pydantic import ValidationError
from sqlalchemy import (
    Column,
    DateTime,
    Integer,
    MetaData,
    SmallInteger,
    String,
    Table,
    Text,
    case,
    delete,
    func,
    or_,
    select,
    update,
)
from sqlalchemy.dialects.postgresql import JSONB, insert

from config import ConversationConfig
from core.database.redis_client import RedisClient
from services.conversations.models import (
    CloseReason,
    ConversationRecord,
    ConversationStatus,
    ConversationSummary,
    ConversationTurn,
    SummaryStatus,
)


logger = logging.getLogger("after_sales.conversations.repository")


def sanitize_summary_error(error: BaseException | str) -> str:
    """仅持久化有界单行错误，避免日志列携带正文或多行堆栈。"""

    if isinstance(error, BaseException):
        return f"{type(error).__name__}: summary generation failed"
    message = re.sub(r"\s+", " ", str(error)).strip()
    return message[:1000] or "unknown summary error"


class ConversationRepository:
    """PostgreSQL 会话生命周期仓储；表结构由 Alembic 独占管理。"""

    def __init__(self, engine, retention_days: int | None = None):
        self.engine = engine
        self.retention_days = retention_days or ConversationConfig.SUMMARY_RETENTION_DAYS
        self.metadata = MetaData()
        self.table = Table(
            "agent_conversations",
            self.metadata,
            Column("conversation_id", String(128), primary_key=True),
            Column("user_id", String(128), nullable=False),
            Column("status", String(16), nullable=False),
            Column("summary_status", String(16), nullable=False),
            Column("close_reason", String(32)),
            Column("message_count", Integer, nullable=False),
            Column("summary_text", Text),
            Column("summary_json", JSONB, nullable=False),
            Column("summary_version", SmallInteger, nullable=False),
            Column("summary_attempts", SmallInteger, nullable=False),
            Column("next_summary_attempt_at", DateTime(timezone=True)),
            Column("last_error", String(1000)),
            Column("last_active_at", DateTime(timezone=True), nullable=False),
            Column("closed_at", DateTime(timezone=True)),
            Column("expires_at", DateTime(timezone=True)),
            Column("created_at", DateTime(timezone=True), nullable=False),
            Column("updated_at", DateTime(timezone=True), nullable=False),
        )

    @staticmethod
    def _record(row) -> ConversationRecord | None:
        return ConversationRecord.model_validate(dict(row)) if row is not None else None

    async def create_active(
        self,
        user_id: str,
        now: datetime,
        close_reason: CloseReason = CloseReason.USER_NEW_SESSION,
    ) -> ConversationRecord:
        conversation_id = f"C-{uuid4().hex}"
        expires_at = now + timedelta(days=self.retention_days)
        values = {
            "conversation_id": conversation_id,
            "user_id": user_id,
            "status": ConversationStatus.ACTIVE.value,
            "summary_status": SummaryStatus.NOT_STARTED.value,
            "close_reason": None,
            "message_count": 0,
            "summary_text": None,
            "summary_json": {},
            "summary_version": 1,
            "summary_attempts": 0,
            "next_summary_attempt_at": None,
            "last_error": None,
            "last_active_at": now,
            "closed_at": None,
            "expires_at": None,
            "created_at": now,
            "updated_at": now,
        }
        async with self.engine.begin() as connection:
            await connection.execute(
                select(
                    func.pg_advisory_xact_lock(func.hashtextextended(user_id, 0))
                )
            )
            await connection.execute(
                update(self.table)
                .where(
                    self.table.c.user_id == user_id,
                    self.table.c.status == ConversationStatus.ACTIVE.value,
                )
                .values(
                    status=ConversationStatus.CLOSED.value,
                    summary_status=SummaryStatus.PENDING.value,
                    close_reason=close_reason.value,
                    next_summary_attempt_at=now,
                    closed_at=now,
                    expires_at=expires_at,
                    updated_at=now,
                )
            )
            result = await connection.execute(insert(self.table).values(**values).returning(self.table))
            row = result.mappings().one()
        return self._record(row)

    async def get_active(self, user_id: str, idle_after: datetime) -> ConversationRecord | None:
        async with self.engine.begin() as connection:
            result = await connection.execute(
                select(self.table).where(
                    self.table.c.user_id == user_id,
                    self.table.c.status == ConversationStatus.ACTIVE.value,
                    self.table.c.last_active_at > idle_after,
                )
            )
            row = result.mappings().first()
        return self._record(row)

    async def get_owned(self, conversation_id: str, user_id: str) -> ConversationRecord | None:
        async with self.engine.begin() as connection:
            result = await connection.execute(
                select(self.table).where(
                    self.table.c.conversation_id == conversation_id,
                    self.table.c.user_id == user_id,
                )
            )
            row = result.mappings().first()
        return self._record(row)

    async def touch(
        self,
        conversation_id: str,
        user_id: str,
        now: datetime,
        message_delta: int = 2,
    ) -> ConversationRecord | None:
        statement = (
            update(self.table)
            .where(
                self.table.c.conversation_id == conversation_id,
                self.table.c.user_id == user_id,
                self.table.c.status == ConversationStatus.ACTIVE.value,
            )
            .values(
                last_active_at=now,
                message_count=self.table.c.message_count + message_delta,
                updated_at=now,
            )
            .returning(self.table)
        )
        async with self.engine.begin() as connection:
            result = await connection.execute(statement)
            row = result.mappings().first()
        return self._record(row)

    async def close(
        self,
        conversation_id: str,
        user_id: str,
        reason: CloseReason,
        now: datetime,
    ) -> ConversationRecord | None:
        statement = (
            update(self.table)
            .where(
                self.table.c.conversation_id == conversation_id,
                self.table.c.user_id == user_id,
                self.table.c.status == ConversationStatus.ACTIVE.value,
            )
            .values(
                status=ConversationStatus.CLOSED.value,
                summary_status=SummaryStatus.PENDING.value,
                close_reason=reason.value,
                next_summary_attempt_at=now,
                closed_at=now,
                expires_at=now + timedelta(days=self.retention_days),
                updated_at=now,
            )
            .returning(self.table)
        )
        async with self.engine.begin() as connection:
            result = await connection.execute(statement)
            row = result.mappings().first()
        return self._record(row)

    async def claim_due(
        self,
        now: datetime,
        idle_before: datetime,
        limit: int = 20,
    ) -> list[ConversationRecord]:
        expires_at = now + timedelta(days=self.retention_days)
        stale_claim_before = now - timedelta(
            seconds=max(60, ConversationConfig.FINALIZER_INTERVAL_SECONDS * 2)
        )
        async with self.engine.begin() as connection:
            await connection.execute(
                update(self.table)
                .where(
                    self.table.c.status == ConversationStatus.CLOSED.value,
                    self.table.c.summary_status == SummaryStatus.PROCESSING.value,
                    self.table.c.updated_at <= stale_claim_before,
                )
                .values(
                    summary_status=SummaryStatus.FAILED.value,
                    next_summary_attempt_at=case(
                        (
                            self.table.c.summary_attempts
                            < ConversationConfig.SUMMARY_MAX_ATTEMPTS,
                            now,
                        ),
                        else_=None,
                    ),
                    last_error="stale summary claim recovered",
                    updated_at=now,
                )
            )
            await connection.execute(
                update(self.table)
                .where(
                    self.table.c.status == ConversationStatus.ACTIVE.value,
                    self.table.c.last_active_at <= idle_before,
                )
                .values(
                    status=ConversationStatus.CLOSED.value,
                    summary_status=SummaryStatus.PENDING.value,
                    close_reason=CloseReason.IDLE_TIMEOUT.value,
                    next_summary_attempt_at=now,
                    closed_at=now,
                    expires_at=expires_at,
                    updated_at=now,
                )
            )
            due = (
                select(self.table)
                .where(
                    self.table.c.status == ConversationStatus.CLOSED.value,
                    self.table.c.summary_status.in_([
                        SummaryStatus.PENDING.value,
                        SummaryStatus.FAILED.value,
                    ]),
                    or_(
                        self.table.c.next_summary_attempt_at.is_(None),
                        self.table.c.next_summary_attempt_at <= now,
                    ),
                    self.table.c.summary_attempts < ConversationConfig.SUMMARY_MAX_ATTEMPTS,
                )
                .order_by(self.table.c.closed_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
            result = await connection.execute(due)
            rows = list(result.mappings().all())
            ids = [row["conversation_id"] for row in rows]
            if not ids:
                return []
            claimed = await connection.execute(
                update(self.table)
                .where(self.table.c.conversation_id.in_(ids))
                .values(
                    summary_status=SummaryStatus.PROCESSING.value,
                    summary_attempts=self.table.c.summary_attempts + 1,
                    next_summary_attempt_at=None,
                    last_error=None,
                    updated_at=now,
                )
                .returning(self.table)
            )
            claimed_rows = claimed.mappings().all()
        return [self._record(row) for row in claimed_rows]

    async def complete_summary(
        self,
        conversation_id: str,
        summary: ConversationSummary,
        summary_text: str,
        now: datetime,
    ) -> None:
        await self._execute(
            update(self.table)
            .where(self.table.c.conversation_id == conversation_id)
            .values(
                summary_status=SummaryStatus.COMPLETED.value,
                summary_text=summary_text,
                summary_json=summary.model_dump(mode="json"),
                summary_version=summary.schema_version,
                next_summary_attempt_at=None,
                last_error=None,
                updated_at=now,
            )
        )

    async def fail_summary(
        self,
        conversation_id: str,
        error: BaseException | str,
        retry_at: datetime | None,
        now: datetime,
    ) -> None:
        await self._execute(
            update(self.table)
            .where(self.table.c.conversation_id == conversation_id)
            .values(
                summary_status=SummaryStatus.FAILED.value,
                next_summary_attempt_at=retry_at,
                last_error=sanitize_summary_error(error),
                updated_at=now,
            )
        )

    async def list_recent_summaries(
        self,
        user_id: str,
        now: datetime,
        limit: int,
    ) -> list[ConversationRecord]:
        statement = (
            select(self.table)
            .where(
                self.table.c.user_id == user_id,
                self.table.c.status == ConversationStatus.CLOSED.value,
                self.table.c.summary_status == SummaryStatus.COMPLETED.value,
                self.table.c.expires_at > now,
            )
            .order_by(self.table.c.closed_at.desc())
            .limit(limit)
        )
        async with self.engine.begin() as connection:
            result = await connection.execute(statement)
            rows = result.mappings().all()
        return [self._record(row) for row in rows]

    async def delete_expired(self, now: datetime, limit: int = 100) -> list[str]:
        async with self.engine.begin() as connection:
            result = await connection.execute(
                select(self.table.c.conversation_id)
                .where(
                    self.table.c.status == ConversationStatus.CLOSED.value,
                    self.table.c.expires_at <= now,
                )
                .order_by(self.table.c.expires_at)
                .limit(limit)
            )
            ids = list(result.scalars().all())
            if ids:
                await connection.execute(
                    delete(self.table).where(self.table.c.conversation_id.in_(ids))
                )
        return ids

    async def _execute(self, statement) -> None:
        async with self.engine.begin() as connection:
            await connection.execute(statement)


class RedisConversationRepository:
    """活跃会话的规范化轮次存储，不保存系统提示词或工具中间消息。"""

    def __init__(self, client=None, ttl_seconds: int | None = None):
        self.client = client
        self.ttl_seconds = ttl_seconds or ConversationConfig.REDIS_TTL_SECONDS

    async def _client(self):
        return self.client or await RedisClient.get()

    @staticmethod
    def _key(conversation_id: str) -> str:
        return f"after_sales:conversation:{conversation_id}:turns"

    @staticmethod
    def _lease_key(conversation_id: str) -> str:
        return f"after_sales:conversation:{conversation_id}:inflight"

    async def acquire_lease(self, conversation_id: str) -> str | None:
        token = uuid4().hex
        acquired = await (await self._client()).set(
            self._lease_key(conversation_id),
            token,
            ex=ConversationConfig.IDLE_TIMEOUT_SECONDS,
            nx=True,
        )
        return token if acquired else None

    async def release_lease(self, conversation_id: str, token: str) -> None:
        script = """
        if redis.call('get', KEYS[1]) == ARGV[1] then
            return redis.call('del', KEYS[1])
        end
        return 0
        """
        await (await self._client()).eval(
            script,
            1,
            self._lease_key(conversation_id),
            token,
        )

    async def append_turn(self, conversation_id: str, turn: ConversationTurn) -> None:
        client = await self._client()
        key = self._key(conversation_id)
        pipeline = client.pipeline(transaction=True)
        pipeline.rpush(key, turn.model_dump_json())
        pipeline.expire(key, self.ttl_seconds)
        await pipeline.execute()

    async def list_turns(self, conversation_id: str) -> list[ConversationTurn]:
        client = await self._client()
        key = self._key(conversation_id)
        values = await client.lrange(key, 0, -1)
        if values:
            await client.expire(key, self.ttl_seconds)
        turns: list[ConversationTurn] = []
        for value in values:
            try:
                turns.append(ConversationTurn.model_validate_json(value))
            except (ValidationError, ValueError, TypeError):
                logger.warning("忽略无效会话轮次 conversation_id=%s", conversation_id)
        return turns

    async def delete_turns(self, conversation_id: str) -> None:
        await (await self._client()).delete(self._key(conversation_id))

    async def refresh_turns(self, conversation_id: str) -> None:
        await (await self._client()).expire(self._key(conversation_id), self.ttl_seconds)
