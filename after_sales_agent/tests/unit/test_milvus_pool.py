import sys
from types import SimpleNamespace

import pytest

from config import MilvusConfig
from core.database.milvus_client import MilvusClient


@pytest.mark.asyncio
async def test_get_client_creates_and_caches_async_client(monkeypatch):
    created = []

    class FakeAsyncMilvusClient:
        def __init__(self, **kwargs):
            created.append(kwargs)

    monkeypatch.setitem(sys.modules, "pymilvus", SimpleNamespace(AsyncMilvusClient=FakeAsyncMilvusClient))
    monkeypatch.setattr(MilvusClient, "_client", None)

    first = await MilvusClient.get_client()
    second = await MilvusClient.get_client()

    assert first is second
    assert created == [
        {
            "uri": MilvusConfig.URI,
            "token": MilvusConfig.TOKEN,
            "db_name": MilvusConfig.DB_NAME,
            "timeout": 1,
        }
    ]


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
