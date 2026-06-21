"""Cycle 16 — rate-limit integration в BasicAuthMiddleware + OAuthMiddleware."""
from __future__ import annotations

import base64
import json
import time
from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from lot_orchestrator_web.auth import (
    BasicAuthMiddleware,
    _Creds,
    parse_roles_map,
)
from lot_orchestrator_web.oauth import (
    JWKSProvider,
    OAuthMiddleware,
    OIDCConfig,
)
from lot_orchestrator_web.ratelimit import RateLimitConfig, RateLimiter


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

class _Clock:
    def __init__(self, t: float = 1000.0):
        self.t = t

    def __call__(self) -> float:
        return self.t

    def tick(self, dt: float) -> None:
        self.t += dt


def _basic(user: str, pw: str) -> dict[str, str]:
    token = base64.b64encode(f"{user}:{pw}".encode()).decode()
    return {"Authorization": f"Basic {token}"}


# ─────────────────────────────────────────────────────────────────────────────
#  Basic Auth + rate-limit
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def basic_app():
    clock = _Clock()
    cfg = RateLimitConfig(enabled=True, fails_limit=3, window_s=60, block_s=120)
    limiter = RateLimiter(cfg, clock=clock)
    creds = _Creds(users={"alice": "secret"})

    app = FastAPI()
    app.state.rate_limiter = limiter
    app.add_middleware(BasicAuthMiddleware, creds=creds, roles_map={})

    @app.get("/api")
    async def api():
        return {"ok": True}

    return app, limiter, clock


def test_basic_unauth_increments_failures(basic_app):
    app, limiter, _ = basic_app
    client = TestClient(app)
    resp = client.get("/api", headers=_basic("alice", "wrong"))
    assert resp.status_code == 401
    # один провал записан (ключ basic:testclient:alice)


def test_basic_limit_triggers_429_with_retry_after(basic_app):
    app, limiter, _ = basic_app
    client = TestClient(app)
    for _ in range(3):
        client.get("/api", headers=_basic("alice", "wrong"))
    resp = client.get("/api", headers=_basic("alice", "wrong"))
    assert resp.status_code == 429
    assert int(resp.headers["Retry-After"]) > 0
    assert "Too many" in resp.json()["detail"]


def test_basic_success_resets_counter(basic_app):
    app, limiter, _ = basic_app
    client = TestClient(app)
    # 2 провала
    client.get("/api", headers=_basic("alice", "wrong"))
    client.get("/api", headers=_basic("alice", "wrong"))
    # успех сбрасывает счётчик
    resp = client.get("/api", headers=_basic("alice", "secret"))
    assert resp.status_code == 200
    # ещё 2 провала не должны заблокировать
    client.get("/api", headers=_basic("alice", "wrong"))
    resp2 = client.get("/api", headers=_basic("alice", "wrong"))
    assert resp2.status_code == 401  # не 429


def test_basic_block_expires_after_window(basic_app):
    app, limiter, clock = basic_app
    client = TestClient(app)
    for _ in range(3):
        client.get("/api", headers=_basic("alice", "wrong"))
    assert client.get("/api", headers=_basic("alice", "wrong")).status_code == 429
    # время идёт
    clock.tick(121.0)  # block_s=120 истёк
    # теперь снова можно попробовать (получим 401, не 429)
    resp = client.get("/api", headers=_basic("alice", "wrong"))
    assert resp.status_code == 401


def test_basic_different_usernames_separate_buckets(basic_app):
    app, limiter, _ = basic_app
    client = TestClient(app)
    # alice заблокирована
    for _ in range(3):
        client.get("/api", headers=_basic("alice", "wrong"))
    assert client.get("/api", headers=_basic("alice", "wrong")).status_code == 429
    # bob свой счётчик имеет
    resp = client.get("/api", headers=_basic("bob", "wrong"))
    assert resp.status_code == 401


def test_basic_no_limiter_unchanged_behavior():
    """Если app.state.rate_limiter не задан — middleware работает как раньше."""
    creds = _Creds(users={"alice": "secret"})
    app = FastAPI()
    # rate_limiter НЕ установлен
    app.add_middleware(BasicAuthMiddleware, creds=creds)

    @app.get("/api")
    async def api():
        return {"ok": True}

    client = TestClient(app)
    for _ in range(20):
        resp = client.get("/api", headers=_basic("alice", "wrong"))
        assert resp.status_code == 401  # никогда 429


# ─────────────────────────────────────────────────────────────────────────────
#  OAuth Bearer + rate-limit
# ─────────────────────────────────────────────────────────────────────────────

def _make_jwks_and_signer():
    """Возвращает (jwks, signer_fn). signer_fn(claims) → jwt string."""
    import jwt
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = priv.public_key()
    pem = priv.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(pub))
    jwk["kid"] = "k1"
    jwk["use"] = "sig"
    jwk["alg"] = "RS256"
    jwks = {"keys": [jwk]}

    def sign(claims):
        return jwt.encode(claims, pem, algorithm="RS256", headers={"kid": "k1"})

    return jwks, sign


@pytest.fixture
def bearer_app():
    clock = _Clock()
    cfg = RateLimitConfig(enabled=True, fails_limit=3, window_s=60, block_s=120)
    limiter = RateLimiter(cfg, clock=clock)
    jwks, sign = _make_jwks_and_signer()
    oidc = OIDCConfig(issuer="https://idp", audience="api",
                       jwks=jwks, algorithms=("RS256",))

    app = FastAPI()
    app.state.rate_limiter = limiter
    app.add_middleware(
        OAuthMiddleware, config=oidc, jwks_provider=JWKSProvider(jwks),
    )

    @app.get("/api")
    async def api():
        return {"ok": True}

    return app, limiter, clock, sign


def test_bearer_invalid_token_increments(bearer_app):
    app, _, _, _ = bearer_app
    client = TestClient(app)
    for _ in range(3):
        client.get("/api", headers={"Authorization": "Bearer garbage"})
    resp = client.get("/api", headers={"Authorization": "Bearer garbage"})
    assert resp.status_code == 429
    assert "Retry-After" in resp.headers


def test_bearer_missing_token_also_counts(bearer_app):
    app, _, _, _ = bearer_app
    client = TestClient(app)
    for _ in range(3):
        client.get("/api")  # без Authorization
    resp = client.get("/api")
    assert resp.status_code == 429


def test_bearer_valid_token_resets(bearer_app):
    app, _, _, sign = bearer_app
    client = TestClient(app)
    # 2 провала
    client.get("/api", headers={"Authorization": "Bearer garbage"})
    client.get("/api", headers={"Authorization": "Bearer garbage"})
    # валидный токен сбрасывает
    now = int(time.time())
    valid = sign({"iss": "https://idp", "aud": "api",
                  "sub": "alice", "iat": now, "exp": now + 60})
    resp = client.get("/api", headers={"Authorization": f"Bearer {valid}"})
    assert resp.status_code == 200
    # ещё 2 провала не блокируют
    client.get("/api", headers={"Authorization": "Bearer garbage"})
    resp2 = client.get("/api", headers={"Authorization": "Bearer garbage"})
    assert resp2.status_code == 401  # не 429
