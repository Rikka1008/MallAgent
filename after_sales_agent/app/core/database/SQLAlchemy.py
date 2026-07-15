from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from config import DatabaseConfig
from core.database.url import normalize_async_database_url

class SqlAlchemyPool:

    _engine: AsyncEngine | None = None

    @classmethod
    async def get(cls, url: str | None = DatabaseConfig.DATABASE_URL) -> AsyncEngine:
        if not url:
            raise RuntimeError("请先配置 DATABASE_URL")
        
        if cls._engine is None:
            async_url = normalize_async_database_url(url)
            engine_options = {}
            if async_url.startswith("postgresql+asyncpg://"):
                engine_options = {
                    "pool_size": DatabaseConfig.POOL_SIZE,
                    "max_overflow": DatabaseConfig.MAX_OVERFLOW,
                    "pool_timeout": DatabaseConfig.POOL_TIMEOUT_SECONDS,
                    "pool_pre_ping": True,
                }
            cls._engine = create_async_engine(async_url, **engine_options)
        return cls._engine
        
    @classmethod
    async def close(cls) -> None:
        if cls._engine is not None:
            await cls._engine.dispose()
            cls._engine = None
