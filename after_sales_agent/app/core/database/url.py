def normalize_async_database_url(url: str) -> str:
    """Normalize supported PostgreSQL URLs to SQLAlchemy's asyncpg dialect."""

    if url.startswith("postgresql+asyncpg://"):
        return url
    if url.startswith("postgresql+psycopg://"):
        return "postgresql+asyncpg://" + url.removeprefix("postgresql+psycopg://")
    if url.startswith("postgresql://"):
        return "postgresql+asyncpg://" + url.removeprefix("postgresql://")
    return url
