# Cycle 16 — Rate limiting на auth-провалы

> Hardening против online credential-stuffing. После N неудачных auth-попыток
> по ключу (IP+username для Basic / IP для Bearer) — блок на T секунд с
> `429 Too Many Requests` + `Retry-After`.

## Зачем

Cycle 13 защитил от offline-brute-force через PBKDF2 600k iterations.
Cycle 16 закрывает online: даже с медленным хешем миллион попыток в минуту
перегружает CPU и даёт шанс на угадывание. Rate limit срезает атаку на
ранней стадии.

## Архитектура

```
┌─ Конфиг (env) ────────────────────────────────────────┐
│ EKCELO_RATELIMIT_ENABLED   default true                │
│ EKCELO_RATELIMIT_FAILS     default 5                   │
│ EKCELO_RATELIMIT_WINDOW_S  default 300 (5 мин)         │
│ EKCELO_RATELIMIT_BLOCK_S   default 900 (15 мин)        │
└────────┬──────────────────────────────────────────────┘
         ▼
┌─ RateLimiter (in-memory) ─────────────────────────────┐
│ is_blocked(key) → (bool, retry_after_s)                │
│ record_failure(key) → (blocked, retry_after_s)         │
│ reset(key)  # success                                  │
│ thread-safe, monotonic clock                           │
└────────┬──────────────────────────────────────────────┘
         │ кладётся в app.state.rate_limiter
         ▼
┌─ Auth middleware integration ─────────────────────────┐
│ BasicAuthMiddleware:                                   │
│   key = f"basic:{ip}:{attempted_username}"             │
│   401 → record_failure; 200 → reset                    │
│ OAuthMiddleware:                                       │
│   key = f"bearer:{ip}"                                 │
│   401 → record_failure; 200 → reset                    │
│                                                        │
│ Перед verify: is_blocked → 429 + Retry-After           │
└───────────────────────────────────────────────────────┘
```

## Поведение

### Окно подсчёта
Первый провал — start of window. Все провалы за `window_s` секунд считаются
в этот счётчик. После `window_s` истечения — новое окно (счётчик сбрасывается).

### Блок
По достижении `fails_limit` провалов в окне — устанавливается блок до
`now + block_s`. В этот период все запросы (даже с правильными
credentials) → 429.

### Сброс
Успешная аутентификация сбрасывает счётчик для ключа полностью. Это
важно: легитимный пользователь после случайной опечатки не накапливает
fails.

### Ключи rate-limit

**Basic Auth:** `basic:{ip}:{attempted_username}` — позволяет:
- разделять buckets разных пользователей с одного IP (alice провалилась
  → bob с того же IP ещё может);
- ловить распределённый перебор одного пользователя (если username
  фиксирован, IP меняется — каждый IP сам по себе).

**Bearer OAuth:** `bearer:{ip}` (только IP). Sub из токена недоступен
до verify; использовать unverified_claims небезопасно для счётчика.

### Disabled mode
`EKCELO_RATELIMIT_ENABLED=false` — limiter становится no-op для всех методов.
Удобно для интеграционных тестов и отладки.

### Backward-compat
Если `app.state.rate_limiter` не установлен — middleware работают как
раньше (без 429). Используется в legacy-тестах.

## Файлы и тесты

| Файл | Назначение |
|---|---|
| `lot_orchestrator_web/ratelimit.py` | RateLimitConfig + RateLimiter (in-memory) |
| `lot_orchestrator_web/auth.py` | BasicAuthMiddleware: ключ basic:{ip}:{user} |
| `lot_orchestrator_web/oauth.py` | OAuthMiddleware: ключ bearer:{ip} |
| `lot_orchestrator_web/main.py` | create_app: `app.state.rate_limiter` |
| `lot_orchestrator_web/tests/test_ratelimit.py` | 13 тестов core |
| `lot_orchestrator_web/tests/test_ratelimit_middleware.py` | 9 тестов integration |

**Тесты cycle 16:** 22 (13 + 9). Полный suite в sandbox: **480 passed,
1 skipped** (458 + 22). 0 регрессий.

Покрытие:
- core: defaults from env, disabled, fails-below-limit, hit-limit-blocks,
  block-expires, window-resets-counter, reset-clears, key-isolation,
  return-values.
- Basic middleware: increment, 429 + Retry-After, success resets,
  expire window, different users isolated, no-limiter no-op.
- Bearer middleware: invalid token, missing token, valid token resets.

## Конфиг для production

```bash
# .env / docker-compose:
EKCELO_RATELIMIT_ENABLED=true
EKCELO_RATELIMIT_FAILS=5
EKCELO_RATELIMIT_WINDOW_S=300
EKCELO_RATELIMIT_BLOCK_S=900
```

Для тестового стенда (более мягкие лимиты):
```bash
EKCELO_RATELIMIT_FAILS=10
EKCELO_RATELIMIT_WINDOW_S=60
EKCELO_RATELIMIT_BLOCK_S=120
```

## Что НЕ в cycle 16

- **Redis backend** (multi-worker shared state). Архитектурно подготовлено:
  RateLimiter принимает callable clock и любой storage. Реализация Redis-
  backed класса — отдельный sub-stage при реальном multi-worker деплое.
- **Distributed rate limiting** за пределами одного Redis — это reverse-
  proxy / CDN (Cloudflare, nginx limit_req).
- **WAF / DDoS** — тоже периметровый слой.

## Связи

- Roadmap: `obsidian/Architecture/roadmap-2026-06.md` §Cycle 16.
- Предшественники: `cycle-14-oauth.md`, `cycle-15-rbac.md`,
  `password.py` (cycle 13 PBKDF2 600k).
- Не привязан к C-контракту (внутренний hardening).
