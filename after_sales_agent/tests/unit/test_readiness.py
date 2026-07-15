from config import AppConfig
from diagnostics import readiness


async def test_readiness_reports_all_external_dependencies(monkeypatch):
    async def ok(_name):
        return {"status": "ok"}

    monkeypatch.setattr(readiness, "_check_llm", lambda: ok("llm"))
    monkeypatch.setattr(readiness, "_check_redis", lambda: ok("redis"))
    monkeypatch.setattr(readiness, "_check_milvus", lambda: ok("milvus"))
    monkeypatch.setattr(readiness, "_check_mall", lambda: ok("mall"))

    result = await readiness.check_readiness()

    assert set(result) == {"llm", "redis", "milvus", "mall"}
    assert all(item["status"] == "ok" for item in result.values())


async def test_production_require_ready_rejects_failed_dependency(monkeypatch):
    monkeypatch.setattr(AppConfig, "APP_ENV", "production")
    monkeypatch.setattr(
        readiness,
        "check_readiness",
        lambda: _failed_readiness(),
    )

    try:
        await readiness.require_ready()
    except RuntimeError as exc:
        assert "redis" in str(exc)
    else:
        raise AssertionError("生产环境必须拒绝未就绪的依赖")


async def _failed_readiness():
    return {"redis": {"status": "failed", "detail": "连接失败"}}
