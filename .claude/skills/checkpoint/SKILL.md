---
name: checkpoint
description: >-
  Зафиксировать состояние разработки после завершённого подэтапа, чтобы работу
  мог продолжить другой разработчик (человек или AI) при окончании лимитов токенов.
  Use when a sub-task/cycle/step is done and state must be durably saved
  (e.g. "зафиксируй состояние", "сделай чекпойнт", "checkpoint", "заверши подэтап").
  Создаёт/обновляет obsidian/Changelog + CHECKPOINT.md (живой указатель «где мы»),
  гоняет тесты+smoke, коммитит на ветке и пушит. НЕ мержит в main без явной просьбы.
  Если git-push через прокси падает с auth-ошибкой — переходит на zip-handoff
  (см. obsidian/UserGuide/local-handoff-workflow.md).
---

# checkpoint

Фиксирует **текущее состояние** разработки так, чтобы при обрыве (конец токенов,
смена команды) преемник за один проход понял: что сделано, что зелёное, где
продолжать. Источник принципов — `CLAUDE.md` (EKCELO OPERATIONAL LOOP → DELIVERY)
и `obsidian/Architecture/handoff-onboarding.md`.

Это процедура, а не разовый файл: каждый чекпойнт обновляет **живой указатель**
`obsidian/CHECKPOINT.md` (всегда отражает последнее состояние) и **добавляет**
запись в `obsidian/Changelog/` (хронология, не перезаписывается).

## Когда вызывать

- Завершён подэтап / цикл / значимый кусок работы.
- Перед вероятным обрывом (лимиты на исходе).
- По явной просьбе пользователя.

## Procedure — основная (git push работает)

1. **Прогнать verification** (не коммитить красное):
   ```bash
   python -m pytest lot_orchestrator/tests/ lot_orchestrator_web/tests/ \
       backend/tests/ parser/tests/test_smoke_cli.py parser/tests/test_etl_checko.py -q
   python -m parser.exporters.etp.smoke_cli   # ожидается 33/33
   ```
   Записать фактические числа (N passed, smoke X/Y). Если красное — чинить
   ИЛИ явно отметить «known-red» в чекпойнте с причиной.

2. **Обновить `obsidian/CHECKPOINT.md`** (перезаписать целиком — это снимок «сейчас»):
   - Дата + ветка + последний commit SHA.
   - Что сделано в этом подэтапе (3-7 пунктов).
   - Состояние тестов (числа из шага 1).
   - **Незавершённое / в процессе** (если обрыв — что было на руках).
   - **Следующий конкретный шаг** (одна команда / один файл, чтобы преемник стартовал мгновенно).
   - Ссылка на активный пункт `roadmap-2026-06.md` и на `handoff-onboarding.md`.

3. **Добавить запись в Changelog** `obsidian/Changelog/YYYY-MM-DD-<slug>.md`
   (новый файл; современное состояние, не diff). Если в этот день по этому
   подэтапу файл уже есть — дописать секцию, не плодить дубль.

4. **Обновить roadmap-статус** если подэтап закрыл пункт:
   `obsidian/Architecture/roadmap-2026-06.md` (🚧 → ✅ или «done») и таблицу
   циклов в `obsidian/Architecture/lot-orchestrator.md`.

5. **Коммит + push** на текущей feature-ветке (НЕ main):
   ```bash
   git add -A
   git commit -m "checkpoint(<subtask>): <короткий итог> + tests N pass / smoke X/Y"
   git push -u origin <current-branch>
   ```
   Сообщение коммита всегда содержит числа тестов — это якорь для преемника.

6. **Отчёт пользователю** (кратко): что зафиксировано, ветка, как продолжить
   (одна строка), что мержить. НЕ создавать PR и НЕ мержить, если пользователь
   не просил.

## Procedure — fallback (git push не идёт через прокси)

Если шаг 5 даёт `fatal: could not read Password` / `Authentication failed` /
`Invalid username or token` — НЕ перебирать токены/прокси-варианты бесконечно.
Один-два разумных пробника достаточно. Затем переход на **zip-handoff**:

5b. Собрать архив `ekcelo-<subtask>-<YYYY-MM-DD>.zip` со структурой:
    ```
    HANDOFF.md          — инструкция для этого подэтапа (ветка, коммит-msg, PR title/body)
    files/<repo-relative>/...   — все новые/изменённые файлы
    manifest.json       — список файлов + sha256 + base/branch
    ```
    Файлы — те, что попадали бы в `git commit` (см. `git status --porcelain`).

6b. Отдать пользователю через `SendUserFile` (status=proactive) с caption,
    указывающим: куда сохранить (Downloads), что делать дальше (читать HANDOFF.md
    из архива). Пользователь распаковывает, копирует, push'ит со своей машины.

7b. В отчёте указать: «push не прошёл (proxy auth), отдал zip-архив; жду
    подтверждение и номер PR от вас». См. `obsidian/UserGuide/local-handoff-workflow.md`
    для полной процедуры пользователя.

## Инварианты

- **Никогда не коммитить красные тесты молча.** Либо зелёное, либо явный
  «known-red + причина» в CHECKPOINT.md.
- **CHECKPOINT.md = снимок, Changelog = хронология.** Первый перезаписывается,
  второй накапливается.
- **Следующий шаг — исполнимая команда**, не абстракция («доделать X» — плохо;
  «`git checkout -b orchestrator/cycle-14-oauth`, читать roadmap §Cycle 14,
  создать `lot_orchestrator_web/oauth.py`» — хорошо).
- **Не мержить в main** без явной просьбы — чекпойнт фиксирует на ветке (или
  в zip-handoff).
- README.md в obsidian/ — gitignored; указатель называется `CHECKPOINT.md`.
- **Не утопать в попытках починить транспорт.** Два разумных пробника push'а —
  затем zip-handoff.

## Шаблон CHECKPOINT.md

```markdown
# CHECKPOINT — <YYYY-MM-DD>

> Живой указатель «где мы». Обновляется каждым чекпойнтом. Снимок, не хронология
> (хронология — obsidian/Changelog/). Для въезда новой команды — сначала
> obsidian/Architecture/handoff-onboarding.md.

## Сейчас
- **Ветка:** `<branch>` (commit `<sha7>`)
- **Подэтап:** <что делали>
- **Тесты:** <N> passed; smoke <X/Y>
- **main на:** <последний merge / cycle>
- **Канал доставки:** git push ИЛИ zip-handoff (см. local-handoff-workflow.md)

## Сделано в этом подэтапе
- ...

## В процессе / не закончено
- ... (или «нет — подэтап закрыт целиком»)

## Следующий конкретный шаг
```bash
<исполнимая команда старта>
```
Читать: `obsidian/Architecture/roadmap-2026-06.md` §<пункт>.

## Открытые PR
- #NNN — <что> (base main)

## Указатели
- Планы: `obsidian/Architecture/roadmap-2026-06.md`
- Онбординг: `obsidian/Architecture/handoff-onboarding.md`
- Снимок системы: `obsidian/Architecture/system-state-2026-05-30.md`
- Workflow zip-handoff: `obsidian/UserGuide/local-handoff-workflow.md`
```
