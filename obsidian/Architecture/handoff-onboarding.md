# Передача проекта новой команде разработки (onboarding)

> Документ для случая, когда текущий AI-разработчик (Claude) недоступен и проект подхватывает другая команда (люди или другой AI). Цель: за один проход въехать в курс дела и продолжить разработку без потери контекста.

## 0. TL;DR за 60 секунд

- **Что это:** Ekcelo — система оценки/продажи залогового недвижимого имущества. Парсит выписки ЕГРН → обогащает (NSPD/EXIF/checko/OSV) → экспортирует карточки ЭТП + KMZ → показывает в viewer. Плюс LLM-оркестратор меморандумов.
- **Архитектурный вектор (2026-06):** переход к **contracts-driven multi-repo**: три кодовые базы (parser локальный / ekcelo backend / ekcelo-site frontend) сходятся через пакет `contracts/` (C1-C6). Web-шов = REST-рендеринг ViewModel; единица обмена = Bundle.
- **Источник истины:** `contracts/` (контракты) + `docs/specs/SPEC_*.md` (спеки команд). Код вторичен.
- **Где продолжать:** `obsidian/Architecture/roadmap-2026-06.md` (циклы 14-16 + EXIF v1.2).
- **Правило изменений:** spec-PR-first + дуальная мажоритарность (см. `contracts/PACKAGE.md` / `docs/CONTRACT_KMZ.md` §3).

## 1. Карта репозитория (что где живёт)

| Путь | Что | Статус |
|---|---|---|
| `contracts/` | **C1-C6 нормативные контракты** (KMZ/DB/Bundle/REST-ViewModel/Lot/Roles). Source of truth кросс-команды. | живой, v1.0.0 |
| `docs/specs/SPEC_{parser,backend,frontend}.md` | Спеки трёх команд | живой |
| `docs/CORRESPONDENCE/` | Append-only журнал согласований parser↔viewer (28 постов) | живой |
| `docs/CONTRACT_KMZ*.md` | KMZ wire-формат (C1, SemVer 2.12.0) | ratified |
| `parser/egrn_parser/` | Парсер ЕГРН v1.10 (PDF/XML/ОСВ → SQLite) | прод |
| `parser/exporters/etp/` | ЭТП-экспортёр Stage 1-6 + smoke (22 модуля) | прод |
| `parser/scripts/` | Пайплайн-скрипты pirushin_* (01→08 до KMZ) | прод |
| `lot_orchestrator/` | CLI меморандум-пайплайн (4 фазы, cycle 4-6) | прод |
| `lot_orchestrator_web/` | FastAPI обёртка (cycle 5-13: persistence/redis/SSE/auth/hashing) | прод |
| `backend/app/` | Re-export layer под fastapi-template (zero-logic) | прод |
| `viewer/` | Статический HTML+Leaflet KMZ-viewer | **deprecated** (в пользу ekcelo-site) |
| `schema/` | SQLite DDL + миграции (`0001_etp_profile.sql`) | прод |
| `serve.py` | Foolproof launcher backend'а (PYTHONPATH+reload) | прод |
| `obsidian/` | **Вся проектная память** (читать первой) | живой |

### obsidian/ — внутренняя память (читать в порядке)

0. **`obsidian/CHECKPOINT.md`** — живой указатель «где мы прямо сейчас»:
   текущая ветка, последний commit, что сделано, **следующий конкретный шаг**.
   Обновляется skill'ом `checkpoint` после каждого подэтапа. Читать ПЕРВЫМ.

1. `obsidian/Architecture/system-state-2026-05-30.md` — снимок всей системы.
2. `obsidian/Architecture/handoff-onboarding.md` — **этот файл**.
3. `obsidian/Architecture/roadmap-2026-06.md` — что делать дальше.
4. `obsidian/Architecture/mechanisms-for-maintainers.md` — как работают front/back/окружение.
5. `obsidian/Architecture/lot-orchestrator.md` — детали orchestrator (таблица циклов).
6. `obsidian/Architecture/backend-template-mapping.md` — layout backend/ ↔ fastapi-template.
7. `obsidian/Decisions/ADR-001..003.md` — зафиксированные архитектурные решения.
8. `obsidian/Changelog/` — хронология (читать последние 5-10 для свежего контекста).
9. `obsidian/UserGuide/` — пользовательские инструкции (golden-path, data-flows, clone-and-run).
10. `obsidian/Prompts/llm_memorandum_pipeline/` — спецификация оркестратора.

