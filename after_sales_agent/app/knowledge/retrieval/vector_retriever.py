from typing import Any

from config import EmbeddingConfig, MilvusConfig
from core.database.milvus_client import MilvusClient
from knowledge.ingestion.vectorizer import BgeM3Vectorizer


class MilvusVectorRetriever:
    """Retrieve and normalize vector-search results from Milvus."""

    def __init__(
        self,
        client: Any | None = None,
        collection_name: str = MilvusConfig.COLLECTION,
        dimension: int = EmbeddingConfig.DIMENSION,
        vectorizer: BgeM3Vectorizer | None = None,
    ):
        self.client = client
        self.collection_name = collection_name
        self.vectorizer = vectorizer or BgeM3Vectorizer(dimension=dimension)

    async def search(self, query: str, limit: int = 5) -> list[dict]:
        client = self.client or await MilvusClient.get_client()
        if hasattr(client, "has_collection") and not await client.has_collection(
            collection_name=self.collection_name
        ):
            raise RuntimeError(f"Milvus collection does not exist: {self.collection_name}")

        query_vector = self.vectorizer.embed_texts([query])[0]
        raw_results = await client.search(
            collection_name=self.collection_name,
            data=[query_vector],
            anns_field="embedding",
            limit=limit,
            output_fields=["text", "metadata", "chunk_id"],
        )
        return self._normalize_results(raw_results)

    @staticmethod
    def _normalize_results(raw_results) -> list[dict]:
        normalized: list[dict] = []
        for result_group in raw_results or []:
            for item in result_group:
                entity = item.get("entity", {}) or {}
                metadata = entity.get("metadata", {}) or {}
                content = entity.get("text", "") or ""
                score = item.get("distance", 0.0) or item.get("score", 0.0)
                normalized.append(
                    {
                        "title": metadata.get("title")
                        or metadata.get("source_name")
                        or "知识库片段",
                        "content": content,
                        "score": float(score),
                        "metadata": metadata,
                        "chunk_id": entity.get("chunk_id") or item.get("id"),
                    }
                )
        return normalized
