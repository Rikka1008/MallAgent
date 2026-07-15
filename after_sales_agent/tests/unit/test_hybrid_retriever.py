from knowledge.retrieval.hybrid_retriever import HybridRetriever
from knowledge.retrieval.reranker import BgeReranker
import pytest


class FakeBgeM3Vectorizer:
    """模拟 BGE-M3 向量器，避免检索器单测加载真实模型。"""

    def embed_texts(self, texts):
        return [[0.1, 0.2, 0.3, 0.4] for _ in texts]


class FakeMilvusClient:
    """模拟 Milvus 异步客户端，避免单元测试依赖真实向量数据库。"""

    def __init__(self):
        self.search_kwargs = None

    async def has_collection(self, collection_name: str) -> bool:
        return True

    async def search(self, **kwargs):
        self.search_kwargs = kwargs
        return [
            [
                {
                    "id": "chunk-1",
                    "distance": 0.91,
                    "entity": {
                        "text": "七天无理由退货需要保持商品不影响二次销售。",
                        "metadata": {"source_name": "售后政策.md"},
                    },
                }
            ]
        ]


class FakeKeywordRetriever:
    def search(self, query, limit=3):
        return [type("Snippet", (), {"title":"关键词政策", "content":"关键词内容", "score":0.8})()]


class IdentityReranker:
    def rerank(self, query, candidates):
        return candidates


@pytest.mark.asyncio
async def test_hybrid_retriever_delegates_to_injected_vector_retriever():
    class FakeVectorRetriever:
        def __init__(self):
            self.calls = []

        async def search(self, query, limit=5):
            self.calls.append((query, limit))
            return [
                {
                    "title": "Vector policy",
                    "content": "vector content",
                    "score": 0.9,
                    "metadata": {},
                    "chunk_id": "vector-1",
                }
            ]

    vector_retriever = FakeVectorRetriever()
    retriever = HybridRetriever(
        vector_retriever=vector_retriever,
        keyword_retriever=FakeKeywordRetriever(),
        reranker=IdentityReranker(),
    )

    results = await retriever.search("  return  ", limit=2)

    assert vector_retriever.calls == [("return", 2)]
    assert "Vector policy" in {result["title"] for result in results}
    assert len(results) == 2


@pytest.mark.asyncio
async def test_hybrid_retriever_preserves_falsey_vector_retriever_injection():
    class FalseyVectorRetriever:
        def __init__(self):
            self.calls = []

        def __bool__(self):
            return False

        async def search(self, query, limit=5):
            self.calls.append((query, limit))
            return []

    class ExplodingClient:
        async def has_collection(self, collection_name):
            raise AssertionError("injected vector retriever should be used")

    vector_retriever = FalseyVectorRetriever()
    retriever = HybridRetriever(
        client=ExplodingClient(),
        vector_retriever=vector_retriever,
        reranker=IdentityReranker(),
    )

    assert await retriever.search("return", limit=2) == []
    assert vector_retriever.calls == [("return", 2)]


@pytest.mark.asyncio
async def test_hybrid_retriever_falls_back_to_keyword_when_milvus_fails():
    class BrokenClient:
        async def has_collection(self, collection_name):
            raise ConnectionError("offline")
    retriever = HybridRetriever(
        client=BrokenClient(),
        vectorizer=FakeBgeM3Vectorizer(),
        keyword_retriever=FakeKeywordRetriever(),
        reranker=IdentityReranker(),
    )
    results = await retriever.search("退货", limit=2)
    assert results[0]["title"] == "关键词政策"
    assert retriever.degradation_events[0]["fallback_strategy"] == "keyword"


@pytest.mark.asyncio
async def test_hybrid_retriever_searches_milvus_and_normalizes_results():
    client = FakeMilvusClient()
    retriever = HybridRetriever(
        client=client,
        collection_name="unit_collection",
        dimension=4,
        vectorizer=FakeBgeM3Vectorizer(),
        reranker=IdentityReranker(),
    )

    results = await retriever.search("七天无理由退货", limit=2)

    assert client.search_kwargs["collection_name"] == "unit_collection"
    assert client.search_kwargs["limit"] == 2
    assert len(client.search_kwargs["data"][0]) == 4
    assert results == [
        {
            "title": "售后政策.md",
            "content": "七天无理由退货需要保持商品不影响二次销售。",
            "score": 0.91,
            "metadata": {"source_name": "售后政策.md"},
            "chunk_id": "chunk-1",
        }
    ]


@pytest.mark.asyncio
async def test_hybrid_retriever_uses_pool_when_client_is_not_injected(monkeypatch):
    client = FakeMilvusClient()
    async def mock_get_client():
        return client
    monkeypatch.setattr(
        "knowledge.retrieval.vector_retriever.MilvusClient.get_client", mock_get_client
    )
    retriever = HybridRetriever(
        dimension=4,
        vectorizer=FakeBgeM3Vectorizer(),
        reranker=IdentityReranker(),
    )

    await retriever.search("七天无理由退货", limit=2)

    assert client.search_kwargs["collection_name"] == retriever.collection_name


@pytest.mark.asyncio
async def test_hybrid_retriever_checks_collection_before_vectorizing():
    class MissingCollectionClient:
        async def has_collection(self, collection_name: str) -> bool:
            return False

    class ExplodingVectorizer:
        def embed_texts(self, texts):
            raise AssertionError("collection 不存在时不应该加载 BGE-M3 向量模型")

    retriever = HybridRetriever(
        client=MissingCollectionClient(),
        collection_name="missing_collection",
        dimension=4,
        vectorizer=ExplodingVectorizer(),
    )

    with pytest.raises(RuntimeError) as exc_info:
        await retriever.search("七天无理由退货")

    assert "missing_collection" in str(exc_info.value)


@pytest.mark.asyncio
async def test_hybrid_retriever_applies_bge_reranker_after_retrieval():
    class TwoResultClient(FakeMilvusClient):
        async def search(self, **kwargs):
            return [[
                {"distance": 0.9, "entity": {"text": "first", "metadata": {"source_name": "a.md"}}},
                {"distance": 0.8, "entity": {"text": "second", "metadata": {"source_name": "b.md"}}},
            ]]

    class FakeRerankerModel:
        def compute_score(self, pairs, **kwargs):
            return [0.1, 0.9]

    retriever = HybridRetriever(
        client=TwoResultClient(),
        dimension=4,
        vectorizer=FakeBgeM3Vectorizer(),
        reranker=BgeReranker(model=FakeRerankerModel()),
    )

    results = await retriever.search("query", limit=2)

    assert [result["content"] for result in results] == ["second", "first"]
    assert [result["rerank_score"] for result in results] == [0.9, 0.1]
