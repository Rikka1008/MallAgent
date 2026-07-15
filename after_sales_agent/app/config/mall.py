import os


class MallConfig:
    PORTAL_BASE_URL = os.getenv("MALL_PORTAL_BASE_URL", "http://localhost:8085")
    LOGIN_URL = os.getenv(
        "MALL_LOGIN_URL",
        f"{PORTAL_BASE_URL}/member/login.html",
    )
    # 浏览器登录回跳必须使用唯一公开地址，避免 localhost 与 127.0.0.1 混用导致 Cookie 被拦截。
    AGENT_PUBLIC_URL = os.getenv("AGENT_PUBLIC_URL", "http://localhost:8010")
    ADMIN_BASE_URL = os.getenv("MALL_ADMIN_BASE_URL", "http://localhost:8080")
    AUTH_TOKEN = os.getenv("MALL_AUTH_TOKEN", "")
    REQUEST_TIMEOUT_SECONDS = float(os.getenv("MALL_REQUEST_TIMEOUT_SECONDS", "3"))
    COOKIE_SECURE = os.getenv("MALL_COOKIE_SECURE", "false").lower() == "true"
    COOKIE_MAX_AGE_SECONDS = int(os.getenv("MALL_COOKIE_MAX_AGE_SECONDS", "86400"))
    PORTAL_ORIGINS = [
        origin.strip()
        for origin in os.getenv("MALL_PORTAL_ORIGINS", "http://localhost:8085").split(",")
        if origin.strip()
    ]

    @classmethod
    def require_portal_url(cls) -> str:
        if cls.PORTAL_BASE_URL is None or not str(cls.PORTAL_BASE_URL).strip():
            raise RuntimeError("缺少生产配置：MALL_PORTAL_BASE_URL")
        return cls.PORTAL_BASE_URL

    @classmethod
    def require_admin_url(cls) -> str:
        if cls.ADMIN_BASE_URL is None or not str(cls.ADMIN_BASE_URL).strip():
            raise RuntimeError("缺少生产配置：MALL_ADMIN_BASE_URL")
        return cls.ADMIN_BASE_URL
