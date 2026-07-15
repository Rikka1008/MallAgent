from __future__ import annotations

from collections.abc import Awaitable, Callable
from hashlib import sha256

import httpx

from config.llm import LlmConfig

SummaryFunction = Callable[[list[str]], Awaitable[str]]
EmbeddingFunction = Callable[[str], Awaitable[list[float]]]


class OpenAIConversationSummarizer:
    """使用配置的聊天模型生成压缩后的会话记忆"""
    async def __call__(self, messages: list[str]) -> str:
        if not LlmConfig.API_KEY or not LlmConfig.BASE_URL:
            raise RuntimeError("LLM_API_KEY 和 LLM_BASE_URL 是会话压缩的必需配置")
        payload = {
            "model": LlmConfig.MODEL_NAME,
            "temperature": 0,
            "max_tokens": min(LlmConfig.MAX_TOKENS, 512),
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "请将售后对话压缩为简洁、事实性的长期记忆。保留订单号、用户偏好、"
                        "未解决事项和明确意图；不要虚构信息，只返回摘要正文。"
                    ),
                },
                {"role": "user", "content": "\n".join(messages)},
            ],
        }
        async with httpx.AsyncClient(timeout=LlmConfig.REQUEST_TIMEOUT_SECONDS) as client:
            response = await client.post(
                f"{LlmConfig.BASE_URL.rstrip('/')}/chat/completions",
                headers={"Authorization": f"Bearer {LlmConfig.API_KEY}"},
                json=payload,
            )
            response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"].strip()


class ConversationCompressor:
    def __init__(self, summarizer: SummaryFunction, 
    turns: int = 5,
    token_threshold: int = 2000):
        self.summarizer = summarizer #摘要生成
        self.turns = turns # 每5轮对话触发一次压缩
        self.token_threshold = token_threshold # 每轮对话最大token数为2000个

    def should_compress(self, messages: list[str]) -> bool:
        """判断是否需要压缩，满足任一条件"""
        return len(messages) >= self.turns and (
            # 条件1：达到轮数倍数
            len(messages) % self.turns == 0 
            # 条件2：达到最大token数
            or sum(len(message) for message in messages) >= self.token_threshold * 4
        )

    async def summarize(self, messages: list[str]) -> str:
        return await self.summarizer(messages)

    @staticmethod
    def key(session_id: str, message_count: int, summary: str) -> str:
        """生成会话摘要的唯一键"""
        # 对摘要进行哈希处理，取前16个字符作为摘要的唯一标识
        digest = sha256(summary.encode("utf-8")).hexdigest()[:16]
        return f"{session_id}:{message_count}:{digest}"


class SemanticMemoryService:
    def __init__(self, store, embed: EmbeddingFunction, compressor: ConversationCompressor):
        self.store = store # 向量存储
        self.embed = embed # 向量嵌入
        self.compressor = compressor # 会话压缩器

    async def remember(self, user_id: str, session_id: str, messages: list[str]) -> bool:
        """记住会话记忆"""
        if not self.compressor.should_compress(messages):
            return False
        summary = await self.compressor.summarize(messages)
        embedding = await self.embed(summary)
        # 存储会话摘要到向量存储
        await self.store.put(
            (user_id, "conversation_summary"), # 命名空间为用户ID和会话摘要
            self.compressor.key(session_id, len(messages), summary), # 会话摘要的唯一键
            {"content": summary, "embedding": embedding},
        )
        return True

    async def recall(self, user_id: str, query: str, limit: int = 3) -> list[str]:
        """根据查询检索会话摘要"""
        embedding = await self.embed(query)
        # 检索与查询最相似的会话摘要
        items = await self.store.search(
            (user_id, "conversation_summary"), embedding, limit=limit
        )
        return [item.value["content"] for item in items]
