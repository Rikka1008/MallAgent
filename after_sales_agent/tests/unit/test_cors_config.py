from fastapi.testclient import TestClient

from main import app


client = TestClient(app)


def test_cors_allows_configured_portal_with_credentials():
    response = client.options(
        "/api/auth/session",
        headers={
            "Origin": "http://localhost:8085",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "Authorization,Content-Type",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:8085"
    assert response.headers["access-control-allow-credentials"] == "true"


def test_cors_does_not_allow_unknown_origin():
    response = client.options(
        "/api/auth/session",
        headers={
            "Origin": "http://untrusted.example",
            "Access-Control-Request-Method": "POST",
        },
    )

    assert "access-control-allow-origin" not in response.headers
