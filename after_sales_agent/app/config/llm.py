import os
from dotenv import load_dotenv

load_dotenv()

class LlmConfig:
    # 统一使用 LLM_* 命名空间
    API_KEY = os.getenv("LLM_API_KEY")
    BASE_URL = os.getenv("LLM_BASE_URL")
    MODEL_NAME = os.getenv("LLM_MODEL_NAME", "deepseek-v4-flash")
    TEMPERATURE = float(os.getenv("LLM_TEMPERATURE", "0.3"))
    MAX_TOKENS = int(os.getenv("LLM_MAX_TOKENS", "4096"))
    INTENT_ENABLED = os.getenv("LLM_INTENT_ENABLED", "true").lower() == "true"
    INTENT_CONFIDENCE_THRESHOLD = float(os.getenv("LLM_INTENT_CONFIDENCE_THRESHOLD", "0.65"))
    REQUEST_TIMEOUT_SECONDS = float(os.getenv("LLM_REQUEST_TIMEOUT_SECONDS", "10"))

    @classmethod
    def _require_value(cls, value: str | None, env_name: str) -> str:
        if value is None or not str(value).strip():
            raise RuntimeError(f"缺少生产配置：{env_name}")
        return value

    @classmethod
    def main_model_config(cls) -> dict:
        return {
            "model": cls.MODEL_NAME,
            "api_key": cls.API_KEY,
            "base_url": cls.BASE_URL,
            "temperature": cls.TEMPERATURE,
            "max_tokens": cls.MAX_TOKENS,
            "request_timeout_seconds": cls.REQUEST_TIMEOUT_SECONDS,
        }

    @classmethod
    def subagent_model_config(cls) -> dict:
        """子智能体与主智能体复用同一套 DeepSeek 配置。"""
        return cls.main_model_config()

    @classmethod
    def require_main_model(cls) -> dict:
        config = cls.main_model_config()
        cls._require_value(config["model"], "LLM_MODEL_NAME")
        cls._require_value(config["api_key"], "LLM_API_KEY")
        cls._require_value(config["base_url"], "LLM_BASE_URL")
        return config

    @classmethod
    def require_subagent_model(cls) -> dict:
        return cls.require_main_model()
