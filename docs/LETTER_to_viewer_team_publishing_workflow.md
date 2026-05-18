# Письмо команде №2 (viewer/worker) — как публиковать наработки без конфликтов

**Дата:** 2026-05-18
**От:** команда parser (ветка `claude/review-project-structure-aEdDY`)
**Кому:** команда viewer/worker
**Репо:** https://github.com/romanbabenkorostov-ux/ekcelo

---

## 1. Почему у вас 403

403 при `git push` = ваш GitHub-аккаунт **не в списке collaborators** репозитория `romanbabenkorostov-ux/ekcelo`. Это не баг и не сетевая проблема — это намеренное ограничение прав. Ни смена токена, ни force-push это не починят.

Чинить надо одним из двух способов (выбираете вы + владелец репо):

### Вариант A — Fork + Pull Request (рекомендуется)
Не требует прав на основной репо. Безопаснее всего.

```bash
# 1. Один раз: форкнуть romanbabenkorostov-ux/ekcelo через GitHub UI в свой аккаунт
# 2. Клонировать СВОЙ форк, а не основной репо
git clone https://github.com/<ваш-аккаунт>/ekcelo.git
cd ekcelo
git remote add upstream https://github.com/romanbabenkorostov-ux/ekcelo.git

# 3. Перед началом работы — синк с основным
git fetch upstream
git checkout main
git merge upstream/main

# 4. Ветка под фичу
git checkout -b team2/<feature-name>

# ... коммиты ...

# 5. Пуш в СВОЙ форк (403 здесь не будет)
git push -u origin team2/<feature-name>

# 6. Открыть PR через GitHub UI: <ваш-форк>:team2/<feature-name> → romanbabenkorostov-ux:main
```

### Вариант B — Прямой доступ collaborator
Владелец репо (`romanbabenkorostov-ux`) добавляет ваш аккаунт:
`Settings → Collaborators → Add people`.
После этого вы пушите ветки `team2/*` напрямую и открываете PR изнутри.

**В обоих случаях:** мерж в `main` — только через PR с ревью. Никаких прямых пушей в `main`.

---

## 2. Как не ломать друг друга — разделение зон ответственности

Сейчас репо моно, корень захламлён. Договариваемся о **жёстких зонах**. Никто не трогает чужую зону без PR-обсуждения.

| Зона | Кто владеет | Что внутри |
|---|---|---|
| `parser/` | команда parser | Python-парсер, миграции БД, генератор дампа |
| `viewer/` *(новая)* | **команда viewer** | `index.html`, `sw.js`, фронтовые ассеты |
| `worker/` *(новая)* | **команда viewer** | `worker.js`, Cloudflare Worker конфиг |
| `schema/` | shared (PR обязателен) | `current_schema.sql`, миграции |
| `docs/` | shared | спеки, golden path, письма |
| `decisions/` | shared | ADR — архитектурные решения |
| корень `/` | shared (минимально) | только `README.md`, `CLAUDE.md`, `.gitignore`, `_config.yml` |

### Что предлагаем перенести (вашими руками, отдельным PR)

```
index.html                      → viewer/index.html
sw.js                           → viewer/sw.js
worker.js                       → worker/worker.js
worker_good_work2026-04-26.js   → worker/archive/
schema.sql                      → schema/current_schema.sql
fix/                            → viewer/fix/        (если ваше)
scripts/                        → решить, чьё
```

Корневые `pirushin_sosn_rocha_*.py` — наши, не трогайте, мы их сами реструктурируем в `parser/pipeline/`.

---

## 3. Контракт между parser и viewer — единственная точка связи

Чтобы зоны были реально независимыми, **связь только через формат данных**, не через общий код:

- **Источник правды для схемы БД:** `schema/current_schema.sql`. Snake_case везде.
- **Источник правды для KML/дампа:** `docs/KML_INGESTION_SPEC_for_viewer_team_v2.10.0.md`. Это контракт. Парсер обязан его соблюдать на выходе, viewer — на входе.
- Любое изменение контракта = PR в `docs/` + bump версии спеки + аппрув обеих команд **до** изменения кода.

Правило: **если меняешь поле в БД или KML — сначала PR в spec, потом код.** Не наоборот.

---

## 4. Рабочий процесс веток

Именование:
- `team2/<feature>` — ваши фичи
- `parser/<feature>` — наши
- `shared/<topic>` — общие (schema, docs, decisions) — требуют ревью обеих команд
- `hotfix/<issue>` — срочные правки

PR-чеклист (короткий):
- [ ] Изменения **только в своей зоне** (или PR помечен `shared`)
- [ ] Если тронут контракт (`schema/`, `docs/*_SPEC*.md`) — есть аппрув второй команды
- [ ] `main` не сломан: тесты/линтер прошли
- [ ] В описании PR — что и зачем, без воды

---

## 5. Что мы (parser) уже зафиксировали с нашей стороны

- Ветка `claude/review-project-structure-aEdDY`, последний коммит `6d55b6c`.
- `pirushin_sosn_rocha_08_build_kmz_v2.py` — приведён к контракту KML v2.10.0.
- `docs/KML_INGESTION_SPEC_for_viewer_team_v2.10.0.md` — спека для вас.
- 21 тест в `tests/` зелёные.

Когда вы переедете в `viewer/` и `worker/`, мы синхронно подвинем свои импорты/ссылки.

---

## 6. Действия от вас (порядок)

1. Решить с владельцем репо: fork+PR или collaborator-доступ.
2. Прочитать `docs/KML_INGESTION_SPEC_for_viewer_team_v2.10.0.md`.
3. Открыть PR `shared/repo-layout` с переездом `index.html`/`sw.js`/`worker.js` в `viewer/` и `worker/` (один коммит, без правок кода — только `git mv`). Мы ревьюим в тот же день.
4. Дальше пушите фичи в `team2/*` уже в новой структуре.

Вопросы — в `docs/` отдельным `.md` или комментом к PR. Не в личку — теряется контекст.

---

*Файл хранится в репо: `docs/LETTER_to_viewer_team_publishing_workflow.md` — единый источник правды для этого письма, обновляется через PR.*
