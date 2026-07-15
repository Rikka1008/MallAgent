from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
from typing import Callable

from config import ConversationConfig
from services.conversations.models import (
    ConversationRecord,
    ConversationStatus,
    ConversationTurn,
)


class ConversationUnavailableError(RuntimeError):
    """会话不存在、不属于当前用户、已关闭或已逻辑过期。"""


class ConversationBusyError(RuntimeError):
    """会话正在处理请求，不能同时关闭或复用。"""


logger = logging.getLogger("after_sales.conversations.lifecycle")


class ConversationLifecycle:
    def __init__(self, repository, turns, clock: Callable[[], datetime] | None = None):
        self.repository = repository
        self.turns = turns
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def _idle_after(self, now: datetime) -> datetime:
        return now - timedelta(seconds=ConversationConfig.IDLE_TIMEOUT_SECONDS)

    async def get_active(self, user_id: str) -> ConversationRecord | None:
        now = self.clock()
        # GET 是纯查询：不 touch，也不隐式创建或关闭会话。
        return await self.repository.get_active(user_id, self._idle_after(now))

    async def create_new(self, user_id: str) -> ConversationRecord:
        now = self.clock()
        active = await self.repository.get_active(user_id, self._idle_after(now))
        if active is None:
            return await self.repository.create_active(user_id, now)
        token = await self.turns.acquire_lease(active.conversation_id)
        if token is None:
            raise ConversationBusyError("当前会话正在处理请求，请完成后再新建会话。")
        try:
            return await self.repository.create_active(user_id, now)
        finally:
            try:
                await self.turns.release_lease(active.conversation_id, token)
            except Exception:
                logger.warning(
                    "新建会话后释放旧会话租约失败 conversation_id=%s",
                    active.conversation_id,
                )

    async def require_active(
        self, conversation_id: str, user_id: str
    ) -> ConversationRecord:
        now = self.clock()
        conversation = await self.repository.get_owned(conversation_id, user_id)
        if (
            conversation is None
            or conversation.status != ConversationStatus.ACTIVE
            or conversation.last_active_at <= self._idle_after(now)
        ):
            raise ConversationUnavailableError("会话已结束，请重新发送消息。")
        return conversation

    async def begin_turn(self, conversation_id: str, user_id: str) -> str:
        """在调用 Agent 前续租，避免终结器关闭正在处理的会话。"""

        await self.require_active(conversation_id, user_id)
        token = await self.turns.acquire_lease(conversation_id)
        if token is None:
            raise ConversationBusyError("当前会话正在处理另一条消息，请稍后再试。")
        try:
            updated = await self.repository.touch(
                conversation_id,
                user_id,
                self.clock(),
                message_delta=0,
            )
            if updated is None:
                raise ConversationUnavailableError("会话已结束，请重新发送消息。")
            return token
        except Exception:
            await self.turns.release_lease(conversation_id, token)
            raise

    async def release_turn(self, conversation_id: str, token: str) -> None:
        await self.turns.release_lease(conversation_id, token)

    async def record_turn(
        self,
        conversation_id: str,
        user_id: str,
        turn: ConversationTurn,
    ) -> None:
        now = self.clock()
        await self.require_active(conversation_id, user_id)
        await self.turns.append_turn(conversation_id, turn)
        updated = await self.repository.touch(
            conversation_id,
            user_id,
            now,
            message_delta=2,
        )
        if updated is None:
            raise ConversationUnavailableError("会话已结束，请重新发送消息。")

    async def recall(self, user_id: str) -> list[ConversationRecord]:
        return await self.repository.list_recent_summaries(
            user_id,
            self.clock(),
            ConversationConfig.RECALL_LIMIT,
        )
