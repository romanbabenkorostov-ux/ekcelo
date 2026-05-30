# 2026-05-30 — Cycles 11 + 12 + httpx2 migration

## Итог
Три смежных улучшения в одном PR:

- **Cycle 11** — SSE через Redis pub/sub (instant phase updates вместо polling 200ms). Polling остаётся как fallback при in-memory store.
- **Cycle 12** — Опциональная HTTP Basic Auth middleware. Env `EKCELO_AUTH_USERS=user:pass,...` или CLI `--auth-users`.
- **httpx2 migration** — заменили `httpx>=0.27` на `httpx2>=2.0` в `[orchestrator-web]` extras. Starlette deprecation warning ушёл.

**95% покрытие удержано.** 109/109 тестов pass за 2.35s (89 + 20 новых).

## Артефакты

### Cycle 11 (SSE pub/sub)

- `lot_orchestrator_web/main.py` — `_sse_phase_changes` теперь гибрид: если у store есть `subscribe_events` (RedisRunStore) → pub/sub, иначе polling.
- `lot_orchestrator_web/main.py::_sse_via_pubsub` — асинхронный generator, читает Redis pubsub через `asyncio.to_thread`, эмитит initial snapshot первым (клиент видит phase сразу).
- `lot_orchestrator_web/tests/test_sse_pubsub.py` — 4 теста (pubsub happy path, error для unknown run, polling fallback, phase changes after initial).

### Cycle 12 (Basic Auth)

- `lot_orchestrator_web/auth.py` (NEW, ~90 LOC) — `BasicAuthMiddleware` + `_Creds.from_env` + `maybe_install_basic_auth`. `secrets.compare_digest` для защиты от timing attacks.
- `lot_orchestrator_web/main.py` — `create_app(auth_users=...)` kwarg; middleware устанавливается последним (оборачивает все routes).
- `lot_orchestrator_web/cli.py` — `--auth-users` flag, читает из env `AUTH_USERS`.
- Exempt-пути: `/static/*`, `/docs`, `/openapi.json`, `/redoc` — открыты для документации.
- `lot_orchestrator_web/tests/test_auth.py` — 12 тестов (Creds parser × 5, install logic × 7).

### httpx2 migration

- `pyproject.toml` — `httpx>=0.27` → `httpx2>=2.0` в `[orchestrator-web]`.
- Никаких импортов в коде не изменилось (httpx использовался только транзитивно через starlette.testclient).
- Starlette автоматически выбирает httpx2 → deprecation warning исчез.

## Тесты (109/109 pass at 2.35s, 95% coverage)

```
======================== 109 passed in 2.35s ===========================
TOTAL                                                 2210    118    95%
```

Распределение нового покрытия:
- `lot_orchestrator_web/auth.py`: 100%
- `lot_orchestrator_web/main.py`: 92% (включая новый _sse_via_pubsub branch)
- `lot_orchestrator_web/tests/test_sse_pubsub.py`: 100%
- `lot_orchestrator_web/tests/test_auth.py`: 100%

## Mental run trace (production multi-worker с auth + SSE pub/sub)

1. `ekcelo-orchestrate-web --redis-url ... --persistence-db ... --auth-users "alice:s" --workers 4`
2. CLI выставляет env `EKCELO_AUTH_USERS=alice:s` → `_build_app_from_env` подхватывает.
3. `create_app(auth_users="alice:s")` → `maybe_install_basic_auth` → BasicAuthMiddleware.
4. uvicorn форкает 4 worker'а, каждый импортирует app → одинаковая auth конфигурация.
5. Client делает GET `/lots/X/run` БЕЗ заголовка → middleware → 401 + WWW-Authenticate.
6. Браузер показывает диалог → пользователь вводит alice:s → повторный запрос → 202.
7. Client делает GET `/lots/X/stream/<run_id>` → middleware пропускает (auth есть) → `_sse_phase_changes`.
8. Store = RedisRunStore (cycle 9) → `hasattr(store, "subscribe_events")` → True → ветка pub/sub.
9. `_sse_via_pubsub` эмитит initial snapshot из Redis hash → ps.subscribe(events_<run_id>).
10. В другом worker'е после очередной фазы: `store.update(...)` → `_publish(run)` → Redis PUBLISH events_<run_id> {"phase": "..."}.
11. Текущий worker через `asyncio.to_thread(ps.get_message, timeout=0.05)` получает событие → emit `event: phase`.
12. status="complete" → emit `event: done` → return → SSE-стрим закрывается, ps закрывается в finally.

## API изменения

| API | Cycle | Действие |
|---|---|---|
| `create_app(auth_users=...)` | 12 | новый kwarg |
| `EKCELO_AUTH_USERS` env | 12 | подхватывается через `_build_app_from_env` (косвенно через cli.py → `AUTH_USERS` → `EKCELO_AUTH_USERS`) |
| `ekcelo-orchestrate-web --auth-users` | 12 | новый CLI flag |
| `GET /stream/{run_id}` поведение | 11 | + initial snapshot первым event'ом; pubsub вместо polling если RedisRunStore |

## Дальше (не сделано в этом PR)

- **cycle 13** — Hashed passwords (bcrypt/argon2) вместо plain в env.
- **cycle 14** — OAuth2 / OIDC support (вместо или в дополнение к Basic).
- **cycle 15** — Per-lot RBAC (alice видит только свои лоты).

Триггер для cycle 13+: реальная production-инсталляция > 2 пользователей или compliance требования.
