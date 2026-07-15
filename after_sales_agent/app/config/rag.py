import os


class RagChunkConfig:
    CHUNK_SIZE = int(os.getenv("CHUNK_SIZE", "800"))
    CHUNK_OVERLAP = int(os.getenv("CHUNK_OVERLAP", "120"))
    MAX_CHUNKS_PER_DOCUMENT = int(os.getenv("MAX_CHUNKS_PER_DOCUMENT", "50"))


class RagConfig:
    RETRIEVER = os.getenv("RAG_RETRIEVER", "hybrid")
    SEARCH_LIMIT = int(os.getenv("RAG_SEARCH_LIMIT", "5"))
    KEYWORD_CANDIDATE_LIMIT = int(os.getenv("RAG_KEYWORD_CANDIDATE_LIMIT", "20"))
    VECTOR_CANDIDATE_LIMIT = int(os.getenv("RAG_VECTOR_CANDIDATE_LIMIT", "20"))
    RERANK_CANDIDATE_LIMIT = int(os.getenv("RAG_RERANK_CANDIDATE_LIMIT", "20"))
    RRF_K = int(os.getenv("RAG_RRF_K", "60"))
    RERANK_MODEL_NAME = os.getenv("RERANK_MODEL_NAME", "BAAI/bge-reranker-v2-m3")
    RERANK_BATCH_SIZE = int(os.getenv("RERANK_BATCH_SIZE", "8"))


class EmbeddingConfig:
    MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME", "BAAI/bge-m3")
    DIMENSION = int(os.getenv("EMBEDDING_DIMENSION", "1024"))
    BATCH_SIZE = int(os.getenv("EMBEDDING_BATCH_SIZE", "16"))
    MAX_LENGTH = int(os.getenv("EMBEDDING_MAX_LENGTH", "1024"))


class MilvusConfig:
    URI = os.getenv("MILVUS_URI")
    TOKEN = os.getenv("MILVUS_TOKEN")
    DB_NAME = os.getenv("MILVUS_DB_NAME", "default")
    PRODUCT_COLLECTION = os.getenv(
        "MILVUS_PRODUCT_COLLECTION",
        os.getenv("MILVUS_COLLECTION", "after_sales_products"),
    )
    POLICY_COLLECTION = os.getenv("MILVUS_POLICY_COLLECTION", "after_sales_policies")
    MEMORY_COLLECTION = os.getenv("MILVUS_MEMORY_COLLECTION", "after_sales_memories")
    COLLECTION = PRODUCT_COLLECTION
    MEMORY_SEARCH_LIMIT = int(os.getenv("MILVUS_MEMORY_SEARCH_LIMIT", "3"))

    @classmethod
    def require_uri(cls) -> str:
        if cls.URI is None or not str(cls.URI).strip():
            raise RuntimeError("缺少生产配置：MILVUS_URI")
        return cls.URI
