# 2026-06-03 — Cycle 13: PBKDF2-хеширование паролей Basic Auth

## Итог
Возобновление цикла развития после остановки cycles 13-15. Cycle 13 закрыт: пароли в `EKCELO_AUTH_USERS` теперь хранятся как `pbkdf2_sha256$<iter>$<salt>$<hash>` (stdlib-only). Backward-compat с plaintext (cycle 12) сохранён через UserWarning. Зависимостей не добавилось.

Параллельно: одним commit'ом подняты в main застрявшие cycles 8-12 (#90/#92/#93 базировались друг на друге, до main не доехали) — merge `orchestrator/cycle-11-12-httpx2-migration` в `chore/integrate-cycles-8-12`. Конфликт только в одной таблице `obsidian/Architecture/lot-orchestrator.md` (статусы циклов) — разрешён в пользу более новой версии с дополнением cycle 13.

## Артефакты

| Файл | LOC | Назначение |
|---|---|---|
| `lot_orchestrator_web/password.py` | 95 | hash_password / verify_password / is_hashed + CLI генерации |
| `lot_orchestrator_web/auth.py` | +18 | вызов `verify_password` вместо `secrets.compare_digest`; warning о plaintext; `_Creds.plaintext_users()` для аудита |
| `lot_orchestrator_web/tests/test_password.py` | 15 тестов | формат, salt-uniqueness, безопасность для `:`/`,`, custom iterations, CLI |
| `lot_orchestrator_web/tests/test_auth_hashing.py` | 9 тестов | login с хешем, plaintext+hash coexistence, защита от передачи хеша как пароля |

## Формат хеша

```
pbkdf2_sha256$600000$<salt_hex_32>$<digest_hex_64>
```

- **Scheme:** pbkdf2_sha256 (HMAC-SHA256).
- **Iterations:** 600 000 (OWASP-2023 recommendation для PBKDF2-HMAC-SHA256).
- **Salt:** 16 случайных байт (`secrets.token_bytes`), уникальный на каждый хеш.
- **Digest:** 32 байта SHA-256.

Формат гарантированно не содержит `:` и `,` — безопасно встраивается в env-переменную с этими разделителями.

## CLI

```bash
# Интерактивно (без эха):
python -m lot_orchestrator_web.password --user alice
# Password: ********
# alice:pbkdf2_sha256$600000$...

# Скриптовый режим:
python -m lot_orchestrator_web.password --user bob mySecret123

# Только хеш без user-префикса:
python -m lot_orchestrator_web.password mySecret123

# Кастомные итерации:
python -m lot_orchestrator_web.password --iterations 700000 mySecret123
```

## Backward compatibility

`verify_password(plain, stored)` распознаёт формат:
- Начинается с `pbkdf2_sha256$` → парсит как хеш, делает `pbkdf2_hmac` и сверяет `secrets.compare_digest`.
- Иначе → трактует как plaintext (cycle 12 поведение), сравнивает напрямую через `secrets.compare_digest`.

При загрузке `EKCELO_AUTH_USERS` метод `_Creds._warn_plaintext()` эмитит `UserWarning` для каждого пользователя в plaintext — миграционный путь не блокирует существующие deployments, но напоминает.

## Тесты (24/24 pass, suite 174/174)

- **password.py (15):** формат, salt unique, `:`/`,`-safe, custom iterations, roundtrip параметризованный (5 разных паролей), is_hashed для pbkdf2/plaintext, malformed hash → False, wrong scheme → False, CLI prints hash / `user:hash` / errors on empty / custom iterations.
- **auth_hashing.py (9):** detect plaintext, no detect для всех-хешированных, warning emitted, no warning for hashed, login hashed user, hashed+plaintext coexist, передача хеша как пароля → 401.

Регрессия: все 12 cycle-12 auth-тестов проходят без изменений (verify_password backward-compat работает).

## Mental-reproduce безопасности

1. Атака на slow-equality (timing): `verify_password` использует `secrets.compare_digest` на digest'ах одинаковой длины → constant-time.
2. Атака на rainbow tables: уникальная случайная соль на каждый хеш → нельзя предвычислить.
3. Атака на brute-force: 600k итераций PBKDF2 → ~100ms на проверку, неприемлемо для GPU-attack offline.
4. Атака «передам хеш как пароль»: `verify_password(plain=hash, stored=hash)` — `pbkdf2_hmac(hash)` ≠ `digest_from_stored`, проверка вернёт False (test_hash_not_accidentally_matched_as_password подтверждает).
5. Атака на env-leak: хеш в env-логах безопаснее plaintext'а, но всё равно ограничивайте кто читает `EKCELO_AUTH_USERS`.

## Не сделано в этом cycle

- **Rate limiting** на 401-ответы (для защиты от credential-stuffing) — нужна отдельная цикл с in-memory или Redis-counter.
- **Удаление plaintext-режима** — оставлено для backward-compat. Кандидат на удаление в cycle 14+, когда все деплои мигрируют.
- **OAuth2 / OIDC** — cycle 14.
- **Per-lot RBAC** — cycle 15.

## Связи

- backend: `lot_orchestrator_web/auth.py` (cycle 12) + `password.py` (cycle 13).
- архитектура: `obsidian/Architecture/lot-orchestrator.md` раздел «Auth cycle 13».
- инструкция: `obsidian/UserGuide/orchestrator-web.md` раздел «HTTP Basic Auth».
- ADR: пока не вынесено; решение «pbkdf2 stdlib вместо bcrypt/argon2» зафиксировано в docstring `password.py`.
