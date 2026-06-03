# 2026-06-03 — Roadmap циклов 14-16 + EXIF v1.2 + onboarding для передачи команде

## Задача
Подготовить репозиторий к возможному продолжению разработки другой командой (при недоступности текущего AI). Зафиксировать чёткие планы следующих циклов и онбординг-инструкцию. Плюс — инструкция обновления локального клона через VS Code (по факту устаревшего клона у пользователя).

## Артефакты

- **`obsidian/Architecture/roadmap-2026-06.md`** — детальные планы:
  - Cycle 14 (OAuth2/OIDC) — реализует C6 auth-эволюцию.
  - Cycle 15 (Per-lot RBAC) — реализует `contracts/roles/ROLES_SPEC.md` целиком.
  - Cycle 16 (Rate limiting на auth-провалы) — hardening.
  - EXIF v1.2 (per-photo note) — закрывает post 027/028 (parser-сторона).
  - Каждый цикл: зачем / scope / не-в-scope / тесты / зависимости / acceptance.
  - Граф зависимостей + напоминание о приоритете P0 контрактного пакета.

- **`obsidian/Architecture/handoff-onboarding.md`** — передача новой команде:
  - TL;DR за 60 секунд + карта репозитория + порядок чтения obsidian.
  - «Первые 30 минут» (клон → тесты → запуск → чтение).
  - Принципы разработки (из CLAUDE.md + практики проекта).
  - Открытые направления с приоритетами + развилка «P0 контрактов vs auth-трек».
  - Граблеведение (stacked-PR не доезжают в main, uvicorn ModuleNotFound, README gitignored, viewer deprecated, API-key opt-in).
  - Пример «как продолжить cycle 14» + чек-лист готовности.

- **`obsidian/UserGuide/clone-and-run.md`** — добавлена секция «Обновление существующего клона»:
  - Способ A (кнопка Sync в VS Code) + Способ B (терминал `git pull` + `pip install -e`).
  - Разбор `ModuleNotFoundError: lot_orchestrator_web.password` = устаревший клон.
  - Разрешение конфликтов при pull (stash / checkout).

## Контекст согласования с contracts/

Учтён параллельный вклад PR #98 (другая команда): пакет `contracts/` (C1-C6) + три `docs/specs/SPEC_*.md`. Roadmap НЕ переопределяет контракты — указывает, какой контракт реализует каждый цикл:
- Cycle 15 RBAC → `contracts/roles/ROLES_SPEC.md` (C6).
- Cycle 14 OAuth → C6 «OAuth/JWT — будущий триггер».
- Зафиксирована развилка: по `SPEC_backend.md` высший приоритет (P0) — C2 DB + Bundle import + ViewModel REST (C4), а не auth-трек. Финальный выбор — за владельцем репо.

## Состояние на момент написания

- main на cycle 13 (PBKDF2 hashing) после merge #99.
- viewer/ помечен deprecated в пользу ekcelo-site (по #98).
- Все координационные posts закрыты/self-resolved.

## Связи
- `obsidian/Architecture/roadmap-2026-06.md`
- `obsidian/Architecture/handoff-onboarding.md`
- `contracts/PACKAGE.md`, `docs/specs/SPEC_*.md`
