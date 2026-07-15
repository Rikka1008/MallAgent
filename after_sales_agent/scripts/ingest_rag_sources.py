from __future__ import annotations

import argparse
import asyncio
from pathlib import Path
import sys

app_dir = Path(__file__).resolve().parents[1] / "app"
if str(app_dir) not in sys.path:
    sys.path.insert(0, str(app_dir))

from config import EmbeddingConfig, MilvusConfig  # noqa: E402
from knowledge.ingestion.milvus_store import InMemoryVectorStore, MilvusVectorStore  # noqa: E402
from knowledge.ingestion.pipeline import build_rag_documents  # noqa: E402
from knowledge.ingestion.vectorizer import BgeM3Vectorizer  # noqa: E402


async def main() -> None:
    """RAG 知识库入库脚本。

    代码小白可以把它理解成“一键搬运工”：
    它会从 `rag_sources` 读取文件，切成小段，生成向量，再写入 Milvus。
    """

    parser = argparse.ArgumentParser(description="构建 RAG 知识库索引")
    parser.add_argument(
        "--source-dir",
        default="app/data/rag_sources",
        help="RAG 原始源文件目录",
    )
    parser.add_argument(
        "--collection",
        default=MilvusConfig.COLLECTION,
        help="Milvus collection 名称",
    )
    parser.add_argument(
        "--db-name",
        default=MilvusConfig.DB_NAME,
        help="Milvus 数据库名称，默认 default",
    )
    parser.add_argument(
        "--dimension",
        type=int,
        default=EmbeddingConfig.DIMENSION,
        help="向量维度，BGE-M3 默认是 1024，必须和 Milvus collection 一致",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=EmbeddingConfig.BATCH_SIZE,
        help="BGE-M3 批量编码大小，机器内存较小时可以调小",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="只跑加载、清洗、切片、向量化，不写入 Milvus",
    )
    args = parser.parse_args()

    vectorizer = BgeM3Vectorizer(
        model_name=EmbeddingConfig.MODEL_NAME,
        dimension=args.dimension,
        batch_size=args.batch_size,
    )
    vector_store = (
        InMemoryVectorStore()
        if args.dry_run
        else MilvusVectorStore(
            uri=MilvusConfig.URI,
            collection_name=args.collection,
            dimension=args.dimension,
            db_name=args.db_name,
            token=MilvusConfig.TOKEN,
        )
    )
    result = await build_rag_documents(
        source_dir=Path(args.source_dir),
        vectorizer=vectorizer,
        vector_store=vector_store,
    )
    print(
        {
            "loaded_documents": result.loaded_documents,
            "created_chunks": result.created_chunks,
            "inserted_vectors": result.inserted_vectors,
            "dry_run": args.dry_run,
            "db_name": args.db_name,
            "collection": args.collection,
        }
    )


if __name__ == "__main__":
    asyncio.run(main())
