"""OAuthMiddleware — Bearer-валидация на реальном FastAPI app (cycle 14, M1)."""
from __future__ import annotations

import json
import time
from typing import Any

import pytest
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient

from lot_orchestrator_web.oauth import (
    JWKSProvider,
    OAuthMiddleware,
    OIDCConfig,
)


@pytest.fixture(scope="module")
def rsa_keypair():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = priv.public_key()
    pem = priv.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return priv, pub, pem


@pytest.fixture(scope="module")
def jwks(rsa_keypair):
    import jwt
    _, pub, _ = rsa_keypair
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(pub))
    jwk["kid"] = "k1"
    jwk["use"] = "sig"
    jwk["alg"] = "RS256"
    return {"keys": [jwk]}


@pytest.fixture
def config(jwks):
    return OIDCConfig(
        issuer="https://idp", audience="ekcelo-api",
        jwks=jwks, algorithms=("RS256",),
    )


@pytest.fixture
def app(config) -> FastAPI:
    a = FastAPI()
    a.add_middleware(
        OAuthMiddleware, config=config,
        jwks_provider=JWKSProvider(config.jwks),
    )

    @a.get("/")
    async def root():
        return {"ok": True}

    @a.get("/api/me")
    async def me(request: Request):
        s = request.state.subject
        return {"sub": s.sub, "roles": list(s.roles)}

    @a.get("/static/file.css")
    async def static_file():
        return {"ok": "static"}
    return a


def _sign(priv_pem: bytes, *, exp_delta_s: int = 60,
          roles: list[str] | None = None) -> str:
    import jwt
    now = int(time.time())
    claims = {
        "iss": "https://idp", "aud": "ekcelo-api", "sub": "alice@example",
        "iat": now, "exp": now + exp_delta_s,
    }
    if roles is not None:
        claims["roles"] = roles
    return jwt.encode(claims, priv_pem, algorithm="RS256", headers={"kid": "k1"})


# ─────────────────────────────────────────────────────────────────────────────
#  Tests
# ─────────────────────────────────────────────────────────────────────────────

def test_root_exempt_no_auth_needed(app):
    client = TestClient(app)
    assert client.get("/").status_code == 200


def test_static_exempt(app):
    client = TestClient(app)
    assert client.get("/static/file.css").status_code == 200


def test_protected_endpoint_requires_bearer(app):
    client = TestClient(app)
    resp = client.get("/api/me")
    assert resp.status_code == 401
    assert "missing Bearer" in resp.json()["detail"]
    assert "Bearer" in resp.headers.get("WWW-Authenticate", "")


def test_protected_endpoint_with_valid_token(app, rsa_keypair):
    _, _, pem = rsa_keypair
    token = _sign(pem, roles=["assessor"])
    client = TestClient(app)
    resp = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["sub"] == "alice@example"
    assert body["roles"] == ["assessor"]


def test_protected_endpoint_rejects_expired(app, rsa_keypair):
    _, _, pem = rsa_keypair
    token = _sign(pem, exp_delta_s=-3600)
    client = TestClient(app)
    resp = client.get("/api/me", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 401
    assert "expired" in resp.json()["detail"]


def test_protected_endpoint_rejects_garbage_token(app):
    client = TestClient(app)
    resp = client.get("/api/me", headers={"Authorization": "Bearer not.a.token"})
    assert resp.status_code == 401


def test_non_bearer_authorization_rejected(app):
    client = TestClient(app)
    resp = client.get("/api/me", headers={"Authorization": "Basic Zm9vOmJhcg=="})
    assert resp.status_code == 401
    assert "missing Bearer" in resp.json()["detail"]
