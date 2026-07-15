from __future__ import annotations

from typing import Any

from config import EmbeddingConfig
from knowledge.ingestion.models import DocumentChunk, VectorRecord


class BgeM3Vectorizer:
    """BGE-M3 向量生成器。

    BGE-M3 是适合中文和多语言检索的 embedding 模型。这里默认使用
    `BAAI/bge-m3`，输出维度为 1024；入库和查询必须使用同一个模型与维度，
    否则 Milvus collection 的向量维度会对不上。
    """

    def __init__(
        self,
        model_name: str = EmbeddingConfig.MODEL_NAME,
        dimension: int = EmbeddingConfig.DIMENSION,
        batch_size: int = EmbeddingConfig.BATCH_SIZE,
        max_length: int = EmbeddingConfig.MAX_LENGTH,
        model: Any | None = None,
    ):
        self.model_name = model_name
        self.dimension = dimension
        self.batch_size = batch_size
        self.max_length = max_length
        self._model = model

    def vectorize(self, chunks: list[DocumentChunk]) -> list[VectorRecord]:
        """把文本切片转换为 BGE-M3 向量记录。"""

        if not chunks:
            return []

        texts = [chunk.text for chunk in chunks]
        embeddings = self._encode(texts)
        records: list[VectorRecord] = []
        for chunk, embedding in zip(chunks, embeddings, strict=True):
            vector = [float(value) for value in embedding]
            if len(vector) != self.dimension:
                raise ValueError(
                    f"BGE-M3 向量维度应为 {self.dimension}，实际得到 {len(vector)}。"
                )
            records.append(
                VectorRecord(
                    text=chunk.text,
                    embedding=vector,
                    metadata=chunk.metadata,
                )
            )
        return records

    def _encode(self, texts: list[str]):
        """调用 BGE-M3 模型生成向量。

        测试中可以传入假的 `model`；生产环境没有传入时，会懒加载
        `FlagEmbedding.BGEM3FlagModel`，避免应用启动时立刻加载大模型。
        """

        model = self._model or self._load_model()
        embeddings = model.encode(
            texts,
            batch_size=self.batch_size,
            max_length=self.max_length,
        )
        if isinstance(embeddings, dict) and "dense_vecs" in embeddings:
            return embeddings["dense_vecs"]
        return embeddings

    def _load_model(self):
        """加载 BGE-M3 模型。"""

        try:
            from FlagEmbedding import BGEM3FlagModel
            import torch
        except ImportError as exc:
            raise RuntimeError(
                "请先安装 FlagEmbedding，再使用 BGE-M3 向量模型。"
            ) from exc

        self._model = BGEM3FlagModel(
            self.model_name,
            use_fp16=bool(torch.cuda.is_available()),
        )
        return self._model
