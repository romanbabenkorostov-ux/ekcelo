# 2026-06-21 — Cycle 16 rate limiting + investor overview

## Что сделал

1. **Cycle 16 — rate limiting на auth-провалы.** Hardening против online
   credential-stuffing. После N провалов в окне → 429 + Retry-After. Закрывает
   auth-трек (13-14-15-16 ✅).
2. **Investor overview** — отдельный markdown в `obsidian/Investor/` для
   презентации инвестору (что делаем, что сделано, что предстоит, golden
   path демонстрации).

## Файлы (cycle 16)
- ✨ `lot_orchestrator_web/ratelimit.py` — `RateLimitConfig`, `RateLimiter`
  (in-memory, thread-safe, monotonic clock).
- ✏️ `lot_orchestrator_web/auth.py` — BasicAuthMiddleware integration
  (ключ `basic:{ip}:{attempted_user}`).
- ✏️ `lot_orchestrator_web/oauth.py` — OAuthMiddleware integration
  (ключ `bearer:{ip}`).
- ✏️ `lot_orchestrator_web/main.py` — `app.state.rate_limiter`
  из `RateLimitConfig.from_env()`.
- ✨ `lot_orchestrator_web/tests/test_ratelimit.py` — 13 core-тестов.
- ✨ `lot_orchestrator_web/tests/test_ratelimit_middleware.py` — 9
  integration-тестов (Basic + Bearer).
- ✨ `obsidian/Architecture/cycle-16-ratelimit.md` — снимок.

## Файлы (investor)
- ✨ `obsidian/Investor/overview-2026-06.md` — investor overview документ.

## Файлы (docs)
- ✏️ `obsidian/Architecture/roadmap-2026-06.md` — cycle 16 ✅.
- ✏️ `obsidian/CHECKPOINT.md` — live.
- ✏️ `docs/specs/SPEC_backend.md` — актуализирован.

## Тесты
- 22 новых cycle 16 (13 + 9).
- Полный suite в sandbox: **480 passed, 1 skipped** (458 + 22).
- 0 регрессий: все cycle 14/15 + Bundle + RBAC + auth — без изменений.

## Решения

- **In-memory backend default, Redis оставлен крючком.** Single-worker
  uvicorn — основной деплой. Multi-worker (gunicorn workers > 1) потребует
  Redis-backed RateLimiter — реализуется отдельным sub-stage когда
  понадобится.
- **Thread-safe через `threading.Lock`.** FastAPI single-event-loop, но
  middleware могут вызываться из разных threads если приложение под
  gunicorn с threading workers. Lock дешёвый, страховка стоит.
- **Monotonic clock, не wallclock.** NTP-skip не должен влиять на блок-
  таймер. Тесты подмешивают clock callable.
- **Ключ Basic = `basic:{ip}:{attempted_user}`.** Изоляция buckets:
  - alice провалилась с IP 1.2.3.4 → bob с того же IP свой счётчик
  - распределённый перебор alice с разных IP → каждый IP свой счётчик
  - не идеально (атакер с ботнетом ускользает), но IP-only хуже.
- **Ключ Bearer = `bearer:{ip}`.** Sub из токена недоступен до verify;
  unverified_claims.sub небезопасно. IP — единственный надёжный сигнал.
- **No-limiter mode (`app.state.rate_limiter is None`).** Существующие
  unit-тесты middleware (без create_app) работают как раньше — limiter
  опционален.
- **disabled-config — no-op для всех методов.** `EKCELO_RATELIMIT_ENABLED=false`
  не отключает middleware (всё ещё проверяет verify), но не записывает
  fails и не блокирует. Полезно для интеграционных тестов.
- **Counter reset on success.** Легитимный пользователь после случайной
  опечатки не накапливает счётчик. Атакер с угаданным паролем хотя бы
  получит rate-limit reset, но это уже не важно — он внутри.

## Закрытие auth-трека

После cycle 16 в `main`:
- ✅ Cycle 12 — Basic Auth.
- ✅ Cycle 13 — PBKDF2 600k password hashing.
- ✅ Cycle 14 M1 — OAuth/OIDC Bearer (#114).
- ✅ Cycle 15 M1-M4 — полный RBAC C6 (#115/#116/#117/#118).
- ✅ **Cycle 16 — rate limiting на auth-провалы.**

Auth-стек завершён в части серверной защиты. Cycle 14 M2 (browser
`/auth/login`) — нужен когда `ekcelo-site` начнёт реальный login UI.

## Канал доставки
- Sandbox-proxy блокирует push — zip-handoff (после merge #118).
- Investor overview включён в архив + поставляется отдельным артефактом
  (`SendUserFile`).

## Следующий шаг
1. Применить архив, открыть PR.
2. После merge:
   - **C3.3 geo materialization** (когда parser-team даст KMZ→DB).
   - **Production deploy на timeweb** (SQLite → PostgreSQL + S3).
   - **`ekcelo-site` frontend** — отдельный репозиторий (потребляет ViewModel REST).