## 2. Первые 30 минут новой команды

```bash
# 1. Клонировать + окружение (Win10/Linux — см. UserGuide/clone-and-run.md)
git clone https://github.com/romanbabenkorostov-ux/ekcelo.git
cd ekcelo
python -m venv .venv && source .venv/bin/activate   # или .\.venv\Scripts\Activate.ps1
pip install -e ".[dev]"

# 2. Убедиться, что всё зелёное
python -m pytest lot_orchestrator/tests/ lot_orchestrator_web/tests/ backend/tests/ \
    parser/tests/test_smoke_cli.py parser/tests/test_etl_checko.py
python -m parser.exporters.etp.smoke_cli          # 33/33

# 3. Поднять backend + frontend (для понимания «как выглядит»)
python serve.py                                    # backend :8000 → /docs
python -m http.server 8001                         # frontend → /viewer/index.html

# 4. Прочитать obsidian/ в порядке из §1
```

Если тесты НЕ зелёные при свежем клоне — это первый баг к фиксу (вероятно missing extras: `pip install -e ".[dev,egrn-full]"`).

## 3. Принципы разработки (унаследовать)

Из `CLAUDE.md` (корень репо) — обязательны к соблюдению:
- **Think before coding** — сначала assumptions/tradeoffs, не уверен → спроси.
- **Simplicity first** — минимум кода, без спекулятивных абстракций.
- **Surgical changes** — трогать только то, что просили.
- **Migrations only via `schema/migrations/`** — БД не правится напрямую.
- **snake_case везде** (Python/JS/SQL).
- **БД = слепок ЕГРН + ЭТП-профиль** (ADR-001): §1-5 восстанавливаются из выписок; §6 (object_etp_profile/lots/lot_items) — не-ЕГРН слой с source+confidence.

Из практики этого проекта:
- **Каждый цикл** = ветка + тесты (цель ≥95% coverage) + обновление obsidian (Architecture + Changelog) + PR. Не мержить без зелёных тестов.
- **Документация в obsidian пишет ТЕКУЩЕЕ состояние**, не diff'ы (diff'ы — в Changelog).
- **spec-PR-first**: контракт меняется PR'ом в `contracts/` + bump SemVer + ack доменной команды ДО кода.
- **Не добавлять тяжёлых зависимостей** без причины (паттерн: stdlib > opt-in extras > mandatory dep).

## 4. Открытые направления (что делать дальше)

Полные спеки — в `obsidian/Architecture/roadmap-2026-06.md`. Кратко:

| Направление | Реализует контракт | Зависит от | Приоритет |
|---|---|---|---|
| **P0 контрактного пакета** (по SPEC_backend) | C2 DB + C3 Bundle import + C4 REST/ViewModel | — | **высший** |
| EXIF v1.2 per-photo note | EXIF_USERCOMMENT_SCHEMA bump | — (parser-A) | независим |
| Cycle 14 OAuth/OIDC | C6 (auth-эволюция) | — | P1 |
| Cycle 15 RBAC | C6 ROLES_SPEC целиком | cycle 14 | P1 |
| Cycle 16 rate limiting | hardening | желательно после 14 | P2 |

> **Важная развилка для новой команды:** auth-трек (14-16) делался текущим AI как продолжение orchestrator-стека. Но по `docs/specs/SPEC_backend.md` высший приоритет (P0) — это **DB-контракт C2 + импортёр Bundle + ViewModel REST C4**, потому что они разблокируют веб-шов между бэком и фронтом (ekcelo-site). Если ресурс ограничен — берите P0 контрактного пакета первым, auth-трек после. Финальный приоритет — за владельцем репозитория `romanbabenkorostov-ux`.

## 5. Незакрытые координационные вопросы

