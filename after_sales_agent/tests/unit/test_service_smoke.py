import asyncio

import pytest

from diagnostics.service_smoke import (
    SmokeResult,
    check_milvus,
    check_milvus_async,
    redact,
    run_rag_check,
    run_with_timeout,
)


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
