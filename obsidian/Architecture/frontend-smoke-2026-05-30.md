# Frontend smoke-отчёт — 2026-05-30

> Текущее состояние: viewer/ + lot_orchestrator_web/ Jinja templates. Результаты ручного smoke.

## Что протестировано

### viewer/ — статические HTML

Запуск:

```bash
cd /home/user/ekcelo
python -m http.server 8001 --bind 127.0.0.1
```

Все 4 ключевых ресурса отдаются с HTTP 200:

| Ресурс | Размер (LOC) | Статус |
|---|---|---|
| `viewer/index.html` | 12006 | 200 OK |
| `viewer/admin-etp-profile.html` | 508 | 200 OK |
| `viewer/tokens.js` | small | 200 OK |
| `viewer/sw.js` | small | 200 OK |

Локальные ссылки в `viewer/index.html`:
- `./v2961.html` — вспомогательный UI (доступен).
- `images/${safeName}`, `images/...` — шаблонные `src` для динамической вставки фото из KMZ (не отдаются как статика).
- Внешние ссылки на `nspd.gov.ru`, `pkk.rosreestr.ru` — динамические URL для перехода (не загружаются smoke-ом).

**ЭТП-фикстура — multi-path fallback (2026-06-03):** `loadEtpFixture()` пробует `parser/tests/fixtures/etp/object_etp_profile_sample.json`, затем `../parser/tests/...`. При раздаче из корня репо первый путь даёт 404 (`/viewer/parser/...`), второй — 200 (`/parser/...`). 404 в логе http.server ожидаем и безвреден (опциональный слой; см. `obsidian/UserGuide/data-flows.md` устье A).

**Вывод:** виьюер технически работоспособен (HTML/JS/CSS грузятся без 404), KMZ-загрузчик активируется через UI «Загрузить KMZ». Глубокий e2e — открыть в браузере, загрузить реальный KMZ, проверить рендер.

### lot_orchestrator_web/ — FastAPI + Jinja

Запуск:

```bash
uvicorn lot_orchestrator_web.main:app --port 8765
```

Endpoints (cycle 5 state, до merge #90/#92/#93):

| Endpoint | Метод | Статус |
|---|---|---|
| `/` | GET | 200, 1001 байт HTML (`<h1>Ekcelo Orchestrator</h1>`) |
| `/openapi.json` | GET | 200, 6 paths |
| `/docs` | GET | 200 (Swagger UI) |
| `/redoc` | GET | 200 (ReDoc) |
| `/lots/{lot_id}/run` | POST | 400 при отсутствии `workspace_path` (ожидаемо) |
| `/lots/{lot_id}/needs-input` | GET | 200 (Jinja-форма) |
| `/lots/{lot_id}/status/{run_id}` | GET | 404 при unknown run (ожидаемо) |
| `/lots/{lot_id}/artifacts` | GET | 404 при отсутствии завершённых прогонов (ожидаемо) |

`POST /lots/{lot_id}/provide-input` — принимает form-data; smoke не проверял (требует подготовки workspace).

**Title:** `Ekcelo Orchestrator` · **Version:** `0.1.0` (на main; после merge PR #92 — `0.3.0`, после #93 — `0.4.0`).

## Тестовое покрытие (текущее main)

```
$ python -m pytest lot_orchestrator{,_web}/tests/ parser/tests/test_etl_checko.py parser/tests/test_smoke_cli.py
======================== 56 passed in 0.5s =======================
```

После merge #90/#92/#93 — 109/109 pass, coverage 95% (см. [[lot-orchestrator]] раздел тесты).

## Smoke CLI ЭТП-экспортёра

```bash
$ python -m parser.exporters.etp.smoke_cli
[OK ] import parser.exporters.etp
[OK ] import parser.exporters.etp.address_parser
... 33 проверки ...
smoke: 33/33 passed
```

rc=0, все 33 чек-поинта зелёные (включая `etl_checko` после фикса `_REQUIRED_MODULES`).

## Что НЕ протестировано (требует ручной проверки)

1. **KMZ загрузка в viewer/index.html** — нужно открыть в Chrome/Edge, загрузить реальный `.kmz`, проверить:
   - Leaflet рендер маркеров.
   - Карточка объекта (бейджи source/confidence для ЭТП-профиля).
   - Граф связей (`graph.html` в KMZ).
2. **`admin-etp-profile.html`** — редактор YAML-патчей для `object_etp_profile`. Smoke не проверял генерацию YAML.
3. **`tokens.js` / `token-gate.html`** — auth-gate для приватных deploy'ев viewer'а.
4. **Service Worker (`sw.js`)** — offline-кэш, поведение в Incognito-режиме.

## Известные ограничения / непокрытые сценарии

| Что | Где описано |
|---|---|
| Multi-extract timeline UI (timeline.json) | post 019/022, Phase 1 B2 активна, Phase 2 ждёт production-кейсов |
| EXIF v1.2 per-photo `note` в admin UI | post 027/028 (self-resolved) — реализация откладывается до cycle EXIF-v1.2-impl |
| Render лотов на карте (Phase 2 viewer) | post 025/026 — отложено до подтверждённого спроса |
| OAuth/JWT/multi-user RBAC | cycle 12 даёт только Basic Auth; cycles 13-15 явно отложены пользователем |

## Следующие шаги для пользователя

1. **Перед production:** запустить полный e2e «golden-path» (см. [[golden-path]]) на реальном лоте.
2. После merge PR #90/#92/#93 — перегнать smoke с `ekcelo-etp-smoke` + `ekcelo-orchestrate-web --reload` (новые console scripts).
3. Если найдены регрессии в viewer/ — задокументировать в отдельном файле `obsidian/Architecture/viewer-issues-YYYY-MM-DD.md`.
