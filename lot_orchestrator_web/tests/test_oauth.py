"""OAuth/OIDC verifier — JWT validation + JWKS provider (cycle 14, M1)."""
from __future__ import annotations

import json
import time
from typing import Any

import pytest

from lot_orchestrator_web.oauth import (
    JWKSProvider,
    JWTVerificationError,
    OAuthConfigError,
    OIDCConfig,
    Subject,
    verify_jwt,
)


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers — RS256 keypair + JWKS + token sign
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def rsa_keypair():
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    priv = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = priv.public_key()
    priv_pem = priv.private_bytes(
        serialization.Encoding.PEM,
        serialization.PrivateFormat.PKCS8,
        serialization.NoEncryption(),
    )
    return priv, pub, priv_pem


@pytest.fixture(scope="module")
def jwks(rsa_keypair) -> dict[str, Any]:
    """JWKS набор с одним RS256-ключом, kid='test-key-1'."""
    import jwt
    _, pub, _ = rsa_keypair
    # PyJWK.from_json для public key → JWK dict
    jwk = json.loads(jwt.algorithms.RSAAlgorithm.to_jwk(pub))
    jwk["kid"] = "test-key-1"
    jwk["use"] = "sig"
    jwk["alg"] = "RS256"
    return {"keys": [jwk]}


@pytest.fixture
def config(jwks) -> OIDCConfig:
    return OIDCConfig(
        issuer="https://test-idp.example.com",
        audience="ekcelo-api",
        jwks=jwks,
        algorithms=("RS256",),
        leeway_s=5,
    )


@pytest.fixture
def jwks_provider(jwks) -> JWKSProvider:
    return JWKSProvider(jwks)


def _sign(priv_pem: bytes, claims: dict[str, Any], *,
          kid: str = "test-key-1", alg: str = "RS256") -> str:
    import jwt
    return jwt.encode(claims, priv_pem, algorithm=alg, headers={"kid": kid})


