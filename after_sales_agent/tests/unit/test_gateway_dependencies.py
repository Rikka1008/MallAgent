from api import dependencies
from adapters.mall_gateway import MallEcommerceGateway


def test_get_gateway_uses_mall_by_default(monkeypatch):
    monkeypatch.delenv("ECOMMERCE_GATEWAY", raising=False)
    monkeypatch.setenv("MALL_PORTAL_BASE_URL", "http://mall-portal")
    monkeypatch.setenv("MALL_ADMIN_BASE_URL", "http://mall-admin")
    dependencies.reset_gateway_cache()

    gateway = dependencies.get_gateway()

    assert isinstance(gateway, MallEcommerceGateway)


def test_get_gateway_can_switch_to_mall_explicitly(monkeypatch):
    monkeypatch.setenv("ECOMMERCE_GATEWAY", "mall")
    monkeypatch.setenv("MALL_PORTAL_BASE_URL", "http://mall-portal")
    monkeypatch.setenv("MALL_ADMIN_BASE_URL", "http://mall-admin")
    dependencies.reset_gateway_cache()

    gateway = dependencies.get_gateway()

    assert isinstance(gateway, MallEcommerceGateway)


def test_get_gateway_rejects_mock_gateway(monkeypatch):
    monkeypatch.setenv("ECOMMERCE_GATEWAY", "mock")
    dependencies.reset_gateway_cache()

    try:
        dependencies.get_gateway()
    except ValueError as exc:
        assert "不支持的电商网关配置" in str(exc)
    else:
        raise AssertionError("接入真实 mall 后不应再允许切换到 mock 网关")


def test_get_gateway_uses_request_bearer_token(monkeypatch):
    monkeypatch.setenv("ECOMMERCE_GATEWAY", "mall")

    gateway = dependencies.get_gateway(authorization="Bearer user-token")

    assert gateway.auth_header == "Bearer user-token"
