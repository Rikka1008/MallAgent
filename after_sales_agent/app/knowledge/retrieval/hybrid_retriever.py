from config import EmbeddingConfig, MilvusConfig
from knowledge.retrieval.reranker import BgeReranker
from knowledge.retrieval.fusion import reciprocal_rank_fusion, stable_chunk_id
from knowledge.retrieval.vector_retriever import MilvusVectorRetriever


class HybridRetriever:
    """面向 Agent 的 RAG 检索器。
    `HybridRetriever`，是为了后续在这里继续合并关键词召回、向量召回和重排序。
    """
    def __init__(
        self,
        client=None,
        collection_name: str = MilvusConfig.COLLECTION,
        dimension: int = EmbeddingConfig.DIMENSION,
        vectorizer=None,
        reranker: BgeReranker | None = None,
        keyword_retriever=None,
        vector_retriever=None,
    ):
        self.client = client
        self.collection_name = collection_name
        self.dimension = dimension
        self.vectorizer = vectorizer
        self.reranker = reranker or BgeReranker()
        self.keyword_retriever = keyword_retriever
        self.vector_retriever = vector_retriever or MilvusVectorRetriever(
            client=client,
            collection_name=collection_name,
            dimension=dimension,
            vectorizer=vectorizer,
        )
        self.degradation_events: list[dict] = []

    async def search(self, query: str, limit: int = 5) -> list[dict]:
        """从 Milvus 检索与用户问题最相关的知识片段。
        返回值统一成 `title/content/score/metadata`，这样 Agent 不需要关心底层向量库
        的返回格式；以后替换 Milvus 或增加 rerank，也不会影响上层对话逻辑。
        """
        # 去除首尾空格
        normalized_query = query.strip()
        # 空查询直接返回空列表
        if not normalized_query:
            return []

        self.degradation_events = []
        keyword = self._keyword_search(normalized_query, limit) if self.keyword_retriever else []
        try:
            vector = await self.vector_retriever.search(normalized_query, limit=limit)
        except Exception as exc:
            if not self.keyword_retriever:
                raise
            vector = []
            reason = "missing_collection" if "collection" in str(exc).lower() else "connection_error"
            self.degradation_events.append({"capability":"vector_retrieval", "reason":reason, "fallback_strategy":"keyword"})
        # 合并关键词召回和向量召回的结果
        candidates = reciprocal_rank_fusion(keyword, vector) if self.keyword_retriever else vector
        # 对合并后的结果进行重排序
        try:
            return self.reranker.rerank(normalized_query, candidates)[:limit]
        except Exception:
            self.degradation_events.append({
                "capability":"reranker", 
                "reason":"model_error", 
                "fallback_strategy":"rrf"})# 重排序模型出错，使用RRF回退
            return candidates[:limit]

    def _keyword_search(self, query, limit):
        results = []
        for item in self.keyword_retriever.search(query, limit=limit):
            metadata = dict(getattr(item, "metadata", {}) or {})
            content = item.content
            results.append({"title":item.title, "content":content, "score":float(item.score), "metadata":metadata,
                            "chunk_id":metadata.get("chunk_id") or stable_chunk_id(metadata.get("source_path", item.title), content)})
        return results