def _base_claims(*, exp_delta_s: int = 60) -> dict[str, Any]:
    now = int(time.time())
    return {
        "iss": "https://test-idp.example.com",
        "aud": "ekcelo-api",
        "sub": "alice@example.com",
        "iat": now,
        "exp": now + exp_delta_s,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  Happy path
# ─────────────────────────────────────────────────────────────────────────────

def test_verify_valid_token_returns_subject(rsa_keypair, config, jwks_provider):
    _, _, priv_pem = rsa_keypair
    token = _sign(priv_pem, _base_claims())
    subject = verify_jwt(token, config, jwks_provider)
    assert isinstance(subject, Subject)
    assert subject.sub == "alice@example.com"
    assert subject.roles == ()


def test_verify_extracts_roles_from_claims(rsa_keypair, config, jwks_provider):
    _, _, priv_pem = rsa_keypair
    claims = _base_claims() | {"roles": ["assessor", "client"]}
    token = _sign(priv_pem, claims)
    subject = verify_jwt(token, config, jwks_provider)
    assert subject.roles == ("assessor", "client")


def test_verify_nested_roles_claim(rsa_keypair, jwks):
    """Keycloak-стиль: roles в `realm_access.roles`."""
    _, _, priv_pem = rsa_keypair
    cfg = OIDCConfig(
        issuer="https://test-idp.example.com",
        audience="ekcelo-api",
        jwks=jwks,
        algorithms=("RS256",),
        roles_claim="realm_access.roles",
    )
    claims = _base_claims() | {"realm_access": {"roles": ["superadmin"]}}
    token = _sign(priv_pem, claims)
    subject = verify_jwt(token, cfg, JWKSProvider(jwks))
    assert subject.roles == ("superadmin",)


# ─────────────────────────────────────────────────────────────────────────────
#  Negative paths
# ─────────────────────────────────────────────────────────────────────────────

def test_verify_rejects_expired_token(rsa_keypair, config, jwks_provider):
    _, _, priv_pem = rsa_keypair
    # exp в прошлом + minus leeway
    claims = _base_claims(exp_delta_s=-120)
    token = _sign(priv_pem, claims)
    with pytest.raises(JWTVerificationError, match="expired"):
        verify_jwt(token, config, jwks_provider)


def test_verify_rejects_wrong_audience(rsa_keypair, config, jwks_provider):
    _, _, priv_pem = rsa_keypair
    claims = _base_claims() | {"aud": "OTHER-api"}
    token = _sign(priv_pem, claims)
    with pytest.raises(JWTVerificationError, match="audience"):
        verify_jwt(token, config, jwks_provider)


def test_verify_rejects_wrong_issuer(rsa_keypair, config, jwks_provider):
    _, _, priv_pem = rsa_keypair
    claims = _base_claims() | {"iss": "https://evil-idp.example.com"}
    token = _sign(priv_pem, claims)
    with pytest.raises(JWTVerificationError, match="issuer"):
        verify_jwt(token, config, jwks_provider)


def test_verify_rejects_unknown_kid(rsa_keypair, config, jwks_provider):
    _, _, priv_pem = rsa_keypair
    token = _sign(priv_pem, _base_claims(), kid="ghost-key")
    with pytest.raises(JWTVerificationError, match="JWK"):
        verify_jwt(token, config, jwks_provider)


def test_verify_rejects_disallowed_algorithm(rsa_keypair, jwks_provider):
    _, _, priv_pem = rsa_keypair
    cfg = OIDCConfig(
        issuer="https://test-idp.example.com",
        audience="ekcelo-api",
        jwks={"keys": []},
        algorithms=("RS512",),  # запретили RS256
    )
    token = _sign(priv_pem, _base_claims())
    with pytest.raises(JWTVerificationError, match="alg"):
        verify_jwt(token, cfg, jwks_provider)


def test_verify_rejects_token_without_sub(rsa_keypair, config, jwks_provider):
    _, _, priv_pem = rsa_keypair
    claims = _base_claims()
    claims.pop("sub")
    token = _sign(priv_pem, claims)
    with pytest.raises(JWTVerificationError, match="sub"):
        verify_jwt(token, config, jwks_provider)


def test_verify_rejects_malformed_jwt(config, jwks_provider):
    with pytest.raises(JWTVerificationError):
        verify_jwt("not.a.jwt", config, jwks_provider)


# ─────────────────────────────────────────────────────────────────────────────
#  HS256 (test/dev mode — без cryptography RS-ключей)
# ─────────────────────────────────────────────────────────────────────────────

def test_verify_hs256_with_hmac_secret(jwks_provider):
    import jwt
    cfg = OIDCConfig(
        issuer="https://test-idp.example.com",
        audience="ekcelo-api",
        jwks={"keys": []},
        algorithms=("HS256",),
    )
    token = jwt.encode(_base_claims(), "shared-secret", algorithm="HS256")
    subject = verify_jwt(token, cfg, jwks_provider, hmac_secret="shared-secret")
    assert subject.sub == "alice@example.com"


def test_verify_hs256_without_secret_raises(jwks_provider):
    import jwt
    cfg = OIDCConfig(
        issuer="https://test-idp.example.com",
        audience="ekcelo-api",
        jwks={"keys": []},
        algorithms=("HS256",),
    )
    token = jwt.encode(_base_claims(), "shared-secret", algorithm="HS256")
    with pytest.raises(OAuthConfigError, match="hmac_secret"):
        verify_jwt(token, cfg, jwks_provider)


# ─────────────────────────────────────────────────────────────────────────────
#  OIDCConfig.from_env
# ─────────────────────────────────────────────────────────────────────────────

def test_config_from_env_returns_none_when_no_issuer(monkeypatch):
    for k in ("EKCELO_OIDC_ISSUER", "EKCELO_OIDC_AUDIENCE", "EKCELO_OIDC_JWKS_URL"):
        monkeypatch.delenv(k, raising=False)
    assert OIDCConfig.from_env() is None


def test_config_from_env_requires_audience(monkeypatch):
    monkeypatch.setenv("EKCELO_OIDC_ISSUER", "https://idp")
    monkeypatch.delenv("EKCELO_OIDC_AUDIENCE", raising=False)
    monkeypatch.setenv("EKCELO_OIDC_JWKS_URL", "https://idp/jwks")
    with pytest.raises(OAuthConfigError, match="AUDIENCE"):
        OIDCConfig.from_env()


def test_config_from_env_requires_jwks(monkeypatch):
    monkeypatch.setenv("EKCELO_OIDC_ISSUER", "https://idp")
    monkeypatch.setenv("EKCELO_OIDC_AUDIENCE", "api")
    monkeypatch.delenv("EKCELO_OIDC_JWKS_URL", raising=False)
    with pytest.raises(OAuthConfigError, match="JWKS"):
        OIDCConfig.from_env()


def test_config_from_env_full(monkeypatch):
    monkeypatch.setenv("EKCELO_OIDC_ISSUER", "https://idp")
    monkeypatch.setenv("EKCELO_OIDC_AUDIENCE", "ekcelo-api")
    monkeypatch.setenv("EKCELO_OIDC_JWKS_URL", "https://idp/.well-known/jwks.json")
    monkeypatch.setenv("EKCELO_OIDC_ROLES_CLAIM", "realm_access.roles")
    cfg = OIDCConfig.from_env()
    assert cfg is not None
    assert cfg.issuer == "https://idp"
    assert cfg.audience == "ekcelo-api"
    assert cfg.jwks == "https://idp/.well-known/jwks.json"
    assert cfg.roles_claim == "realm_access.roles"


# ─────────────────────────────────────────────────────────────────────────────
#  JWKSProvider — cache
# ─────────────────────────────────────────────────────────────────────────────

def test_jwks_provider_static_dict():
    provider = JWKSProvider({"keys": [{"kid": "k1"}]})
    assert provider.get_keys() == {"keys": [{"kid": "k1"}]}


def test_jwks_provider_callable_cached():
    calls = []
    def src():
        calls.append(1)
        return {"keys": [{"kid": f"k{len(calls)}"}]}
    provider = JWKSProvider(src, ttl_s=600)
    provider.get_keys()
    provider.get_keys()
    assert len(calls) == 1  # второй вызов из кеша


def test_jwks_provider_ttl_expiry():
    calls = []
    def src():
        calls.append(1)
        return {"keys": []}
    provider = JWKSProvider(src, ttl_s=0)  # сразу истекает
    provider.get_keys()
    time.sleep(0.01)
    provider.get_keys()
    assert len(calls) == 2
