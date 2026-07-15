from core.database.url import normalize_async_database_url


def test_postgresql_urls_use_asyncpg_driver():
    assert normalize_async_database_url("postgresql://u:p@db/app") == (
        "postgresql+asyncpg://u:p@db/app"
    )
    assert normalize_async_database_url("postgresql+psycopg://u:p@db/app") == (
        "postgresql+asyncpg://u:p@db/app"
    )
