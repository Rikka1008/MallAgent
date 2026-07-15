from services.memory.semantic import ConversationCompressor, SemanticMemoryService


class FakeSemanticStore:
    def __init__(self):
        self.puts = []

    async def put(self, namespace, key, value):
        self.puts.append((namespace, key, value))

    async def search(self, namespace, embedding, limit=5):
        class Item:
            value = {"content": "用户此前正在追踪订单 ORD1002"}

        return [Item()]


async def test_compressor_uses_injected_llm_summarizer():
    calls = []

    async def summarize(messages):
        calls.append(messages)
        return "LLM 生成的会话摘要"

    compressor = ConversationCompressor(summarizer=summarize, turns=5)
    messages = [f"第 {index} 轮" for index in range(5)]

    assert compressor.should_compress(messages)
    assert await compressor.summarize(messages) == "LLM 生成的会话摘要"
    assert calls == [messages]


async def test_semantic_memory_service_writes_and_retrieves_user_scoped_summary():
    store = FakeSemanticStore()

    async def embed(_text):
        return [0.1, 0.2, 0.3]

    async def summarize(_messages):
        return "压缩后的摘要"

    service = SemanticMemoryService(
        store=store,
        embed=embed,
        compressor=ConversationCompressor(summarizer=summarize, turns=5),
    )
    messages = [f"message-{index}" for index in range(5)]

    await service.remember("U100", "S1", messages)
    recalled = await service.recall("U100", "物流怎么还没到", limit=3)

    assert store.puts[0][0] == ("U100", "conversation_summary")
    assert store.puts[0][2]["content"] == "压缩后的摘要"
    assert recalled == ["用户此前正在追踪订单 ORD1002"]
