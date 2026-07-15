from api.dependencies import _resolve_auth_header


def test_cookie_auth_is_wrapped_as_bearer_header():
    assert _resolve_auth_header(None, "member-token") == "Bearer member-token"


def test_authorization_header_has_priority_over_cookie():
    assert _resolve_auth_header("Bearer header-token", "cookie-token") == "Bearer header-token"
