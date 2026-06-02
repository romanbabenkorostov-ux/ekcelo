# Снимок состояния системы — 2026-05-30

> Только современное состояние (не diff'ы). Чтобы понять, что было раньше, см. `obsidian/Changelog/`.

## Top-level layout репозитория

```
/
├── parser/                    # Python ETL (egrn_parser + exporters/etp + utils + scripts + tests)
├── lot_orchestrator/          # CLI MVP меморандум-пайплайна (12 модулей + tests)
├── lot_orchestrator_web/      # FastAPI обёртка (cycle 5 в main; cycles 8-12 в открытых PR)
├── viewer/                    # HTML5 + Leaflet карточки (index.html, admin-etp-profile.html, sw.js, tokens.js)
├── obsidian/                  # Knowledge base — Architecture / Decisions / Changelog / UserGuide / Prompts
├── docs/                      # CORRESPONDENCE + spec'и формата (CONTRACT_KMZ, GOLDEN_PATH_economist_v3.md)
├── schema/                    # SQLite DDL + migrations (0001 ЭТП-слой)
└── *.bat, install.bat        # Win10 launchers
```

## parser/

| Под-пакет | Назначение |
|---|---|
| `parser/egrn_parser/` | Каноническая v1.10 парсера: PDF/XML/ОСВ/DOCX → SQLite + XLSX + JSON + graph.json v1.1. CLI: `egrn-parser parse / folders / migrate / dict-load`. |
| `parser/exporters/etp/` | ЭТП-экспортёр Stage 1-6 + smoke. 22 модуля. Канонические CLI: `init_db_cli`, `etl_osv_cli`, `etl_pipeline_cli` (bulk), `nspd_enrich_cli`, `etl_exif_cli`, `etl_checko`, `cli` (Stage 3 → карточки), `export_json_cli`, `smoke_cli` (33 чек-поинта). |
| `parser/utils/` | `folder_match.py` (best_match с layout-swap ЙЦУКЕН↔QWERTY), `personal_data_filter.py`, EXIF utils. |
| `parser/scripts/` | Скрипты-пайплайн pirushin_sosn_rocha_*: 01 OS parse → 02 cad folders → 03 merge → 04 sanity → 052 structure → 06 photos → 07 init project v3 → 08 build KMZ v2.2 → 09 reports → 10-13 contract assembly. |
| `parser/inbox/etp/` | Inbox YAML survey-листов экономиста; bulk-pipeline переносит applied → `_applied/<YYYY-MM-DD>/`. |
| `parser/tests/` | pytest для ETL, smoke, KMZ-сборки, schema, NSPD, etl_checko. |

## lot_orchestrator/ (CLI MVP, cycle 4 — в main)

12 модулей:

- `__init__.py` (re-exports), `config.py` (Settings.from_env), `schemas.py` (Pydantic v2 AssetData/TargetScenario/DocumentDate/Fact/Provenance/Conflict/EgrnLayer/EtpProfile), `workspace.py` (init_workspace с canonical `parser.utils.folder_match.best_match`).
- `inputs_finder.py` (canonical → recursive fallback, skip service-dirs, mtime ordering).
- `temporal.py` (detect_conflicts: newer > registered > document_date).
- `response_handler.py` (regex `<SYSTEM_MARKET_TEMPLATE>` extract).
- `router.py` (split `<!-- MARP_START -->` → final_report.md + investment_slides.md).
- `prompts.py` (build system+user, source = `obsidian/Prompts/llm_memorandum_pipeline/`).
- `llm_client.py` (Protocol `LLMClient`, `AnthropicClient` retry × N, `MockClient`).
- `state_machine.py` (4 фазы: VALIDATING → CONTEXT_INJECTION → LLM_RUNNING → ROUTING; `_run_log.jsonl` audit).
- `cli.py` (`python -m lot_orchestrator.cli --workspace ... --lot ... [--mock-llm|--dry-run]`).

## lot_orchestrator_web/ (FastAPI, cycle 5 — в main; cycles 8-12 в открытых PR)

| Файл | Что |
|---|---|
| `main.py` | `create_app(...)` factory. Endpoints: POST /lots/{id}/run · GET /status/{run_id} · GET /needs-input · POST /provide-input · GET /artifacts · GET / |
| `runner.py` | `execute_run` async wrapper над `run_pipeline` + `patch_target_scenario` + `build_llm_client` |
| `store.py` | `RunStore` (threadsafe in-memory) + `get_store` dep + `reset_store_for_tests` |
| `templates/` | Jinja2: `base.html`, `index.html`, `needs_input.html` |
| `static/` | минимальный CSS |
| `tests/` | TestClient pytest |

## viewer/

Статический фронт для GitHub Pages:

| Файл | Что |
|---|---|
| `index.html` (≈12K строк) | Leaflet-карта + KMZ-загрузчик + карточки объектов + бейджи source/confidence для ЭТП-профиля + фикстура `parser/tests/fixtures/etp/object_etp_profile_sample.json` |
| `admin-etp-profile.html` (508 строк) | Редактор ЭТП-профиля по cad_number; генерирует YAML-патч для импорта через `etl_osv_cli` |
| `tokens.js` | Auth token gate (опц.) |
| `sw.js` | Service worker (offline кэш) |
| `v2961.html`, `admin-encode.html`, `token-gate.html` | Вспомогательные UI |

## obsidian/ (knowledge base)

| Подпапка | Содержимое |
|---|---|
| `Architecture/` | dev-доки: `lot-orchestrator.md`, `etp-exporter.md`, `etp-local-sync.md`, `etl-osv.md`, `parallel-parsers-map.md`, **`system-state-2026-05-30.md` (этот файл)**, `pending-from-other-teams.md`, `frontend-smoke-2026-05-30.md`, `dependencies.md`, `viewer-version-and-tabs-investigation.md` |
| `UserGuide/` | пользовательские: `install.md`, `etp-export.md`, `etp-osv-import.md`, `etp-checko.md`, `orchestrator-cli.md`, `orchestrator-web.md`, **`golden-path.md`, `clone-and-run.md`** |
| `Decisions/` | ADR: `ADR-001-etp-profile-extension.md`, `ADR-002-parser-checko-integration-policy.md`, **`ADR-003-temporal-v2-ownership.md`**, `2026-05-25-contour-sidecar-architecture.md`, `EGRN_Parsing_Logic.md` |
| `Changelog/` | по датам: 2026-05-29-* (PDF/DOCX, bulk pipeline, EXIF v1.2), 2026-05-30-* (parser4 inventory, orchestrator MVP, web cycle 5, folder_match, etl_checko, web cycle 8, redis+extras, cycle 11+12+httpx2) |
| `Prompts/` | `llm_memorandum_pipeline/` — спецификация SSOT (`enrich.json.tpl`), 4-фазного оркестратора, market injector |
| `Database/` | `etp-tables.md` (схема object_etp_profile/lots/lot_items) |

## docs/

| Подпапка / файл | Содержимое |
|---|---|
| `CORRESPONDENCE/` | 28 ratified postов parser↔viewer: контракт KMZ, временные оси, ЭТП-профиль координация, EXIF schema bumps |
| `CONTRACT_KMZ_2_11_0.md`, `CONTRACT_KMZ.md` | Единый источник истины формата KMZ (ratified) |
| `GOLDEN_PATH_economist_v3.md` | Текущий пайплайн pirushin-* скриптов до KMZ (см. `UserGuide/golden-path.md` для актуальной полной версии включая ЭТП и оркестратор) |
| `etp_export/` | SPEC + шаблоны Jinja для платформ ЭТП |
| `EXIF_USERCOMMENT_SCHEMA.md` | v1.1 (per-photo `note` field обсуждается в посте 027 + ack 028) |
| `KML_INGESTION_SPEC_for_viewer_team_v2.10.0.md` | Wire-формат KMZ (pin SHA в CONTRACT) |

## Зависимости (pyproject.toml — в открытом PR #92)

Базовые: `jinja2`, `pyyaml`, `pymorphy3`, `pymorphy3-dicts-ru`.

Optional (extras в pyproject — будут после merge #92):
- `[orchestrator]` — pydantic + anthropic
- `[orchestrator-web]` — + fastapi + uvicorn + python-multipart + httpx2
- `[orchestrator-redis]` — + redis
- `[egrn-full]` — pdfplumber + openpyxl + python-docx + piexif + Pillow
- `[dev]` — + pytest + pytest-cov + fakeredis

## Console scripts (после merge #92)

- `ekcelo-orchestrate` → CLI memorandum
- `ekcelo-orchestrate-web` → uvicorn wrapper (+ persistence-db / redis-url / auth-users / workers)
- `ekcelo-etp-smoke` → ЭТП-экспортёр end-to-end check (33 проверки)

## Архитектурные паттерны (живые)

- **Dependency-injection через `Depends(get_store)`** (FastAPI) для подмены store в тестах.
- **Protocol-based `LLMClient`** — лёгкая подмена провайдера, mock-friendly.
- **Idempotent fuzzy-match через `parser.utils.folder_match.best_match`** — переиспользуется в orchestrator workspace и v3 init-project.
- **Gap-fill merge в `object_etp_profile`** — все ETL (OSV, NSPD, EXIF, checko) НЕ перезатирают существующие более авторитетные source (osv/manual > nspd/exif/llm/checko).
- **Source + confidence в каждой ETP-записи** — viewer показывает бейдж разной яркости.
- **GLOB-based artifacts** (cycle 8 в #90) — путь к артефактам не сериализуется, восстанавливается с диска.
- **Background tasks + threadsafe singleton store** в FastAPI (для cycle 5; cycles 8-9 — SQLite snapshot + Redis hash+pubsub).

## Тестовое покрытие

| Suite | Тесты | Coverage |
|---|---|---|
| `parser/tests/` (smoke, ETL, KMZ, schema) | 416 pass · 4 pre-existing fail (openpyxl/pdfplumber missing) · 6 smoke | — |
| `lot_orchestrator/tests/` (cycle 4-6 в main) | 33 pass за 0.09s | 100% (schemas/response/router/temporal/workspace), 85-94% (state_machine/temporal edges) |
| `lot_orchestrator_web/tests/` (cycle 5 в main) | 9 pass | 91% (main.py error paths не покрыты в main; покрытие 95% появляется после merge #92 + #93) |
| **Combined после merge всех PR** | **109/109 pass за 2.35s** | **95%** (target met) |

## Что НЕ в main (открытые PR-ы)

- **#90** — SQLite persistence + SSE streaming + GLOB-based artifacts (cycle 8).
- **#92** — Redis multi-worker store + pyproject extras + CLI `ekcelo-orchestrate-web` (cycles 9+10). Base: #90 (после merge перенаправится на main).
- **#93** — SSE через Redis pub/sub + Basic Auth + httpx2 migration (cycles 11+12). Base: #92.

После merge всех трёх — backend готов к production multi-worker deploy.
