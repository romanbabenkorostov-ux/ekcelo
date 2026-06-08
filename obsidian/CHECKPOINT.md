# CHECKPOINT — 2026-06-03 (P0.2 sub-stages A+B done · zip-handoff active)

> Живой указатель «где мы». Обновляется каждым чекпойнтом (skill `checkpoint`).
> Снимок, не хронология (хронология — `obsidian/Changelog/`). Для въезда новой
> команды — сначала `obsidian/Architecture/handoff-onboarding.md`.

## Сейчас
- **Ветка (sandbox):** `backend/p0-bundle-importer` (2 коммита: sub-stage A + sub-stage B на одной ветке для одного PR)
- **Подэтап:** P0.2 Bundle importer — **sub-stages A + B** закрыты.
- **Тесты:** 205 passed; smoke 33/33
- **main на:** cycle 13 (PBKDF2) + roadmap+handoff (#100) + checkpoint-skill+password-UX (#101)
- **Канал доставки:** ⚠️ **zip-handoff** (git push из sandbox через proxy
  отдаёт «Invalid username or token»). Архивы складируются в чате через
  `SendUserFile`; пользователь распаковывает + пушит со своей машины. См.
  `obsidian/UserGuide/local-handoff-workflow.md`.

## Сделано (на этой ветке)

### Sub-stage A — ядро Bundle importer
- `backend/app/services/bundle.py` (~415 LOC): Pydantic-схема манифеста C3,
  `load_manifest`, `verify_files`, идемпотентный `import_bundle` с upsert по
  content-hash. Уважает ADR-001 §6 (manual/osv не перезатирается).
- `backend/tests/test_bundle.py` — 16 service-тестов.

### Sub-stage B — REST + CLI
- `lot_orchestrator_web/bundle_cli.py` — CLI `ekcelo-import-bundle` (тонкая
  обёртка над сервисом; exit codes 0/2/3/4; `--dry-run`, `--no-verify`, `--json`).
- `lot_orchestrator_web/main.py` — `POST /bundles/import` (multipart upload,
  поддерживает 2 формы архива: файлы в корне или в подкаталоге).
- `pyproject.toml::[project.scripts]::ekcelo-import-bundle`.
- 15 новых тестов (7 CLI + 8 endpoint).

### Документация
- `obsidian/Architecture/p0-bundle-importer.md` (объединённый снимок A+B).
- `obsidian/Architecture/roadmap-2026-06.md` (A ✅ B ✅ C 🚧).
- `obsidian/Changelog/2026-06-03-p0-bundle-importer-substage-b.md`.
- `obsidian/UserGuide/local-handoff-workflow.md` (workflow zip-handoff — для пользователя).
- `.claude/skills/checkpoint/SKILL.md` (+ fallback на zip).

## В процессе / не закончено

- **Sub-stage C** (= P0.3) — ViewModel REST endpoints. Не начат.
- Регистрация KMZ в локальном хранилище для будущего `/bundles/{id}/download`
  отложена до C (потребует sidecar-таблицы `bundles`).
- Push из sandbox в GitHub не работает — продолжаем через zip-handoff.

## Следующий конкретный шаг

После получения архива sub-stages A+B (или отдельных архивов для A и B):

1. Распаковать в `C:\Users\Соня\Downloads\ekcelo-handoff\`.
2. Скопировать содержимое `files/` в `E:\Code\ekcelo\ftontback2026-01-02\`.
3. По инструкции `HANDOFF.md` внутри архива: создать ветку, коммит, push, открыть PR.
4. Сообщить мне номер PR. Я начну sub-stage C.

## Открытые PR

- Локально готово: sub-stage A (16 тестов) + sub-stage B (15 тестов) на одной
  ветке. PR ещё не открыт (zip-handoff в процессе).

## Указатели
- Планы: `obsidian/Architecture/roadmap-2026-06.md` (P0.2 sub-stages A+B done)
- Подэтап-снимок: `obsidian/Architecture/p0-bundle-importer.md`
- Спека: `docs/specs/SPEC_backend.md`
- Контракт: `contracts/bundle/BUNDLE_SPEC.md` + `contracts/api/openapi.yaml`
- Онбординг: `obsidian/Architecture/handoff-onboarding.md`
- Workflow zip-handoff: `obsidian/UserGuide/local-handoff-workflow.md`
- Принципы: `CLAUDE.md` (EKCELO OPERATIONAL LOOP)
