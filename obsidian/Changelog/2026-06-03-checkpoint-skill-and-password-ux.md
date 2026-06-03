# 2026-06-03 — Checkpoint-механизм (skill) + password CLI UX

## Задача
1. Ввести механизм фиксации состояния после каждого подэтапа — чтобы разработку
   мог подхватить другой разработчик (человек/AI) при окончании лимитов токенов.
2. Сделать password-CLI самообъясняющимся (пользователь не понял, куда вставлять хеш).

## Артефакты

### Checkpoint-механизм
- **`.claude/skills/checkpoint/SKILL.md`** — процедура: verification (тесты+smoke) →
  обновить `obsidian/CHECKPOINT.md` (снимок) → добавить Changelog (хронология) →
  обновить roadmap-статус → commit+push на ветке (без merge в main) → краткий отчёт.
  Инварианты: не коммитить красное молча; следующий шаг — исполнимая команда;
  CHECKPOINT.md перезаписывается, Changelog накапливается.
- **`obsidian/CHECKPOINT.md`** — живой указатель «где мы»: ветка, commit, что сделано,
  что не закончено, следующий конкретный шаг, открытые PR, указатели.
- `handoff-onboarding.md` — CHECKPOINT.md добавлен пунктом 0 «читать первым».

### Password CLI UX
- `lot_orchestrator_web/password.py`:
  - prompt с именем пользователя: «Введите пароль для 'alice' (ввод скрыт, затем Enter)».
  - hint «что дальше» печатается в **stderr** (хеш в stdout остаётся чистым для пайпа).
  - флаг `--quiet` — подавляет hint.
  - epilog в `--help` с полным сценарием: генерация → EKCELO_AUTH_USERS → вход в браузер.

## Зачем нужен password (ответ на вопрос пользователя)
Хеш вставляется в `EKCELO_AUTH_USERS`, которой защищается web-сервер оркестратора.
Применяется ТОЛЬКО если включаете Basic Auth на web-UI. Если auth не нужен —
переменную не задавать, CLI можно игнорировать. Полный сценарий — в `--help` CLI
и в `obsidian/UserGuide/orchestrator-web.md` (раздел Basic Auth).

## Тесты
- 177 passed (orchestrator + web + backend + parser smoke/checko); smoke 33/33.
- +4 CLI-теста: hint→stderr, `--quiet` подавляет, stdout pipeable (одна строка).

## Состояние
- Подэтап закрыт. main на cycle 13 (#99) + roadmap/handoff (#100).
- Следующий по плану: EXIF v1.2 (независим, parser) ИЛИ cycle 14 (OAuth, требует
  решения о приоритете vs P0 контрактного пакета). См. roadmap-2026-06.md.

## Связи
- `.claude/skills/checkpoint/SKILL.md`, `obsidian/CHECKPOINT.md`
- `obsidian/Architecture/roadmap-2026-06.md`, `handoff-onboarding.md`
