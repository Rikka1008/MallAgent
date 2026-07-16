from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys

app_dir = Path(__file__).resolve().parents[2] / "app"
if str(app_dir) not in sys.path:
    sys.path.insert(0, str(app_dir))

from config import DatabaseConfig, EmbeddingConfig, MilvusConfig, RedisConfig  # noqa: E402
from diagnostics.service_smoke import (  # noqa: E402
    SmokeResult,
    check_milvus_async,
    check_postgres,
    check_redis,
    run_rag_check,
    run_with_timeout,
)
from knowledge.retrieval.hybrid_retriever import HybridRetriever  # noqa: E402


async def main() -> int:
    parser = argparse.ArgumentParser(description="只读检查 Agent 外部服务")
    parser.add_argument("--query", default="七天无理由退货需要什么条件？")
    parser.add_argument("--skip-rag", action="store_true", help="只检查基础服务，不加载模型")
    args = parser.parse_args()
    results: list[SmokeResult] = []

    if DatabaseConfig.DATABASE_URL:
        results.append(
            await run_with_timeout("postgres", check_postgres(DatabaseConfig.DATABASE_URL))
        )
    else:
        results.append(SmokeResult("postgres", False, {"error": "not_configured"}))
    if RedisConfig.REDIS_URL:
        results.append(await run_with_timeout("redis", check_redis(RedisConfig.REDIS_URL)))
    else:
        results.append(SmokeResult("redis", False, {"error": "not_configured"}))
    if MilvusConfig.URI:
        results.append(
            await run_with_timeout(
                "milvus",
                check_milvus_async(
                    MilvusConfig.URI,
                    MilvusConfig.TOKEN,
                    MilvusConfig.DB_NAME,
                    MilvusConfig.COLLECTION,
                    EmbeddingConfig.DIMENSION,
                ),
            )
        )
        if results[-1].ok and not args.skip_rag:
            try:
                results.append(
                    await run_with_timeout(
                        "rag",
                        run_rag_check(HybridRetriever(), args.query),
                        timeout_seconds=60,
                    )
                )
            except Exception as exc:
                results.append(SmokeResult("rag", False, {"error": type(exc).__name__}))
    else:
        results.append(SmokeResult("milvus", False, {"error": "not_configured"}))

    print(json.dumps([result.to_dict() for result in results], ensure_ascii=False, indent=2))
    return 0 if all(result.ok for result in results) else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
