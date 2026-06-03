"""password hashing (cycle 13) — pbkdf2 + backward-compat plaintext."""
from __future__ import annotations

import sys

import pytest

from lot_orchestrator_web.password import (
    hash_password,
    is_hashed,
    main,
    verify_password,
)


# ── hash_password ─────────────────────────────────────────────────────────────

def test_hash_format():
    h = hash_password("secret")
    parts = h.split("$")
    assert len(parts) == 4
    assert parts[0] == "pbkdf2_sha256"
    assert int(parts[1]) >= 600_000          # iterations
    assert len(bytes.fromhex(parts[2])) == 16  # salt 16 bytes
    assert len(bytes.fromhex(parts[3])) == 32  # sha256 digest


def test_hash_no_colon_or_comma():
    """Хеш безопасен внутри EKCELO_AUTH_USERS (split по ':' и ',')."""
    h = hash_password("p@ss,word:with:specials")
    assert ":" not in h
    assert "," not in h


def test_hash_is_salted_unique():
    """Один пароль → разные хеши (разная соль)."""
    assert hash_password("same") != hash_password("same")


def test_custom_iterations():
    h = hash_password("x", iterations=700_000)
    assert h.split("$")[1] == "700000"


# ── is_hashed ─────────────────────────────────────────────────────────────────

def test_is_hashed_true_for_pbkdf2():
    assert is_hashed(hash_password("x"))


def test_is_hashed_false_for_plaintext():
    assert not is_hashed("just-a-plain-password")
    assert not is_hashed("")


# ── verify_password ───────────────────────────────────────────────────────────

def test_verify_hashed_correct():
    h = hash_password("correct horse")
    assert verify_password("correct horse", h)


def test_verify_hashed_wrong():
    h = hash_password("correct horse")
    assert not verify_password("wrong", h)


def test_verify_plaintext_backward_compat():
    assert verify_password("plain", "plain")
    assert not verify_password("plain", "other")


def test_verify_malformed_hash_returns_false():
    assert not verify_password("x", "pbkdf2_sha256$notanint$zz$zz")
    assert not verify_password("x", "pbkdf2_sha256$600000$xyz")  # too few parts


def test_verify_wrong_scheme_in_hashlike():
    # начинается не с нашего scheme → трактуется как plaintext, не равен
    assert not verify_password("x", "bcrypt$abc$def")


# ── round trip ────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("pw", ["a", "Пароль123", "p:с,$pecial", "x" * 200, " spaced "])
def test_roundtrip(pw):
    assert verify_password(pw, hash_password(pw))
    assert not verify_password(pw + "x", hash_password(pw))


# ── CLI ───────────────────────────────────────────────────────────────────────

def test_cli_prints_hash(capsys):
    rc = main(["mysecret"])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert is_hashed(out)
    assert verify_password("mysecret", out)


def test_cli_with_user_prints_entry(capsys):
    rc = main(["--user", "alice", "topsecret"])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    user, _, token = out.partition(":")
    assert user == "alice"
    assert verify_password("topsecret", token)


def test_cli_empty_password_errors(capsys):
    rc = main([""])
    assert rc == 2
    assert "пустой пароль" in capsys.readouterr().err


def test_cli_custom_iterations(capsys):
    rc = main(["--iterations", "650000", "pw"])
    assert rc == 0
    out = capsys.readouterr().out.strip()
    assert out.split("$")[1] == "650000"
