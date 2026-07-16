import asyncio
from pathlib import Path
import sys
from types import SimpleNamespace

import pytest

from core.database.milvus_client import MilvusClient
from diagnostics.service_smoke import (
    SmokeResult,
    check_milvus,
    check_milvus_async,
    redact,
    run_rag_check,
    run_with_timeout,
)


def test_smoke_entrypoints_live_under_tests():
    project_root = Path(__file__).resolve().parents[2]
    smoke_dir = project_root / "tests/smoke"

    assert (smoke_dir / "smoke_test_services.py").is_file()
    assert (smoke_dir / "smoke_test_idempotency.py").is_file()
    assert not (project_root / "scripts/smoke_test_services.py").exists()
    assert not (project_root / "scripts/smoke_test_idempotency.py").exists()


class FakeRetriever:
    def search(self, query: str, limit: int = 3):
        return [{"title": "退货规则", "content": "七天无理由", "score": 0.9, "metadata": {}}]


@pytest.mark.asyncio
async def test_rag_smoke_returns_structured_result_without_content():
    class FakeAsyncRetriever:
        async def search(self, query: str, limit: int = 3):
            return [{"title": "退货规则", "content": "七天无理由", "score": 0.9, "metadata": {}}]

    result = await run_rag_check(FakeAsyncRetriever(), "如何退货？")

    assert result == SmokeResult(
        component="rag",
        ok=True,
        detail={"hit_count": 1, "titles": ["退货规则"]},
    )


def test_redact_removes_secret_values_recursively():
    payload = {"token": "secret-token", "nested": {"password": "p", "ok": True}}

    assert redact(payload) == {"token": "***", "nested": {"password": "***", "ok": True}}


async def test_component_timeout_returns_structured_failure():
    async def slow_check():
        await asyncio.sleep(1)
        return SmokeResult("slow", True, {})

    result = await run_with_timeout("slow", slow_check(), timeout_seconds=0.01)

    assert result == SmokeResult("slow", False, {"error": "timeout"})


def test_milvus_dimension_mismatch_is_failure():
    class FakeMilvusClient:
        def has_collection(self, collection_name: str):
            return True

        def describe_collection(self, collection_name: str):
            return {
                "fields": [
                    {"name": "embedding", "params": {"dim": 384}},
                ]
            }

    result = check_milvus(
        "http://milvus",
        None,
        "default",
        "knowledge",
        expected_dimension=1024,
        client=FakeMilvusClient(),
    )

    assert result.ok is False
    assert result.detail["dimension"] == 384
    assert result.detail["expected_dimension"] == 1024


@pytest.mark.asyncio
async def test_milvus_async_dimension_mismatch_is_failure():
    class FakeAsyncMilvusClient:
        async def has_collection(self, collection_name: str):
            return True

        async def describe_collection(self, collection_name: str):
            return {
                "fields": [
                    {"name": "embedding", "params": {"dim": 384}},
                ]
            }

    result = await check_milvus_async(
        "http://milvus",
        None,
        "default",
        "knowledge",
        expected_dimension=1024,
        client=FakeAsyncMilvusClient(),
    )

    assert result.ok is False
    assert result.detail["dimension"] == 384
    assert result.detail["expected_dimension"] == 1024


@pytest.mark.asyncio
async def test_milvus_async_uses_unified_factory_when_client_is_not_injected(monkeypatch):
    create_calls = []
    close_calls = []

    class FakeAsyncMilvusClient:
        async def has_collection(self, collection_name: str):
            return True

        async def describe_collection(self, collection_name: str):
            return {"fields": []}

        async def close(self):
            close_calls.append(True)

    class ExplodingDirectClient:
        def __init__(self, **kwargs):
            raise AssertionError("AsyncMilvusClient must be created by MilvusClient.create")

    def fake_create(cls, **kwargs):
        create_calls.append(kwargs)
        return FakeAsyncMilvusClient()

    monkeypatch.setattr(MilvusClient, "create", classmethod(fake_create))
    monkeypatch.setitem(
        sys.modules,
        "pymilvus",
        SimpleNamespace(AsyncMilvusClient=ExplodingDirectClient),
    )

    result = await check_milvus_async(
        "http://milvus",
        "test-token",
        "test-db",
        "knowledge",
    )

    assert result.ok is True
    assert create_calls == [
        {
            "uri": "http://milvus",
            "token": "test-token",
            "db_name": "test-db",
            "timeout": 2,
        }
    ]
    assert close_calls == [True]


@pytest.mark.asyncio
async def test_milvus_async_closes_owned_client_after_failure(monkeypatch):
    client = SimpleNamespace()
    client.close_calls = 0

    async def fail_has_collection(*, collection_name: str):
        raise ConnectionError(collection_name)

    async def close():
        client.close_calls += 1

    client.has_collection = fail_has_collection
    client.close = close
    monkeypatch.setattr(MilvusClient, "create", classmethod(lambda cls, **kwargs: client))

    result = await check_milvus_async("http://milvus", None, "default", "knowledge")

    assert result == SmokeResult("milvus", False, {"error": "ConnectionError"})
    assert client.close_calls == 1


@pytest.mark.asyncio
async def test_milvus_async_closes_owned_client_when_cancelled(monkeypatch):
    started = asyncio.Event()
    client = SimpleNamespace()
    client.close_calls = 0

    async def wait_forever(*, collection_name: str):
        started.set()
        await asyncio.Event().wait()

    async def close():
        client.close_calls += 1

    client.has_collection = wait_forever
    client.close = close
    monkeypatch.setattr(MilvusClient, "create", classmethod(lambda cls, **kwargs: client))

    task = asyncio.create_task(
        check_milvus_async("http://milvus", None, "default", "knowledge")
    )
    await started.wait()
    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await task

    assert client.close_calls == 1


@pytest.mark.asyncio
async def test_milvus_async_does_not_close_injected_client():
    client = SimpleNamespace()
    client.close_calls = 0

    async def has_collection(*, collection_name: str):
        return False

    async def close():
        client.close_calls += 1

    client.has_collection = has_collection
    client.close = close

    result = await check_milvus_async(
        "http://milvus",
        None,
        "default",
        "knowledge",
        client=client,
    )

    assert result.ok is False
    assert client.close_calls == 0
