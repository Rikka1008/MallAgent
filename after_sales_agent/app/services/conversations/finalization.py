from __future__ import annotations

import asyncio
import json
import logging
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta, timezone

import httpx

from config import ConversationConfig, LlmConfig
from services.conversations.models import ConversationSummary, ConversationTurn


logger = logging.getLogger("after_sales.conversations.finalization")
SummaryGenerator = Callable[[list[ConversationTurn]], Awaitable[dict | str]]


class ConversationSummarizer:
    """把规范化轮次转换为经过严格校验的第 1 版业务摘要。"""

    def __init__(self, generate: SummaryGenerator | None = None):
        self.generate = generate or self._generate_with_llm

    async def summarize(self, turns: list[ConversationTurn]) -> ConversationSummary:
        raw = await self.generate(turns)
        payload = self._parse_payload(raw)
        summary = ConversationSummary.model_validate(payload)
        corpus = "\n".join(
            f"用户：{turn.user_text}\n助手：{turn.assistant_text}" for turn in turns
        )
        # 编号只允许从原文逐字召回，模型新造的业务 ID 会被剔除。
        for field in ("order_ids", "after_sales_ids", "product_ids"):
            setattr(summary, field, [value for value in getattr(summary, field) if value in corpus])
        return summary

    @staticmethod
    def _parse_payload(raw: dict | str) -> dict:
        if isinstance(raw, dict):
            return raw
        text = raw.strip()
        if text.startswith("```"):
            lines = text.splitlines()
            text = "\n".join(lines[1:-1])
            if text.lstrip().startswith("json"):
                text = text.lstrip()[4:].lstrip()
        value = json.loads(text)
        if not isinstance(value, dict):
            raise ValueError("会话摘要必须是 JSON 对象")
        return value

    @staticmethod
    def render(summary: ConversationSummary) -> str:
        parts = []
        if summary.session_intent:
            parts.append(f"会话意图：{summary.session_intent}")
        if summary.order_ids:
            parts.append(f"相关订单：{', '.join(summary.order_ids)}")
        if summary.after_sales_ids:
            parts.append(f"相关售后单：{', '.join(summary.after_sales_ids)}")
        if summary.completed_actions:
            parts.append(f"已完成：{'；'.join(summary.completed_actions)}")
        if summary.pending_actions:
            parts.append(f"待处理：{'；'.join(summary.pending_actions)}")
        if summary.last_user_request:
            parts.append(f"用户最后诉求：{summary.last_user_request}")
        return "\n".join(parts)[:4000]

    async def _generate_with_llm(self, turns: list[ConversationTurn]) -> dict | str:
        config = LlmConfig.require_main_model()
        transcript = "\n\n".join(
            f"用户：{turn.user_text}\n助手：{turn.assistant_text}" for turn in turns
        )
        schema = ConversationSummary.model_json_schema()
        payload = {
            "model": config["model"],
            "temperature": 0,
            "max_tokens": min(config["max_tokens"], 1200),
            "response_format": {"type": "json_object"},
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "将商城售后对话整理为事实性 JSON 摘要。禁止推测或新增编号；"
                        "只输出 JSON 对象，必须符合此 schema："
                        + json.dumps(schema, ensure_ascii=False)
                    ),
                },
                {"role": "user", "content": transcript},
            ],
        }
        async with httpx.AsyncClient(
            timeout=config["request_timeout_seconds"], trust_env=False
        ) as client:
            response = await client.post(
                f"{config['base_url'].rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {config['api_key']}"},
                json=payload,
            )
            response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]


class ConversationFinalizer:
    """认领超时会话、生成最终摘要、重试并清理过期数据。"""

    def __init__(self, repository, turns, summarizer: ConversationSummarizer, clock=None):
        self.repository = repository
        self.turns = turns
        self.summarizer = summarizer
        self.clock = clock or (lambda: datetime.now(timezone.utc))
        self._stop_event: asyncio.Event | None = None
        self._task: asyncio.Task | None = None

    async def run_once(self) -> None:
        now = self.clock()
        idle_before = now - timedelta(seconds=ConversationConfig.IDLE_TIMEOUT_SECONDS)
        records = await self.repository.claim_due(now, idle_before, limit=20)
        for record in records:
            try:
                turns = await self.turns.list_turns(record.conversation_id)
                summary = await self.summarizer.summarize(turns)
                summary_text = self.summarizer.render(summary)
                await self.repository.complete_summary(
                    record.conversation_id, summary, summary_text, now
                )
            except Exception as exc:
                retry_at = self._retry_at(now, record.summary_attempts)
                await self.repository.fail_summary(
                    record.conversation_id, exc, retry_at, now
                )
                logger.warning(
                    "会话摘要失败 conversation_id=%s attempts=%s",
                    record.conversation_id,
                    record.summary_attempts,
                )
                continue
            # PostgreSQL 完成提交后才允许删除 Redis 正文；删除失败不能回退已完成摘要。
            try:
                await self.turns.delete_turns(record.conversation_id)
            except Exception:
                logger.warning(
                    "已完成摘要但 Redis 轮次删除失败 conversation_id=%s",
                    record.conversation_id,
                )

        expired_ids = await self.repository.delete_expired(now, limit=500)
        for conversation_id in expired_ids:
            await self.turns.delete_turns(conversation_id)

    @staticmethod
    def _retry_at(now: datetime, attempts: int) -> datetime | None:
        delay = {1: 60, 2: 300}.get(attempts)
        return now + timedelta(seconds=delay) if delay is not None else None

    def start(self) -> asyncio.Task:
        if self._task is None or self._task.done():
            self._stop_event = asyncio.Event()
            self._task = asyncio.create_task(self._run_loop(), name="conversation-finalizer")
        return self._task

    async def stop(self) -> None:
        if self._stop_event is not None:
            self._stop_event.set()
        if self._task is not None:
            await self._task
        self._task = None
        self._stop_event = None

    async def _run_loop(self) -> None:
        assert self._stop_event is not None
        while not self._stop_event.is_set():
            try:
                await self.run_once()
            except Exception:
                logger.exception("会话终结器扫描失败")
            try:
                await asyncio.wait_for(
                    self._stop_event.wait(),
                    timeout=ConversationConfig.FINALIZER_INTERVAL_SECONDS,
                )
            except TimeoutError:
                pass
