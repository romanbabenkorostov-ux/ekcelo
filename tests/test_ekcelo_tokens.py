"""Round-trip и edge cases для tools/ekcelo_tokens.py."""

from __future__ import annotations

import json
import pathlib
import sys

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import ekcelo_tokens as et  # noqa: E402


VALID_URLS = [
    "https://disk.yandex.ru/d/GLA8p8oHpnv9NA",
    "http://a/",
    "https://example.com/path?x=1&y=2#frag",
    "https://ru.wikipedia.org/wiki/%D0%9F%D1%80%D0%B8%D0%B2%D0%B5%D1%82",
    "https://example.com/" + "a" * 500,
]


@pytest.mark.parametrize("url", VALID_URLS)
def test_roundtrip(url: str) -> None:
    tok = et.encode(url)
    assert "=" not in tok
    assert all(c in "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_" for c in tok)
    assert et.decode(tok) == url


def test_build_short_url() -> None:
    url = "https://disk.yandex.ru/d/GLA8p8oHpnv9NA"
    short = et.build_short_url(url)
    assert short.startswith("https://ekcelo.ru/?t=")
    assert short.endswith(et.encode(url))


@pytest.mark.parametrize(
    "bad_url",
    [
        "ftp://example.com/",
        "javascript:alert(1)",
        "not a url",
        "://nohost",
        "",
    ],
)
def test_encode_rejects_bad(bad_url: str) -> None:
    with pytest.raises(ValueError):
        et.encode(bad_url)


@pytest.mark.parametrize(
    "bad_token",
    [
        "",
        "!!!",
        "has space",
        "padding====",
        "ZnRwOi8vYS5jb20",  # base64 of "ftp://a.com" — scheme не разрешена
    ],
)
def test_decode_rejects_bad(bad_token: str) -> None:
    assert et.decode(bad_token) is None


def test_decode_non_utf8() -> None:
    import base64 as b64

    raw = b"\xff\xfe\xfd"
    tok = b64.urlsafe_b64encode(raw).rstrip(b"=").decode()
    assert et.decode(tok) is None


def test_fixture_for_js_parity(tmp_path: pathlib.Path) -> None:
    """Создаёт фикстуру для test_tokens_js.mjs если её ещё нет.

    Запуск: pytest tests/test_ekcelo_tokens.py::test_fixture_for_js_parity
    """
    fx_path = ROOT / "tests" / "fixtures" / "token_roundtrip.json"
    fx_path.parent.mkdir(parents=True, exist_ok=True)
    data = [{"url": u, "token": et.encode(u)} for u in VALID_URLS]
    fx_path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    loaded = json.loads(fx_path.read_text(encoding="utf-8"))
    assert loaded == data


# --- v3 (contracts/token/TOKEN_SPEC.md §5) ---------------------------------

V3_VECTOR = "eyJ2IjozLCJwayI6Imh0dHBzOi8vZGlzay55YW5kZXgucnUvZC9BYkNkRWYxMjMiLCJrbXoiOiIv0JrQvtC90YLRg9GA0Ytf0JHQntChLmtteiIsImh0bWwiOiIv0J7RgtGH0ZHRgl_QkdCe0KEuaHRtbCIsIm5hbWUiOiLQkdCe0KEg0J_RgtC40YbQtdCy0L7QtNGB0YLQstC-IiwiZXhwIjoiMjAyNi0xMi0zMSJ9.93avUWqHO9XBXYjP4iQ2gA"


def test_v3_matches_spec_vector() -> None:
    tok = et.issue_v3("https://disk.yandex.ru/d/AbCdEf123", "test-secret-0123456789",
                      kmz="/Контуры_БОС.kmz", html="/Отчёт_БОС.html",
                      name="БОС Птицеводство", exp="2026-12-31")
    assert tok == V3_VECTOR
    assert et.verify_v3(tok, "test-secret-0123456789")["kmz"] == "/Контуры_БОС.kmz"
    assert et.verify_v3(tok, "другой-секрет-0123456789") is None
    assert et.decode(tok) is None  # v2-декодер v3 не принимает


def test_v3_needs_secret_and_path() -> None:
    with pytest.raises(ValueError):
        et.issue_v3("https://disk.yandex.ru/d/x", "короткий", kmz="/a.kmz")
    with pytest.raises(ValueError):
        et.issue_v3("https://disk.yandex.ru/d/x", "test-secret-0123456789")
