import asyncio

import pytest

from knowledge.retrieval.vector_retriever import MilvusVectorRetriever


class FakeVectorizer:
    def __init__(self):
        self.embed_calls = []

    def embed_texts(self, texts):
        self.embed_calls.append(texts)
        return [[0.1, 0.2, 0.3, 0.4]]


class FakeMilvusClient:
    def __init__(self, *, collection_exists=True):
        self.collection_exists = collection_exists
        self.calls = []
        self.search_kwargs = None

    async def has_collection(self, collection_name):
        self.calls.append(("has_collection", collection_name))
        return self.collection_exists

    async def search(self, **kwargs):
        self.calls.append(("search", kwargs["collection_name"]))
        self.search_kwargs = kwargs
        return [
            [
                {
                    "id": "milvus-id",
                    "distance": 0.91,
                    "entity": {
                        "text": "return policy",
                        "metadata": {"source_name": "policy.md"},
                        "chunk_id": "chunk-1",
                    },
                },
                {
                    "id": "chunk-2",
                    "score": 0.73,
                    "entity": {
                        "text": "refund timing",
                        "metadata": {},
                    },
                },
            ]
        ]


@pytest.mark.asyncio
async def test_search_checks_collection_embeds_searches_and_normalizes_hits():
    client = FakeMilvusClient()
    vectorizer = FakeVectorizer()
    retriever = MilvusVectorRetriever(
        client=client,
        collection_name="unit_collection",
        dimension=4,
        vectorizer=vectorizer,
    )

    results = await retriever.search("return", limit=2)

    assert client.calls == [
        ("has_collection", "unit_collection"),
        ("search", "unit_collection"),
    ]
    assert vectorizer.embed_calls == [["return"]]
    assert client.search_kwargs == {
        "collection_name": "unit_collection",
        "data": [[0.1, 0.2, 0.3, 0.4]],
        "anns_field": "embedding",
        "limit": 2,
        "output_fields": ["text", "metadata", "chunk_id"],
    }
    assert results == [
        {
            "title": "policy.md",
            "content": "return policy",
            "score": 0.91,
            "metadata": {"source_name": "policy.md"},
            "chunk_id": "chunk-1",
        },
        {
            "title": "知识库片段",
            "content": "refund timing",
            "score": 0.73,
            "metadata": {},
            "chunk_id": "chunk-2",
        },
    ]


@pytest.mark.asyncio
async def test_search_offloads_embedding_to_worker_thread(monkeypatch):
    offload_calls = []

    async def fake_to_thread(function, *args, **kwargs):
        offload_calls.append((function, args, kwargs))
        return function(*args, **kwargs)

    monkeypatch.setattr(asyncio, "to_thread", fake_to_thread)
    client = FakeMilvusClient()
    vectorizer = FakeVectorizer()
    retriever = MilvusVectorRetriever(
        client=client,
        collection_name="unit_collection",
        dimension=4,
        vectorizer=vectorizer,
    )

    await retriever.search("return", limit=2)

    assert offload_calls == [(vectorizer.embed_texts, (["return"],), {})]
    assert client.search_kwargs["data"] == [[0.1, 0.2, 0.3, 0.4]]


@pytest.mark.asyncio
async def test_search_propagates_missing_collection_before_embedding():
    client = FakeMilvusClient(collection_exists=False)
    vectorizer = FakeVectorizer()
    retriever = MilvusVectorRetriever(
        client=client,
        collection_name="missing_collection",
        dimension=4,
        vectorizer=vectorizer,
    )

    with pytest.raises(RuntimeError, match="missing_collection"):
        await retriever.search("return")

    assert vectorizer.embed_calls == []
    assert client.calls == [("has_collection", "missing_collection")]


@pytest.mark.asyncio
async def test_search_falls_back_to_score_when_distance_is_zero():
    class ZeroDistanceClient(FakeMilvusClient):
        async def search(self, **kwargs):
            return [
                [
                    {
                        "distance": 0.0,
                        "score": 0.8,
                        "entity": {"text": "exact match", "metadata": {}},
                    }
                ]
            ]

    retriever = MilvusVectorRetriever(
        client=ZeroDistanceClient(),
        collection_name="unit_collection",
        dimension=4,
        vectorizer=FakeVectorizer(),
    )

    results = await retriever.search("return")

    assert results[0]["score"] == 0.8
