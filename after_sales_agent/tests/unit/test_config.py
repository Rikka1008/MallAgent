import importlib

import pytest


def test_config_uses_simple_grouped_os_getenv(monkeypatch):
    monkeypatch.setenv("REDIS_URL", "redis://unit-test:6379/2")
    monkeypatch.setenv("DATABASE_URL", "postgresql+psycopg://unit:test@localhost:5432/app")
    monkeypatch.setenv("MILVUS_URI", "http://unit-test:19530")
    monkeypatch.setenv("MILVUS_DB_NAME", "default")
    monkeypatch.setenv("MILVUS_COLLECTION", "unit_collection")
    monkeypatch.setenv("EMBEDDING_MODEL_NAME", "BAAI/bge-m3")
    monkeypatch.setenv("EMBEDDING_DIMENSION", "1024")
    monkeypatch.setenv("EMBEDDING_BATCH_SIZE", "8")
    monkeypatch.setenv("RAG_RETRIEVER", "milvus")
    monkeypatch.setenv("RAG_SEARCH_LIMIT", "7")

    import config
    import config.rag
    import config.storage

    importlib.reload(config.rag)
    importlib.reload(config.storage)
    config = importlib.reload(config)

    assert config.RedisConfig.REDIS_URL == "redis://unit-test:6379/2"
    assert config.DatabaseConfig.DATABASE_URL == "postgresql+psycopg://unit:test@localhost:5432/app"
    assert config.MilvusConfig.URI == "http://unit-test:19530"
    assert config.MilvusConfig.DB_NAME == "default"
    assert config.MilvusConfig.COLLECTION == "unit_collection"
    assert config.EmbeddingConfig.MODEL_NAME == "BAAI/bge-m3"
    assert config.EmbeddingConfig.DIMENSION == 1024
    assert config.EmbeddingConfig.BATCH_SIZE == 8
    assert config.RagConfig.RETRIEVER == "milvus"
    assert config.RagConfig.SEARCH_LIMIT == 7
    assert not hasattr(config.RagConfig, "ENABLE_RERANK")
    assert not hasattr(config, "AppSettings")
    assert not hasattr(config, "settings")
    assert not hasattr(config, "MILVUS_COLLECTION")


def test_production_rejects_missing_external_services(monkeypatch):
    from config.app import AppConfig
    from config.llm import LlmConfig
    from config.mall import MallConfig
    from config.rag import MilvusConfig
    from config.storage import RedisConfig

    monkeypatch.setattr(AppConfig, "APP_ENV", "production")
    monkeypatch.setattr(AppConfig, "REQUIRE_EXTERNAL_SERVICES", True)
    valid_values = (
        (RedisConfig, "REDIS_URL", "redis://unit-test:6379/0"),
        (MilvusConfig, "URI", "http://unit-test:19530"),
        (MallConfig, "PORTAL_BASE_URL", "https://mall.example.com"),
        (MallConfig, "ADMIN_BASE_URL", "https://mall-admin.example.com"),
        (LlmConfig, "MODEL_NAME", "unit-model"),
        (LlmConfig, "API_KEY", "unit-llm-key"),
        (LlmConfig, "BASE_URL", "https://api.llm.example.com"),
    )

    for config_class, attr, value in valid_values:
        monkeypatch.setattr(config_class, attr, value)

    for config_class, attr, missing_value, expected_name in (
        (RedisConfig, "REDIS_URL", None, "REDIS_URL"),
        (MilvusConfig, "URI", "", "MILVUS_URI"),
        (MallConfig, "PORTAL_BASE_URL", "", "MALL_PORTAL_BASE_URL"),
        (MallConfig, "ADMIN_BASE_URL", "", "MALL_ADMIN_BASE_URL"),
        (LlmConfig, "MODEL_NAME", "", "LLM_MODEL_NAME"),
        (LlmConfig, "API_KEY", None, "LLM_API_KEY"),
        (LlmConfig, "BASE_URL", "", "LLM_BASE_URL"),
    ):
        monkeypatch.setattr(config_class, attr, missing_value)
        with pytest.raises(RuntimeError, match=expected_name):
            AppConfig.require_external_services()
        original = next(value for item_class, item_attr, value in valid_values if (item_class, item_attr) == (config_class, attr))
        monkeypatch.setattr(config_class, attr, original)


def test_llm_config_exposes_unified_main_and_subagent_model():
    from config.llm import LlmConfig

    main_config = LlmConfig.main_model_config()
    subagent_config = LlmConfig.subagent_model_config()

    assert main_config["model"] == LlmConfig.MODEL_NAME
    assert subagent_config["model"] == LlmConfig.MODEL_NAME
    assert "api_key" in main_config
    assert "base_url" in subagent_config


def test_subagent_model_reuses_main_deepseek_config():
    from config.llm import LlmConfig

    assert LlmConfig.subagent_model_config() == LlmConfig.main_model_config()


def test_storage_and_mall_config_require_named_values(monkeypatch):
    from config.mall import MallConfig
    from config.rag import MilvusConfig
    from config.storage import RedisConfig

    monkeypatch.setattr(RedisConfig, "REDIS_URL", None)
    monkeypatch.setattr(MilvusConfig, "URI", "")
    monkeypatch.setattr(MallConfig, "PORTAL_BASE_URL", "")

    with pytest.raises(RuntimeError, match="REDIS_URL"):
        RedisConfig.require_url()

    with pytest.raises(RuntimeError, match="MILVUS_URI"):
        MilvusConfig.require_uri()

    with pytest.raises(RuntimeError, match="MALL_PORTAL_BASE_URL"):
        MallConfig.require_portal_url()
