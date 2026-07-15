from fastapi.testclient import TestClient

from api.dependencies import get_gateway
from config import MallConfig
from domain.models import CurrentMember
from domain.errors import AuthenticationError
from main import app
from tests.fakes import FakeEcommerceGateway


class MemberGateway(FakeEcommerceGateway):
    async def get_current_member(self):
        return CurrentMember(user_id="U100", username="test")


def _client() -> TestClient:
    app.dependency_overrides[get_gateway] = MemberGateway
    return TestClient(app)


def test_session_bridge_validates_member_and_sets_http_only_cookie():
    client = _client()
    try:
        response = client.post(
            "/api/auth/session",
            headers={"Authorization": "Bearer member-token"},
        )
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {
        "authenticated": True,
        "user": {"user_id": "U100", "username": "test"},
    }
    assert "mall_access_token=member-token" in response.headers["set-cookie"]
    assert "HttpOnly" in response.headers["set-cookie"]


def test_session_bridge_rejects_missing_authorization_header():
    client = _client()
    try:
        response = client.post("/api/auth/session")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 401
    assert response.json()["detail"] == "缺少 Mall 会员登录凭据。"


def test_auth_status_returns_anonymous_without_cookie():
    client = _client()
    client.cookies.clear()
    try:
        response = client.get("/api/auth/status")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"authenticated": False, "user": None}


def test_mall_login_uses_canonical_agent_origin_for_cookie_exchange(monkeypatch):
    monkeypatch.setattr(
        MallConfig,
        "LOGIN_URL",
        "http://localhost:8085/member/login.html",
    )
    monkeypatch.setattr(
        MallConfig,
        "AGENT_PUBLIC_URL",
        "http://localhost:8010",
        raising=False,
    )
    app.dependency_overrides[get_gateway] = MemberGateway
    client = TestClient(app, base_url="http://127.0.0.1:8010")
    try:
        response = client.get("/api/auth/mall-login", follow_redirects=False)
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 307
    assert response.headers["location"] == (
        "http://localhost:8085/member/login.html"
        "?agent_base_url=http%3A%2F%2Flocalhost%3A8010"
    )


def test_logout_clears_http_only_member_cookie():
    client = _client()
    client.cookies.set("mall_access_token", "member-token")
    try:
        response = client.post("/api/auth/logout")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"authenticated": False, "user": None}
    cookie = response.headers["set-cookie"]
    assert "mall_access_token=" in cookie
    assert "Max-Age=0" in cookie
    assert "HttpOnly" in cookie
    assert "Path=/" in cookie
    assert "SameSite=lax" in cookie


def test_invalid_cookie_is_cleared_during_status_check():
    class ExpiredGateway(MemberGateway):
        async def get_current_member(self):
            raise AuthenticationError("登录状态已失效")

    app.dependency_overrides[get_gateway] = ExpiredGateway
    client = TestClient(app)
    client.cookies.set("mall_access_token", "expired-token")
    try:
        response = client.get("/api/auth/status")
    finally:
        app.dependency_overrides.clear()

    assert response.status_code == 200
    assert response.json() == {"authenticated": False, "user": None}
    assert "Max-Age=0" in response.headers["set-cookie"]
