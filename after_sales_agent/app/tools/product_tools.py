from __future__ import annotations

import inspect
from pathlib import Path

from agent.context import AgentRuntimeContext
from config import MilvusConfig
from knowledge.retrieval.hybrid_retriever import HybridRetriever
from knowledge.retrieval.keyword_retriever import KeywordPolicyRetriever
from langchain.tools import ToolRuntime
from langchain_core.tools import tool
from tools.runtime import get_runtime_context


@tool
async def search_products(
    query: str,
    runtime: ToolRuntime[AgentRuntimeContext],
    limit: int = 5,
) -> dict:
    """检索商品信息，用于按需求推荐商品或解释商品属性。"""

    normalized_query = query.strip()
    if not normalized_query:
        return {"found": False, "message": "请说明想了解的商品或需求。", "items": []}

    context = get_runtime_context(runtime)
    retriever = context.case_context.get("product_retriever") or _build_product_retriever()
    try:
        result = retriever.search(normalized_query, limit=limit)
        items = await result if inspect.isawaitable(result) else result
    except Exception:
        return {
            "found": False,
            "message": "商品检索服务暂时不可用，请稍后再试。",
            "items": [],
            "degradations": [
                {
                    "capability": "product_retrieval",
                    "reason": "service_error",
                    "fallback_strategy": "manual_service",
                }
            ],
        }

    return {
        "found": bool(items),
        "message": "已找到相关商品。" if items else "暂未找到相关商品。",
        "items": [_dump_item(item) for item in items],
        "degradations": getattr(retriever, "degradation_events", []),
    }


def _dump_item(item) -> dict:
    return item if isinstance(item, dict) else item.model_dump()


def _build_product_retriever() -> HybridRetriever:
    """构建商品混合检索器，Milvus 不可用时回退到同源 Markdown。"""

    products_dir = (
        Path(__file__).resolve().parents[1] / "data" / "rag_sources" / "products"
    )
    return HybridRetriever(
        collection_name=MilvusConfig.PRODUCT_COLLECTION,
        keyword_retriever=KeywordPolicyRetriever(source_dir=products_dir),
    )
