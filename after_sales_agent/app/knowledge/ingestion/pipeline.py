from pathlib import Path

from knowledge.ingestion.loader import load_source_documents
from knowledge.ingestion.milvus_store import VectorStore
from knowledge.ingestion.models import RagBuildResult
from knowledge.ingestion.splitter import split_documents
from knowledge.ingestion.vectorizer import BgeM3Vectorizer


async def build_rag_documents(
    source_dir: Path,
    vectorizer: BgeM3Vectorizer,
    vector_store: VectorStore,
    chunk_size: int = 800,
    chunk_overlap: int = 120,
) -> RagBuildResult:
    """执行一条完整的本地 RAG 入库流水线。

    这就是你要记住的主流程：
    加载文件 -> 清洗和切分 -> 生成向量 -> 写入向量库。
    """

    documents = load_source_documents(source_dir)
    chunks = split_documents(documents, chunk_size=chunk_size, chunk_overlap=chunk_overlap)
    vectors = vectorizer.vectorize(chunks)
    inserted = await vector_store.upsert(vectors)
    return RagBuildResult(
        loaded_documents=len(documents),
        created_chunks=len(chunks),
        inserted_vectors=inserted,
    )
