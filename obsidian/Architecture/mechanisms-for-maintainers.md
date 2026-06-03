# Механизмы системы — для программистов эксплуатации и ремонта

> Цель документа: дать поддерживающему программисту достаточно, чтобы **мысленно воспроизвести** работу frontend, backend и окружения от запуска до отказа, без чтения всего кода. Только современное состояние.

## 0. Карта процессов

```
┌─ Окружение ─────────────────────────────────────────────────────────┐
│  Python 3.11+ venv (.venv в корне клона)                             │
│  PYTHONPATH = repo_root (через serve.py или uvicorn --app-dir .)     │
└─────────────────────────────────────────────────────────────────────┘
        │                                   │
        ▼                                   ▼
┌─ Backend (FastAPI) ──────────┐    ┌─ Frontend (статика) ────────────┐
│ uvicorn backend.app.main:app │    │ python -m http.server (или      │
│  → lot_orchestrator_web.main │    │  GitHub Pages, или Live Server) │
│  → run_pipeline (LLM-оркестр)│    │ viewer/index.html (Leaflet+KMZ) │
│ :8000                        │    │ :8001/viewer/index.html         │
└──────────────────────────────┘    └─────────────────────────────────┘
        │                                   ▲
        ▼                                   │ fetch фикстуры / экспорта JSON
┌─ Данные ─────────────────────────────────┘
│ SQLite (ekcelo.sqlite): objects / rights / entity_registry /
│   object_etp_profile / lots / lot_items
│ Артефакты: out/etp/<lot>/*, <project>.kmz, Memorandum/*
└──────────────────────────────────────────────────────────────────────
```

## 1. Окружение

### 1.1 Почему нужен PYTHONPATH

