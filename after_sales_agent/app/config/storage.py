import os


class RedisConfig:
    REDIS_URL = os.getenv("REDIS_URL")
    REDIS_MAX_CONNECTIONS = int(os.getenv("REDIS_MAX_CONNECTIONS", "50"))
    SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", "1800"))
    IDEMPOTENCY_TTL_SECONDS = int(os.getenv("IDEMPOTENCY_TTL_SECONDS", "86400"))
    IDEMPOTENCY_KEY_PREFIX = os.getenv(
        "IDEMPOTENCY_KEY_PREFIX", "after_sales:idempotency:"
    )

    @classmethod
    def require_url(cls) -> str:
        if cls.REDIS_URL is None or not str(cls.REDIS_URL).strip():
            raise RuntimeError("缺少生产配置：REDIS_URL")
        return cls.REDIS_URL


class DatabaseConfig:
    DATABASE_URL = os.getenv("DATABASE_URL")
    POOL_SIZE = int(os.getenv("DATABASE_POOL_SIZE", "5"))
    MAX_OVERFLOW = int(os.getenv("DATABASE_MAX_OVERFLOW", "10"))
    POOL_TIMEOUT_SECONDS = float(os.getenv("DATABASE_POOL_TIMEOUT_SECONDS", "30"))
