from pathlib import Path


WEB_DIR = Path(__file__).parents[2] / "app" / "web"
WEB_APP = WEB_DIR / "app.js"
WEB_INDEX = WEB_DIR / "index.html"
WEB_STYLES = WEB_DIR / "styles.css"
MALL_MEMBER_LOGIN = (
    Path(__file__).parents[3]
    / "mall"
    / "mall-portal"
    / "src"
    / "main"
    / "resources"
    / "static"
    / "member"
    / "login.html"
)


def test_web_uses_auth_status_instead_of_password_form():
    html = WEB_INDEX.read_text(encoding="utf-8")
    script = WEB_APP.read_text(encoding="utf-8")

    assert 'id="login-form"' not in html
    assert 'id="login-username"' not in html
    assert 'id="login-password"' not in html
    assert 'id="auth-status"' in html
    assert 'id="auth-gate"' in html
    assert '/static/styles.css?v=20260714-wide-card' in html
    assert 'fetchWithTimeout("/api/auth/status"' in script
    assert "setAuthState" in script
    assert 'fetch("/api/auth/login"' not in script
    assert 'id="logout-button"' in html
    assert 'href="/api/auth/mall-login"' in html
    assert 'fetchWithTimeout("/api/auth/logout"' in script
    assert 'method: "POST"' in script
    assert 'logoutButton.addEventListener("click"' in script
    assert 'setAuthState("anonymous")' in script


def test_web_contains_focused_workspace_components():
    html = WEB_INDEX.read_text(encoding="utf-8")
    styles = WEB_STYLES.read_text(encoding="utf-8")

    assert "商城智能客服" in html
    assert 'id="quick-actions"' in html
    assert 'data-message="请列出我的最近订单"' in html
    assert '<details class="debug-panel">' in html
    assert 'id="retry-auth"' in html
    assert "--color-primary" in styles
    assert "@media (max-width: 720px)" in styles
    assert ".auth-user { display: none; }" not in styles
    assert ".workspace { width: min(960px, calc(100% - 32px));" in styles
    assert ".page-footer { width: min(960px, calc(100% - 32px));" in styles


def test_web_requests_have_timeout_and_restore_controls():
    script = WEB_APP.read_text(encoding="utf-8")

    assert "async function fetchWithTimeout" in script
    assert "AbortController" in script
    assert "finally" in script
    assert "setComposerEnabled" in script
    assert "请求超时" in script
    assert "async function logoutMember" in script
    assert "退出失败" in script


def test_mall_member_login_bridges_token_to_agent_cookie():
    page = MALL_MEMBER_LOGIN.read_text(encoding="utf-8")

    assert "Mall 会员登录" in page
    assert 'fetch("/sso/login"' in page
    assert 'fetch(`${agentBaseUrl}/api/auth/session`' in page
    assert 'credentials: "include"' in page
    assert "Authorization: `${tokenHead}${token}`" in page
    assert "window.location.replace(agentBaseUrl)" in page
