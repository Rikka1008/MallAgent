from pathlib import Path

from dotenv import load_dotenv

ENV_LOADED = load_dotenv(Path(__file__).resolve().parents[2] / ".env")

# 配置类在导入时读取环境变量，因此必须先加载项目根目录的 .env。
from config.app import AppConfig  # noqa: E402
from config.llm import LlmConfig  # noqa: E402
from config.mall import MallConfig  # noqa: E402
from config.rag import EmbeddingConfig, MilvusConfig, RagChunkConfig, RagConfig  # noqa: E402
from config.storage import ConversationConfig, DatabaseConfig, RedisConfig  # noqa: E402

__all__ = [
    "AppConfig",
    "ConversationConfig",
    "DatabaseConfig",
    "EmbeddingConfig",
    "ENV_LOADED",
    "LlmConfig",
    "MallConfig",
    "MilvusConfig",
    "RagChunkConfig",
    "RagConfig",
    "RedisConfig",
]
