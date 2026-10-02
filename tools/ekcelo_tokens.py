#!/usr/bin/env python3
"""Ekcelo token-system — stateless self-contained URL shortener.

v2:
    encode: url -> base64url(UTF-8(url)) без padding
    decode: token -> url (после восстановления padding и проверки схемы)

v3 (contracts/token/TOKEN_SPEC.md): <payload>.<sig> — папка Яндекс.Диска,
пути HTML и KMZ, срок; подпись HMAC-SHA256 с секретом EKCELO_TOKEN_SECRET.
Проверяет воркер ekcelo-site (/token), здесь — выпуск и проверка для тестов.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import hmac
import json
import os
import sys
from urllib.parse import urlsplit

ALLOWED_SCHEMES = ("http", "https")
DEFAULT_BASE = "https://ekcelo.ru/"


def _is_allowed_url(s: str) -> bool:
    try:
        u = urlsplit(s)
    except ValueError:
        return False
    return u.scheme in ALLOWED_SCHEMES and bool(u.netloc)


def encode(url: str) -> str:
    if not isinstance(url, str) or not _is_allowed_url(url):
        raise ValueError("encode: требуется http(s) URL")
    return base64.urlsafe_b64encode(url.encode("utf-8")).rstrip(b"=").decode("ascii")


def decode(token: str) -> str | None:
    if not isinstance(token, str) or not token:
        return None
    if any(c not in _B64URL_ALPHABET for c in token):
        return None
    pad = "=" * (-len(token) % 4)
    try:
        raw = base64.urlsafe_b64decode(token + pad)
        url = raw.decode("utf-8")
    except (ValueError, UnicodeDecodeError):
        return None
    return url if _is_allowed_url(url) else None


def build_short_url(url: str, base: str = DEFAULT_BASE) -> str:
    return base + "?t=" + encode(url)


def _b64(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _sign(secret: str, payload: str) -> str:
    return _b64(hmac.new(secret.encode("utf-8"), payload.encode("ascii"),
                         hashlib.sha256).digest()[:16])


def issue_v3(pk: str, secret: str, kmz: str = "", html: str = "",
             name: str = "", exp: str = "") -> str:
    """Токен v3: ключи в порядке спецификации, компактный JSON UTF-8."""
    if not _is_allowed_url(pk) or not (kmz or html):
        raise ValueError("issue_v3: нужна ссылка на папку и хотя бы один путь")
    if len(secret or "") < 16:
        raise ValueError("issue_v3: секрет — не короче 16 символов")
    data = {"v": 3, "pk": pk}
    for key, value in (("kmz", kmz), ("html", html), ("name", name), ("exp", exp)):
        if value:
            data[key] = value
    payload = _b64(json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    return payload + "." + _sign(secret, payload)


def verify_v3(token: str, secret: str) -> dict | None:
    """Содержимое токена, если подпись верна (срок проверяет воркер)."""
    payload, _, sig = (token or "").partition(".")
    if not payload or not sig or not hmac.compare_digest(_sign(secret, payload), sig):
        return None
    try:
        return json.loads(base64.urlsafe_b64decode(payload + "=" * (-len(payload) % 4)))
    except ValueError:
        return None


_B64URL_ALPHABET = frozenset(
    "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_"
)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="ekcelo_tokens", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("encode", help="URL -> токен")
    s.add_argument("url")

    s = sub.add_parser("decode", help="токен -> URL")
    s.add_argument("token")

    s = sub.add_parser("url", help="URL -> короткая ссылка")
    s.add_argument("url")
    s.add_argument("--base", default=DEFAULT_BASE)

    s = sub.add_parser("v3", help="папка Диска -> токен v3 с подписью "
                                  "(секрет в EKCELO_TOKEN_SECRET)")
    s.add_argument("--pk", required=True, help="публичная ссылка на папку")
    s.add_argument("--kmz", default="", help="путь KMZ в папке: /Контуры_….kmz")
    s.add_argument("--html", default="", help="путь отчёта в папке: /….html")
    s.add_argument("--name", default="", help="название проекта (без ФИО)")
    s.add_argument("--exp", default="", help="действует по YYYY-MM-DD")
    s.add_argument("--base", default=DEFAULT_BASE)

    args = p.parse_args(argv)

    if args.cmd == "encode":
        print(encode(args.url))
        return 0
    if args.cmd == "decode":
        out = decode(args.token)
        if out is None:
            print("invalid token", file=sys.stderr)
            return 1
        print(out)
        return 0
    if args.cmd == "v3":
        token = issue_v3(args.pk, os.environ.get("EKCELO_TOKEN_SECRET", ""),
                         args.kmz, args.html, args.name, args.exp)
        print(args.base + "?t=" + token)
        return 0
    if args.cmd == "url":
        print(build_short_url(args.url, args.base))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
