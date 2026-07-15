import os


class RedisConfig:
    REDIS_URL = os.getenv("REDIS_URL")
    REDIS_MAX_CONNECTIONS = int(os.getenv("REDIS_MAX_CONNECTIONS", "50"))
    SESSION_TTL_SECONDS = int(os.getenv("SESSION_TTL_SECONDS", "1800"))
    # langgraph-checkpoint-redis 的 default_ttl 单位是分钟。
    CHECKPOINT_TTL_MINUTES = float(os.getenv("CHECKPOINT_TTL_MINUTES", "120"))
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


class ConversationConfig:
    IDLE_TIMEOUT_SECONDS = int(os.getenv("CONVERSATION_IDLE_TIMEOUT_SECONDS", "1800"))
    REDIS_TTL_SECONDS = int(os.getenv("CONVERSATION_REDIS_TTL_SECONDS", "7200"))
    FINALIZER_INTERVAL_SECONDS = int(os.getenv("CONVERSATION_FINALIZER_INTERVAL_SECONDS", "300"))
    SUMMARY_RETENTION_DAYS = int(os.getenv("CONVERSATION_SUMMARY_RETENTION_DAYS", "90"))
    SUMMARY_MAX_ATTEMPTS = int(os.getenv("CONVERSATION_SUMMARY_MAX_ATTEMPTS", "3"))
    RECALL_LIMIT = int(os.getenv("CONVERSATION_RECALL_LIMIT", "3"))

    @classmethod
    def validate(cls) -> None:
        if cls.IDLE_TIMEOUT_SECONDS <= 0:
            raise RuntimeError("CONVERSATION_IDLE_TIMEOUT_SECONDS 必须大于 0")
        if cls.REDIS_TTL_SECONDS <= cls.IDLE_TIMEOUT_SECONDS:
            raise RuntimeError(
                "CONVERSATION_REDIS_TTL_SECONDS 必须大于 CONVERSATION_IDLE_TIMEOUT_SECONDS"
            )
        if not 1 <= cls.SUMMARY_MAX_ATTEMPTS <= 3:
            raise RuntimeError("CONVERSATION_SUMMARY_MAX_ATTEMPTS 必须在 1 到 3 之间")
        for name in (
            "FINALIZER_INTERVAL_SECONDS",
            "SUMMARY_RETENTION_DAYS",
            "RECALL_LIMIT",
        ):
            if getattr(cls, name) <= 0:
                raise RuntimeError(f"CONVERSATION_{name} 必须大于 0")
