import os


class AppConfig:
    APP_ENV = os.getenv("APP_ENV", "local")
    REQUIRE_EXTERNAL_SERVICES = os.getenv("REQUIRE_EXTERNAL_SERVICES", "false").lower() == "true"
    ECOMMERCE_GATEWAY = os.getenv("ECOMMERCE_GATEWAY", "mall")

    @classmethod
    def require_external_services(cls) -> None:
        if cls.APP_ENV != "production" or not cls.REQUIRE_EXTERNAL_SERVICES:
            return

        from config.llm import LlmConfig
        from config.mall import MallConfig
        from config.rag import MilvusConfig
        from config.storage import RedisConfig

        RedisConfig.require_url()
        MilvusConfig.require_uri()
        MallConfig.require_portal_url()
        MallConfig.require_admin_url()
        LlmConfig.require_main_model()
        LlmConfig.require_subagent_model()
