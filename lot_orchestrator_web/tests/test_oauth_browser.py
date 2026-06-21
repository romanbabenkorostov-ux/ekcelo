"""Cycle 14 M2 — OAuth2 browser code-flow (/auth/login + /auth/callback)."""
from __future__ import annotations

import json
import time
import urllib.parse

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from lot_orchestrator_web.oauth import (
    JWKSProvider,
    OAuthMiddleware,
    OIDCConfig,
    SESSION_COOKIE,
)
from lot_orchestrator_web.oauth_browser import (
    OAuthBrowserConfig,
    register_auth_routes,
)


@pytest.fixture
def browser_cfg() -> OAuthBrowserConfig:
    return OAuthBrowserConfig(
        client_id="ekcelo-client",
        client_secret="shh",
        authorize_url="https://idp.example.com/authorize",
        token_url="https://idp.example.com/token",
        redirect_uri="https://app.ekcelo.ru/auth/callback",
        scopes="openid profile",
        post_login_redirect="/",
        cookie_secure=False,  # local dev — TestClient http
    )


def _rs256_keypair_jwks():
    import jwt
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = priv.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(priv.public_key()))
    jwk["kid"] = "k1"; jwk["use"] = "sig"; jwk["alg"] = "RS256"
    return pem, {"keys": [jwk]}


def _sign(pem, claims):
    import jwt
    return jwt.encode(claims, pem, algorithm="RS256", headers={"kid": "k1"})


def _app(browser_cfg, *, exchanger):
    app = FastAPI()
    register_auth_routes(app, config=browser_cfg, token_exchanger=exchanger)
    return app


# ─────────────────────────────────────────────────────────────────────────────
#  /auth/login
# ─────────────────────────────────────────────────────────────────────────────

def test_login_redirects_to_authorize(browser_cfg):
    app = _app(browser_cfg, exchanger=lambda code, cfg: {})
    client = TestClient(app)
    resp = client.get("/auth/login", follow_redirects=False)
    assert resp.status_code == 307
    loc = resp.headers["location"]
    assert loc.startswith("https://idp.example.com/authorize?")
    q = urllib.parse.parse_qs(urllib.parse.urlparse(loc).query)
    assert q["response_type"] == ["code"]
    assert q["client_id"] == ["ekcelo-client"]
    assert q["redirect_uri"] == ["https://app.ekcelo.ru/auth/callback"]
    assert q["scope"] == ["openid profile"]
    assert "state" in q
    # state записан в cookie
    assert "ekcelo_oauth_state" in resp.cookies


# ─────────────────────────────────────────────────────────────────────────────
#  /auth/callback
# ─────────────────────────────────────────────────────────────────────────────

def test_callback_exchanges_code_and_sets_cookie(browser_cfg):
    captured = {}

    def exchanger(code, cfg):
        captured["code"] = code
        return {"id_token": "the-jwt-token", "access_token": "ignored"}

    app = _app(browser_cfg, exchanger=exchanger)
    client = TestClient(app)
    # login чтобы получить state-cookie
    client.get("/auth/login", follow_redirects=False)
    state = client.cookies.get("ekcelo_oauth_state")
    resp = client.get(
        f"/auth/callback?code=authcode123&state={state}",
        follow_redirects=False,
    )
    assert resp.status_code == 307
    assert resp.headers["location"] == "/"
    assert captured["code"] == "authcode123"
    assert client.cookies.get(SESSION_COOKIE) == "the-jwt-token"


def test_callback_missing_code_400(browser_cfg):
    app = _app(browser_cfg, exchanger=lambda code, cfg: {})
    client = TestClient(app)
    client.get("/auth/login", follow_redirects=False)
    state = client.cookies.get("ekcelo_oauth_state")
    resp = client.get(f"/auth/callback?state={state}", follow_redirects=False)
    assert resp.status_code == 400


def test_callback_state_mismatch_400(browser_cfg):
    app = _app(browser_cfg, exchanger=lambda code, cfg: {"id_token": "x"})
    client = TestClient(app)
    client.get("/auth/login", follow_redirects=False)
    resp = client.get(
        "/auth/callback?code=c&state=WRONG-STATE", follow_redirects=False,
    )
    assert resp.status_code == 400
    assert "state" in resp.json()["detail"].lower()


def test_callback_no_state_cookie_400(browser_cfg):
    app = _app(browser_cfg, exchanger=lambda code, cfg: {"id_token": "x"})
    client = TestClient(app)
    # без предварительного /auth/login → нет state-cookie
    resp = client.get("/auth/callback?code=c&state=s", follow_redirects=False)
    assert resp.status_code == 400


def test_callback_exchange_failure_502(browser_cfg):
    def bad_exchanger(code, cfg):
        raise RuntimeError("IdP down")

    app = _app(browser_cfg, exchanger=bad_exchanger)
    client = TestClient(app)
    client.get("/auth/login", follow_redirects=False)
    state = client.cookies.get("ekcelo_oauth_state")
    resp = client.get(
        f"/auth/callback?code=c&state={state}", follow_redirects=False,
    )
    assert resp.status_code == 502


