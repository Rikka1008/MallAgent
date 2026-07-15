import inspect

from agent.context import AgentRuntimeContext
from langchain.tools import ToolRuntime
from langchain_core.tools import tool

from config import MilvusConfig, RagConfig
from knowledge.retrieval.keyword_retriever import KeywordPolicyRetriever
from knowledge.retrieval.hybrid_retriever import HybridRetriever
from tools.runtime import get_runtime_context


@tool
async def search_policy(
    query: str,
    runtime: ToolRuntime[AgentRuntimeContext],
    limit: int = 3,
) -> dict:
    """检索售后政策。

    返回结构化片段，既可以给 Agent 生成回复，也可以在调试面板展示命中的政策依据。
    """

    context = get_runtime_context(runtime)
    return await find_policy(
        query=query,
        limit=limit,
        retriever=context.case_context.get("policy_retriever"),
    )


async def find_policy(query: str, limit: int = 3, retriever=None) -> dict:
    """执行政策检索，供 Agent 工具和受控业务流程复用。"""

    active = retriever
    if active is None and RagConfig.RETRIEVER == "hybrid" and MilvusConfig.URI:
        active = HybridRetriever(
            collection_name=MilvusConfig.POLICY_COLLECTION,
            keyword_retriever=KeywordPolicyRetriever(),
        )
    if active is None:
        active = KeywordPolicyRetriever()
    snippets = await _search_with_fallback(query=query, limit=limit, retriever=active)
    dumped = [_dump_snippet(snippet) for snippet in snippets]
    sources = [_source_from_snippet(item) for item in dumped]
    return {
        "found": bool(snippets),
        "message": "已找到相关政策。" if snippets else "暂未找到相关政策。",
        "snippets": dumped,
        "sources": [source for source in sources if source],
        "degradations": getattr(active, "degradation_events", []),
    }


async def _search_with_fallback(query: str, limit: int, retriever=None) -> list:
    """执行政策检索。

    如果调用方显式传入检索器，说明它希望控制检索来源，例如单元测试传入假 RAG；
    如果没有传入，就先尝试 Milvus，失败后回退到本地关键词检索。
    """

    if retriever is not None:
        result = retriever.search(query, limit=limit)
        return await result if inspect.isawaitable(result) else result

    if RagConfig.RETRIEVER != "milvus":
        return KeywordPolicyRetriever().search(query, limit=limit)

    try:
        return await HybridRetriever(
            collection_name=MilvusConfig.POLICY_COLLECTION
        ).search(query, limit=limit)
    except Exception:
        return KeywordPolicyRetriever().search(query, limit=limit)


def _dump_snippet(snippet) -> dict:
    """统一转换不同检索器返回的片段格式。"""

    if isinstance(snippet, dict):
        return snippet
    return snippet.model_dump()


def _source_from_snippet(item: dict) -> dict | None:
    metadata = item.get("metadata") or {}
    chunk_id = item.get("chunk_id") or metadata.get("chunk_id")
    if not chunk_id:
        return None
    return {
        "source_name": metadata.get("source_name") or item.get("title", "knowledge"),
        "source_path": metadata.get("source_path") or metadata.get("relative_path", ""),
        "chunk_id": chunk_id,
        "document_id": metadata.get("document_id", ""),
        "retrieval_channels": item.get("retrieval_channels", []),
    }
