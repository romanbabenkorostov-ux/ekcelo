# CHECKPOINT — 2026-06-03

> Живой указатель «где мы». Обновляется каждым чекпойнтом (skill `checkpoint`).
> Снимок, не хронология (хронология — `obsidian/Changelog/`). Для въезда новой
> команды — сначала `obsidian/Architecture/handoff-onboarding.md`.

## Сейчас
- **Ветка:** `chore/checkpoint-mechanism-and-password-ux` (ответвлена от main `ae1e5b1`)
- **Подэтап:** checkpoint-механизм (skill) + password CLI UX
- **Тесты:** 177 passed; smoke 33/33
- **main на:** cycle 13 (PBKDF2 hashing) после merge #99; roadmap+handoff после #100

## Сделано в этом подэтапе
- Добавлен skill `.claude/skills/checkpoint/SKILL.md` — процедура фиксации
  состояния после каждого подэтапа (verification → CHECKPOINT.md → Changelog →
  roadmap-статус → commit+push на ветке, без merge в main).
- `lot_orchestrator_web/password.py` CLI стал самообъясняющимся:
  - prompt с именем пользователя («Введите пароль для 'alice' (ввод скрыт…)»);
  - hint «что дальше» в **stderr** (хеш остаётся чистым в stdout для пайпа);
  - `--quiet` подавляет hint;
  - epilog в `--help` с полным сценарием (генерация → env → вход в браузер).
- Создан этот `obsidian/CHECKPOINT.md`.
- +4 теста CLI (hint→stderr, --quiet, pipeable stdout).

## В процессе / не закончено
- Подэтап закрыт целиком. PR ещё не создан (создаётся следующим шагом).

## Следующий конкретный шаг
```bash
# Закоммитить+запушить текущую ветку, открыть PR (base=main).
# Затем — следующий цикл по плану. Кандидат №1 (независим, parser-сторона):
git checkout main && git pull origin main
git checkout -b parser/exif-v1-2-per-photo-note
# Читать: obsidian/Architecture/roadmap-2026-06.md §EXIF v1.2
#         docs/CORRESPONDENCE/027-*.md, 028-*.md (ack)
# Править: docs/EXIF_USERCOMMENT_SCHEMA.md (v1.1→v1.2) + parser/exporters/etp/etl_exif.py
```
Альтернатива — cycle 14 (OAuth), но требует решения о приоритете vs P0
контрактного пакета (см. roadmap §Порядок).

## Открытые PR
- (этот подэтап) — будет PR с base=main после commit+push.

## Указатели
- Планы: `obsidian/Architecture/roadmap-2026-06.md`
- Онбординг: `obsidian/Architecture/handoff-onboarding.md`
- Снимок системы: `obsidian/Architecture/system-state-2026-05-30.md`
- Принципы: `CLAUDE.md` (EKCELO OPERATIONAL LOOP)