def test_callback_empty_token_response_502(browser_cfg):
    app = _app(browser_cfg, exchanger=lambda code, cfg: {"foo": "bar"})
    client = TestClient(app)
    client.get("/auth/login", follow_redirects=False)
    state = client.cookies.get("ekcelo_oauth_state")
    resp = client.get(
        f"/auth/callback?code=c&state={state}", follow_redirects=False,
    )
    assert resp.status_code == 502


def test_callback_prefers_id_token_over_access(browser_cfg):
    app = _app(browser_cfg, exchanger=lambda c, cfg: {
        "id_token": "ID", "access_token": "ACCESS"})
    client = TestClient(app)
    client.get("/auth/login", follow_redirects=False)
    state = client.cookies.get("ekcelo_oauth_state")
    client.get(f"/auth/callback?code=c&state={state}", follow_redirects=False)
    assert client.cookies.get(SESSION_COOKIE) == "ID"


def test_callback_falls_back_to_access_token(browser_cfg):
    app = _app(browser_cfg, exchanger=lambda c, cfg: {"access_token": "ACCESS"})
    client = TestClient(app)
    client.get("/auth/login", follow_redirects=False)
    state = client.cookies.get("ekcelo_oauth_state")
    client.get(f"/auth/callback?code=c&state={state}", follow_redirects=False)
    assert client.cookies.get(SESSION_COOKIE) == "ACCESS"


# ─────────────────────────────────────────────────────────────────────────────
#  /auth/logout
# ─────────────────────────────────────────────────────────────────────────────

def test_logout_clears_cookie(browser_cfg):
    app = _app(browser_cfg, exchanger=lambda c, cfg: {"id_token": "x"})
    client = TestClient(app)
    resp = client.get("/auth/logout")
    assert resp.status_code == 200
    # Set-Cookie с истёкшим cookie
    assert "ekcelo_token" in resp.headers.get("set-cookie", "")


# ─────────────────────────────────────────────────────────────────────────────
#  Config.from_env
# ─────────────────────────────────────────────────────────────────────────────

def test_config_from_env_none_without_client_id(monkeypatch):
    monkeypatch.delenv("EKCELO_OIDC_CLIENT_ID", raising=False)
    assert OAuthBrowserConfig.from_env() is None


def test_config_from_env_partial_raises(monkeypatch):
    monkeypatch.setenv("EKCELO_OIDC_CLIENT_ID", "cid")
    for k in ("EKCELO_OIDC_CLIENT_SECRET", "EKCELO_OIDC_AUTHORIZE_URL",
              "EKCELO_OIDC_TOKEN_URL", "EKCELO_OIDC_REDIRECT_URI"):
        monkeypatch.delenv(k, raising=False)
    from lot_orchestrator_web.oauth_browser import OAuthBrowserConfigError
    with pytest.raises(OAuthBrowserConfigError):
        OAuthBrowserConfig.from_env()


def test_config_from_env_full(monkeypatch):
    monkeypatch.setenv("EKCELO_OIDC_CLIENT_ID", "cid")
    monkeypatch.setenv("EKCELO_OIDC_CLIENT_SECRET", "sec")
    monkeypatch.setenv("EKCELO_OIDC_AUTHORIZE_URL", "https://idp/authorize")
    monkeypatch.setenv("EKCELO_OIDC_TOKEN_URL", "https://idp/token")
    monkeypatch.setenv("EKCELO_OIDC_REDIRECT_URI", "https://app/auth/callback")
    cfg = OAuthBrowserConfig.from_env()
    assert cfg is not None
    assert cfg.client_id == "cid"
    assert cfg.token_url == "https://idp/token"


def test_register_returns_false_when_no_config(monkeypatch):
    monkeypatch.delenv("EKCELO_OIDC_CLIENT_ID", raising=False)
    app = FastAPI()
    assert register_auth_routes(app) is False


# ─────────────────────────────────────────────────────────────────────────────
#  End-to-end: callback cookie → OAuthMiddleware принимает
# ─────────────────────────────────────────────────────────────────────────────

def test_cookie_token_accepted_by_middleware(browser_cfg):
    """После login cookie с валидным JWT проходит OAuthMiddleware (M1)."""
    pem, jwks = _rs256_keypair_jwks()
    now = int(time.time())
    valid_jwt = _sign(pem, {
        "iss": "https://idp", "aud": "ekcelo-api",
        "sub": "alice", "iat": now, "exp": now + 60,
    })

    app = FastAPI()
    register_auth_routes(
        app, config=browser_cfg,
        token_exchanger=lambda c, cfg: {"id_token": valid_jwt},
    )
    oidc = OIDCConfig(issuer="https://idp", audience="ekcelo-api",
                       jwks=jwks, algorithms=("RS256",))
    app.add_middleware(OAuthMiddleware, config=oidc,
                       jwks_provider=JWKSProvider(jwks))

    @app.get("/api/me")
    async def me(request: Request):
        return {"sub": request.state.subject.sub}

    client = TestClient(app)
    # без cookie → 401
    assert client.get("/api/me").status_code == 401
    # пройти login + callback → cookie установлен
    client.get("/auth/login", follow_redirects=False)
    state = client.cookies.get("ekcelo_oauth_state")
    client.get(f"/auth/callback?code=c&state={state}", follow_redirects=False)
    # теперь cookie несёт валидный JWT → 200
    resp = client.get("/api/me")
    assert resp.status_code == 200
    assert resp.json()["sub"] == "alice"