Пакеты `backend`, `lot_orchestrator`, `lot_orchestrator_web`, `parser` лежат в корне репо и **не установлены** (`pip install -e .` доступен только после merge PR #92 — pyproject.toml). Поэтому они импортируются только если корень репо в `sys.path`.

| Способ запуска | `sys.path[0]` | `backend` найдётся? |
|---|---|---|
| `uvicorn backend.app.main:app` (console script) | `…/.venv/Scripts/` | ❌ нет |
| `python -m uvicorn backend.app.main:app` | cwd (`''`) | ✅ да |
| `uvicorn --app-dir . backend.app.main:app` | `.` добавлен явно | ✅ да |
| `python serve.py` | `serve.py` ставит `PYTHONPATH=repo_root` в env | ✅ да (переживает `--reload`) |

**Ключевой нюанс reload**: uvicorn `--reload` форкает reloader-подпроцесс. На Windows (spawn) подпроцесс реконструирует `sys.path` из `PYTHONPATH` env, а не из runtime-мутаций родителя. Поэтому `serve.py` выставляет именно **env-переменную** `PYTHONPATH`, а не только `sys.path.insert`. Реализация: `serve.py::_ensure_pythonpath`.

### 1.2 venv

`serve.py::_warn_if_foreign_venv` сравнивает `os.environ["VIRTUAL_ENV"]` с корнем репо. Если venv снаружи — печатает WARNING. Это ловит классическую ошибку «активирован venv соседнего проекта → ModuleNotFoundError».

### 1.3 Mental-reproduce окружения

1. `python serve.py` → `_ensure_pythonpath()` пишет `PYTHONPATH=E:\...\ftontback2026-01-02` → `_warn_if_foreign_venv()` молчит (venv внутри) → `import uvicorn` ок → `uvicorn.run("backend.app.main:app", reload=True, reload_dirs=[repo_root])`.
2. uvicorn форкает reloader [pid A] + server [pid B]. B наследует `PYTHONPATH` → `import backend.app.main` → re-export `lot_orchestrator_web.main:app`.
3. При правке файла WatchFiles перезапускает B; PYTHONPATH сохраняется → импорт снова успешен.

## 2. Backend (FastAPI)

### 2.1 Слои (template-aligned, см. backend-template-mapping.md)

```
backend/app/main.py        →  re-export lot_orchestrator_web.main:app
lot_orchestrator_web/      →  HTTP-слой: routes, store, runner, auth, persistence, redis_store
lot_orchestrator/          →  ядро: state_machine (4 фазы), schemas, llm_client, prompts, ...
parser/                    →  ETL (используется оркестратором косвенно через workspace/folder_match)
```

### 2.2 Жизненный цикл запроса (POST /lots/{id}/run)

1. `start_run` (main.py) валидирует `workspace_path` существует → 400 если нет.
2. `build_llm_client(settings, mock_text)` — если `mock_llm_text` в body или `--mock-llm` → `MockClient`; иначе требует `ANTHROPIC_API_KEY` → `AnthropicClient`; нет ключа → 400.
3. `store.create(lot_id, workspace)` → `Run(status="pending")`.
4. `BackgroundTasks.add_task(execute_run, ...)` → 202 `{run_id}`.
5. `execute_run` (runner.py) в потоке через `asyncio.to_thread(run_pipeline, ...)`.
6. `run_pipeline` (state_machine.py) гоняет 4 фазы: VALIDATING → CONTEXT_INJECTION → LLM_RUNNING → ROUTING. На каждой `store.update(run_id, phase=…)`.
7. Клиент опрашивает `GET /status/{run_id}` или стримит `GET /stream/{run_id}` (SSE).

### 2.3 State store (3 реализации, единый интерфейс)

| Store | Когда | Persistence | Multi-worker |
|---|---|---|---|
| `RunStore` (in-memory) | dev по умолчанию | нет | ❌ |
| `RunStore(persistence=SQLitePersistence)` | `--persistence-db` (PR #90) | SQLite snapshot | ❌ (один процесс) |
| `RedisRunStore` (PR #92) | `--redis-url` | Redis hash + опц. SQLite mirror | ✅ |

Выбор — в `create_app(...)`: `redis_client` → `configure_redis_store`; иначе `persistence_db` → `configure_store`. DI-точка `get_store()` отдаёт singleton.

### 2.4 SSE — две стратегии (PR #93 cycle 11)

`_sse_phase_changes` диспетчер:
- `hasattr(store, "subscribe_events")` (RedisRunStore) → `_sse_via_pubsub`: initial snapshot + Redis PUBSUB через `asyncio.to_thread(ps.get_message)`. Мгновенно.
- иначе → `_sse_via_polling`: tick 200ms, timeout 5 мин.

### 2.5 Auth (PR #93 cycle 12)

`maybe_install_basic_auth(app, raw_users_env)` — если `EKCELO_AUTH_USERS=u:p,...` задан, добавляет `BasicAuthMiddleware` (secrets.compare_digest, exempt: `/static /docs /openapi.json /redoc`). Не задан → no-op. На main (без #93) `backend/app/core/security.py::install_basic_auth` ловит ImportError → False.

### 2.6 LLM-клиент — opt-in, Protocol-based

`lot_orchestrator/llm_client.py`: Protocol `LLMClient` с `.send(system, user)`. `AnthropicClient` (lazy `import anthropic`, retry × N, exp-backoff) и `MockClient`. **API-ключ нужен только при реальном `AnthropicClient`.** Подмена провайдера = новый класс, реализующий Protocol.

### 2.7 Mental-reproduce backend-отказов

| Симптом | Причина | Где смотреть |
|---|---|---|
| `ModuleNotFoundError: backend` | нет repo_root в sys.path | §1.1, serve.py |
| 400 на /run «ANTHROPIC_API_KEY» | реальный LLM без ключа | build_llm_client; используйте mock_llm_text |
| 404 /artifacts | нет завершённых прогонов / нет Memorandum/ | get_artifacts → GLOB workspace |
| Runs пропали после рестарта | in-memory store | используйте --persistence-db |
| Разные /artifacts на разных workers | артефакты не на shared FS | разместить out/ на NFS |

## 3. Frontend (viewer)

### 3.1 Что это

Статический HTML5 (`viewer/index.html`, ≈12K строк) + Leaflet (карта) + JSZip (распаковка KMZ) + DOMParser (KML) + piexifjs/exifr (EXIF фото). CDN-зависимости (jsdelivr/unpkg/cloudflare): leaflet, jszip, piexif, exifr, xlsx-js-style. **Бэкенд не требуется** — viewer самодостаточен, работает с локальным KMZ.

### 3.2 Источники данных viewer

| Источник | Как загружается | Обязательность |
|---|---|---|
| KMZ-файл | UI «Загрузить KMZ» → JSZip → DOMParser(doc.kml) | основной |
| ЭТП-профиль фикстура | `loadEtpFixture()` — fetch `parser/tests/...` → fallback `../parser/tests/...` | опциональный (Phase 1) |
| Фото из KMZ | `images/` внутри ZIP | опц. |
| Граф связей | `graph.html` внутри KMZ | опц. |

### 3.3 Fixture path resolution (важно для эксплуатации)

`loadEtpFixture()` пробует по очереди:
1. `parser/tests/fixtures/etp/object_etp_profile_sample.json` (работает если viewer раздаётся из своей папки / GH Pages с фикстурой рядом).
2. `../parser/tests/fixtures/etp/object_etp_profile_sample.json` (работает при раздаче из корня репо: `/viewer/index.html` → `../parser/` = `/parser/`).

Все 404 — silent skip (опциональный слой). Поэтому `GET /viewer/parser/tests/...` → 404 в логе http.server **ожидаем и безвреден** — следом идёт успешный `../parser/...`.

### 3.4 Бейджи source/confidence

Карточка объекта для каждого `cad_number` ищет профиль в `_etpProfile.byKn`. Если найден — рисует блок «— ЕГРН —» + бейдж по `confidence`: ≥1.0 (osv/manual) зелёный; 0.5–0.99 (nspd/exif) жёлтый; <0.5 оранжевый приглушённый.

### 3.5 Service worker

`viewer/sw.js` — offline-кэш. В Incognito может не регистрироваться; для отладки — DevTools → Application → Service Workers → Unregister.

### 3.6 Mental-reproduce frontend

1. Браузер GET `/viewer/index.html` → грузит CDN (leaflet/jszip/…).
2. `loadEtpFixture()` async: try `parser/…` (404) → try `../parser/…` (200) → заполняет `_etpProfile.byKn`.
3. Пользователь «Загрузить KMZ» → JSZip распаковывает → DOMParser читает `doc.kml` → Leaflet рисует Placemark'и по `styleUrl` (cad_zu/oks/room/...).
4. Клик по объекту → карточка + (если есть в `_etpProfile`) ЭТП-блок с бейджем.

## 4. Тестовая инфраструктура

| Suite | Запуск | Что |
|---|---|---|
| backend re-export | `pytest backend/tests/test_layout_reexports.py` | 12 — assert template is direct |
| serve launcher | `pytest backend/tests/test_serve_launcher.py` | 10 — PYTHONPATH, foreign venv, argparse |
| orchestrator core | `pytest lot_orchestrator/tests/` | schemas, state_machine, temporal, workspace, llm_client |
| orchestrator web | `pytest lot_orchestrator_web/tests/` | routes, persistence, redis(fakeredis), auth, sse, cli |
| ETP exporter | `pytest parser/tests/test_smoke_cli.py test_etl_checko.py` | smoke 33 + checko |

Совокупно после merge всех PR: **109+ pass, coverage 95%**.

## 5. Связи

- `system-state-2026-05-30.md` — снимок всех модулей.
- `backend-template-mapping.md` — layout backend/ ↔ fastapi-template.
- `lot-orchestrator.md` — детали 4-фазного pipeline.
- `frontend-smoke-2026-05-30.md` — результаты ручного smoke.
- Пользовательский аналог: `obsidian/UserGuide/data-flows.md`.
