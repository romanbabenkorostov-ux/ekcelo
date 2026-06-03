"""Password hashing для Basic Auth (cycle 13).

Stdlib-only (hashlib.pbkdf2_hmac) — никаких новых зависимостей. Хранимый
формат совместим с `EKCELO_AUTH_USERS` (не содержит `:` и `,`):

    pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>

`verify_password` принимает И хешированные, И plaintext-значения (обратная
совместимость с cycle 12). Plaintext помечается как deprecated — для
production используйте хеши, сгенерированные `python -m lot_orchestrator_web.password`.

Почему pbkdf2, а не bcrypt/argon2:
- Чистый stdlib, без C-расширений (важно для лёгкой установки на Win10).
- Достаточно для внутреннего инструмента с парой операторов.
- Для multi-tenant / внешнего доступа — всё равно рекомендуется SSO за
  reverse-proxy (см. auth.py docstring).
"""
from __future__ import annotations

import hashlib
import secrets

_SCHEME = "pbkdf2_sha256"
# OWASP 2023 для PBKDF2-HMAC-SHA256: ≥ 600 000 итераций.
_DEFAULT_ITERATIONS = 600_000
_SALT_BYTES = 16


def hash_password(plain: str, *, iterations: int = _DEFAULT_ITERATIONS) -> str:
    """plain → `pbkdf2_sha256$<iters>$<salt_hex>$<hash_hex>`."""
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt, iterations)
    return f"{_SCHEME}${iterations}${salt.hex()}${digest.hex()}"


def is_hashed(stored: str) -> bool:
    """True если значение похоже на наш pbkdf2-формат."""
    return stored.startswith(f"{_SCHEME}$")


def verify_password(plain: str, stored: str) -> bool:
    """Constant-time проверка. Поддерживает хеш ИЛИ plaintext (backward compat)."""
    if is_hashed(stored):
        return _verify_pbkdf2(plain, stored)
    # Plaintext fallback (cycle 12) — deprecated, но не ломаем существующие конфиги.
    return secrets.compare_digest(plain, stored)


def _verify_pbkdf2(plain: str, stored: str) -> bool:
    try:
        scheme, iter_s, salt_hex, hash_hex = stored.split("$")
        if scheme != _SCHEME:
            return False
        iterations = int(iter_s)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(hash_hex)
    except (ValueError, TypeError):
        return False
    digest = hashlib.pbkdf2_hmac("sha256", plain.encode("utf-8"), salt, iterations)
    return secrets.compare_digest(digest, expected)


# ─────────────────────────────────────────────────────────────────────────────
#  CLI: генерация хеша для вставки в EKCELO_AUTH_USERS
# ─────────────────────────────────────────────────────────────────────────────

_EPILOG = """\
Зачем это нужно
---------------
Хеш вставляется в переменную EKCELO_AUTH_USERS, которой защищается web-сервер
оркестратора (ekcelo-orchestrate-web / serve.py). Пользователь при входе вводит
ПЛЕЙН-пароль в браузерный диалог, сервер сверяет его с хешем. Сам plain-пароль
нигде не хранится.

Полный сценарий
---------------
  1) Сгенерировать запись (ввод пароля скрыт):
       python -m lot_orchestrator_web.password --user alice
  2) Скопировать вывод вида  alice:pbkdf2_sha256$600000$...  в env:
       # PowerShell
       $env:EKCELO_AUTH_USERS = "alice:pbkdf2_sha256$600000$...,bob:pbkdf2_sha256$..."
       # bash
       export EKCELO_AUTH_USERS='alice:pbkdf2_sha256$600000$...'
     или передать флагом:
       ekcelo-orchestrate-web --auth-users "alice:pbkdf2_sha256$600000$..."
  3) Открыть http://localhost:8000/ — браузер спросит логин/пароль; ввести
     alice + ПЛЕЙН-пароль (НЕ хеш).

Если auth не нужен — просто не задавайте EKCELO_AUTH_USERS / --auth-users.
"""


def main(argv: list[str] | None = None) -> int:
    import argparse
    import getpass
    import sys

    p = argparse.ArgumentParser(
        prog="python -m lot_orchestrator_web.password",
        description="Сгенерировать pbkdf2-хеш пароля для EKCELO_AUTH_USERS.",
        epilog=_EPILOG,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument("password", nargs="?",
                   help="Пароль. Если не задан — спросит интерактивно (без эха).")
    p.add_argument("--user", help="Если задан — печатает готовую запись `user:<hash>`.")
    p.add_argument("--iterations", type=int, default=_DEFAULT_ITERATIONS,
                   help=f"Кол-во итераций PBKDF2 (default: {_DEFAULT_ITERATIONS}).")
    p.add_argument("--quiet", action="store_true",
                   help="Не печатать подсказку по применению (только хеш в stdout).")
    args = p.parse_args(argv)

    if args.password is not None:
        plain = args.password
    else:
        prompt = (f"Введите пароль для '{args.user}'" if args.user else "Введите пароль")
        plain = getpass.getpass(f"{prompt} (ввод скрыт, затем Enter): ")
    if not plain:
        print("error: пустой пароль", file=sys.stderr)
        return 2

    token = hash_password(plain, iterations=args.iterations)
    entry = f"{args.user}:{token}" if args.user else token
    # Хеш/запись — в stdout (можно пайпить). Подсказка — в stderr (не мешает пайпу).
    print(entry)
    if not args.quiet:
        _print_usage_hint(entry, args.user, sys.stderr)
    return 0


def _print_usage_hint(entry: str, user: str | None, stream) -> None:
    name = user or "alice"
    print(
        "\n--- что дальше -------------------------------------------------\n"
        "1) Скопируйте строку выше в переменную окружения EKCELO_AUTH_USERS\n"
        "   (или передайте флагом --auth-users), например:\n"
        f"     ekcelo-orchestrate-web --auth-users \"{entry}\"\n"
        "2) Откройте http://localhost:8000/ и войдите как "
        f"'{name}' + ваш ПЛЕЙН-пароль (НЕ хеш).\n"
        "Подробности: obsidian/UserGuide/orchestrator-web.md (раздел Basic Auth).\n"
        "----------------------------------------------------------------",
        file=stream,
    )


if __name__ == "__main__":
    import sys
    sys.exit(main())
