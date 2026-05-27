#!/usr/bin/env python3
"""Ekcelo token-system v1 — stateless self-contained URL shortener.

Алгоритм:
    encode: url -> base64url(UTF-8(url)) без padding
    decode: token -> url (после восстановления padding и проверки схемы)

Никакого реестра, состояния, шифрования.
"""

from __future__ import annotations

import argparse
import base64
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
    if args.cmd == "url":
        print(build_short_url(args.url, args.base))
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
