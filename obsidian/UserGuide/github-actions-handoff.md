# GitHub Actions Apply-Handoff (P0.1.3 setup)

> Альтернатива zip-handoff через PowerShell-копипаст. Workflow
> `.github/workflows/apply-handoff.yml` принимает URL zip-архива от Claude и
> сам создаёт ветку + PR. Разовая настройка ~5 минут.

## Зачем

Текущий zip-handoff (см. `local-handoff-workflow.md`) требует от вас 8-9 шагов
в PowerShell на каждый sub-stage. Этот workflow автоматизирует все шаги после
загрузки zip из чата.

## Разовая настройка

### 1. Создать Fine-grained PAT

1. https://github.com/settings/personal-access-tokens/new
2. **Token name:** `ekcelo-handoff-bot`
3. **Expiration:** `Custom` — выберите дату через **1 год** (максимум для FG-PAT).
4. **Repository access:** `Only select repositories` → `romanbabenkorostov-ux/ekcelo`.
5. **Repository permissions:**
   - Contents: **Read and write**
   - Pull requests: **Read and write**
   - Metadata: Read (авто)
6. Generate token → скопируйте (показывается один раз).

### 2. Положить в Repository Secrets

1. https://github.com/romanbabenkorostov-ux/ekcelo/settings/secrets/actions
2. New repository secret:
   - Name: `EKCELO_APPLY_PAT`
   - Secret: вставьте PAT
3. Save.

### 3. Workflow уже в репо

`.github/workflows/apply-handoff.yml` — этот workflow смержен вместе с
P0.1.3.

## Каждый sub-stage (workflow подход)

Когда Claude доставляет архив:

### Вариант A — через `gh` CLI (быстрее)

```powershell
# В PowerShell:
cd "C:\Users\Соня\Downloads"

# 1. Загрузите zip как gist (получите ссылку для скачивания)
gh gist create "ekcelo-PX-CLEAN-v2.zip" --desc "ekcelo handoff PX" --public=false

# Вывод последней строкой даст URL вида https://gist.github.com/<user>/<id>
# Откройте этот URL в браузере, ПКМ на файле → Copy raw URL
# Раw URL: https://gist.githubusercontent.com/<user>/<id>/raw/<hash>/ekcelo-PX-CLEAN-v2.zip

# 2. Запустите workflow
gh workflow run apply-handoff.yml `
  --repo romanbabenkorostov-ux/ekcelo `
  -F archive_url="<raw_URL>" `
  -F branch_name="backend/p0-X" `
  -F commit_message="feat(backend): P0.X — ..." `
  -F pr_title="P0.X — ..."

# 3. Через 10-30 секунд PR откроется автоматически
gh pr list --repo romanbabenkorostov-ux/ekcelo --author "ekcelo-handoff-bot"
```

### Вариант B — через GitHub UI (без gh CLI)

1. https://gist.github.com → Drag&Drop zip → Save (выберите Secret gist).
2. На странице gist'а ПКМ на файле → Copy raw URL.
3. https://github.com/romanbabenkorostov-ux/ekcelo/actions/workflows/apply-handoff.yml
4. Кнопка `Run workflow` (справа сверху) → заполните 4 поля:
   - `archive_url` — раw URL из шага 2
   - `branch_name` — например `backend/p0-1-3-codegen`
   - `commit_message`
   - `pr_title`
5. `Run workflow` → ждёте 10-30 секунд → проверяете PR.

## После создания PR

Прежде чем мержить — локально прогон smoke:
```powershell
cd E:\Code\ekcelo\ftontback2026-01-02
git fetch origin <branch_name>:<branch_name>
git checkout <branch_name>
python -m pytest backend/tests/ -q
git checkout main
```

Если зелёное — мержите PR через UI как обычно.

## Безопасность

- PAT хранится в **Repository Secrets** — не виден в логах workflow (замаскирован).
- PAT scope ограничен **этим репо**, права минимальные.
- Workflow коммитит как `ekcelo-handoff-bot` — отличимо от ваших коммитов в истории.
- Срок PAT — 1 год; за 7 дней GitHub шлёт email напоминание о ротации.

## Что делать при истечении PAT

1. Создаёте новый PAT (шаг 1).
2. Заходите в Repository Secrets, кликаете на `EKCELO_APPLY_PAT` → Update.
3. Workflow продолжает работать без изменений.

## Сравнение с zip-handoff

| Шаг | zip-handoff (PowerShell) | Actions workflow |
|---|---|---|
| Скачать zip из чата | ✓ | ✓ |
| Распаковать локально | `Expand-Archive` | автоматически |
| Создать ветку | `git checkout -b` | автоматически |
| Скопировать `files/` | `Copy-Item` | автоматически |
| Прогон тестов локально | `pytest` | вручную после открытия PR |
| Commit + push | 3 команды | автоматически |
| Открыть PR | вручную | автоматически |
| **Итого шагов вручную** | **8-9** | **2-3** (gist + run workflow) |

## Связи

- Workflow: `.github/workflows/apply-handoff.yml`
- Старый сценарий (всё ещё доступен): `obsidian/UserGuide/local-handoff-workflow.md`
- Snapshot этой фичи: `obsidian/Architecture/p0-db-contract.md` (P0.1.3 § Setup)
