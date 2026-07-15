import sys
from types import SimpleNamespace

import pytest

from core.database.milvus_client import MilvusClient


def test_create_constructs_async_client_with_explicit_values(monkeypatch):
    created = []

    class FakeAsyncMilvusClient:
        def __init__(self, **kwargs):
            created.append(kwargs)

    monkeypatch.setitem(sys.modules, "pymilvus", SimpleNamespace(AsyncMilvusClient=FakeAsyncMilvusClient))

    client = MilvusClient.create(
        uri="http://milvus.example:19530",
        token="test-token",
        db_name="test-db",
        timeout=7,
    )

    assert isinstance(client, FakeAsyncMilvusClient)
    assert created == [
        {
            "uri": "http://milvus.example:19530",
            "token": "test-token",
            "db_name": "test-db",
            "timeout": 7,
        }
    ]


@pytest.mark.asyncio
async def test_get_client_delegates_to_create_once(monkeypatch):
    client = object()
    create_calls = []

    def fake_create(cls):
        create_calls.append(None)
        return client

    monkeypatch.setattr(MilvusClient, "create", classmethod(fake_create))
    monkeypatch.setattr(MilvusClient, "_client", None)

    first = await MilvusClient.get_client()
    second = await MilvusClient.get_client()

    assert first is second
    assert first is client
    assert create_calls == [None]


@pytest.mark.asyncio
async def test_close_resets_client(monkeypatch):
    class FakeAsyncMilvusClient:
        def __init__(self, **kwargs):
            self.closed = False

        async def close(self):
            self.closed = True

    monkeypatch.setitem(sys.modules, "pymilvus", SimpleNamespace(AsyncMilvusClient=FakeAsyncMilvusClient))
    monkeypatch.setattr(MilvusClient, "_client", None)

    client = await MilvusClient.get_client()
    assert MilvusClient._client is not None

    await MilvusClient.close()
    assert client.closed is True
    assert MilvusClient._client is None