Все на 2026-06-03 закрыты или self-resolved (см. `obsidian/Architecture/pending-from-other-teams.md`):
- Posts 019/020/022/025 — closed.
- Post 027 (EXIF v1.2) — self-resolved через 028 (recommended options). При появлении живого viewer-team — можно пересмотреть отдельным постом.
- ADR-003 — ownership temporal-v2 тем; DB-миграция deferred до adoption Alembic/SQLModel.

## 6. Чего ОПАСАТЬСЯ (граблеведение)

1. **Stacked PR в main не доезжают.** Если делаете цепочку PR с base на feature-ветки — merge сводит их друг в друга, но НЕ в main. Урок (PR #99): для доставки в main нужен PR с base=main. Проверяйте `git merge-base --is-ancestor <branch> origin/main`.
2. **`uvicorn backend.app.main:app` падает с ModuleNotFoundError** без `--app-dir .` / `serve.py` / `PYTHONPATH`. См. `mechanisms-for-maintainers.md` §1.1.
3. **README.md gitignored** (корневой `.gitignore` строка 2). Индекс-файлы называйте иначе (`README_BACKEND.md`, `README_FRONTEND.md`).
4. **Чужой venv** → ModuleNotFoundError. venv ВНУТРИ клона.
5. **viewer/ deprecated** — новые UI-фичи идут в ekcelo-site (отдельный репо), не сюда. Контракт фронта — C4 ViewModel REST.
6. **ANTHROPIC_API_KEY — opt-in.** Нужен только для реального LLM-вызова в orchestrator. Всё остальное (парсинг/ЭТП/KMZ/viewer) работает без ключа. Не делайте его обязательным.

## 7. Как продолжить конкретный цикл (пример: cycle 14)

```bash
git checkout main && git pull origin main
git checkout -b orchestrator/cycle-14-oauth
# Читать: obsidian/Architecture/roadmap-2026-06.md §Cycle 14
#         contracts/roles/ROLES_SPEC.md (C6)
# Реализовать lot_orchestrator_web/oauth.py + тесты в lot_orchestrator_web/tests/
# Обновить: obsidian/Architecture/lot-orchestrator.md (таблица: cycle 14 ✅)
#           obsidian/Changelog/YYYY-MM-DD-cycle-14-oauth.md
#           obsidian/Architecture/roadmap-2026-06.md (cycle 14 → done)
pytest lot_orchestrator_web/tests/   # должно остаться зелёным
git push -u origin orchestrator/cycle-14-oauth
# PR с base=main (НЕ на feature-ветку!)
```

## 8. Точки контакта / арбитраж

- **Владелец репозитория / арбитр:** `romanbabenkorostov-ux` (GitHub). Финальное решение по приоритетам и кросс-командным развилкам.
- **Governance изменений контрактов:** `contracts/PACKAGE.md` + `docs/CONTRACT_KMZ.md` §3 (дуальная мажоритарность: данные→parser/backend, UI→frontend, кросс→обе+арбитр).
- **Связь между командами:** новый пост в `docs/CORRESPONDENCE/NNN-*.md` (append-only, следующий номер).

## 9. Чек-лист «я готов продолжать»

- [ ] Клон собран, `pytest` зелёный, smoke 33/33.
- [ ] backend поднимается (`serve.py` → /docs), frontend открывается (/viewer/index.html).
- [ ] Прочитаны: system-state, этот файл, roadmap-2026-06, lot-orchestrator, CLAUDE.md.
- [ ] Понятен contracts/ (C1-C6) и какой цикл какой контракт реализует.
- [ ] Понятна развилка приоритетов (P0 контрактов vs auth-трек) — решение получено у владельца.
- [ ] Выбран следующий цикл из roadmap-2026-06; заведена ветка с base=main.

## Связи

- `obsidian/Architecture/roadmap-2026-06.md` — детальные планы циклов.
- `obsidian/Architecture/system-state-2026-05-30.md` — снимок системы.
- `contracts/PACKAGE.md` — контрактный пакет.
- `docs/specs/SPEC_{parser,backend,frontend}.md` — спеки команд.
- `CLAUDE.md` (корень) — операционные принципы.
