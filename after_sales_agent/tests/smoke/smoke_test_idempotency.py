from __future__ import annotations

import asyncio
import sys
import time
from pathlib import Path


app_dir = Path(__file__).resolve().parents[2] / "app"
if str(app_dir) not in sys.path:
    sys.path.insert(0, str(app_dir))

from config import RedisConfig  # noqa: E402
from core.database.redis_client import RedisClient  # noqa: E402


async def main() -> int:
    client = await RedisClient.get()
    await client.ping()
    key = f"{RedisConfig.IDEMPOTENCY_KEY_PREFIX}smoke:{int(time.time())}"
    first = await client.set(key, "1", ex=30, nx=True)
    second = await client.set(key, "2", ex=30, nx=True)
    await client.delete(key)
    await RedisClient.close()
    print(
        {
            "redis_ping": True,
            "first_setnx": bool(first),
            "second_setnx": bool(second),
        }
    )
    return 0 if first and not second else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
