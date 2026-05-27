# Ekcelo Project Guidelines (Karpathy + Obsidian Sync)

## 1. Core Principles (Thinking & Simplicity)
- **Think Before Coding**: Сначала assumptions и tradeoffs. Не уверен — спроси.
- **Simplicity First**: Минимум кода. Никаких спекулятивных абстракций. Если можно сделать 50 строк вместо 200 — переписывай.
- **Surgical Changes**: Трогай только то, что просили. Не рефактори соседний код без команды.
- **Goal-Driven**: Каждое изменение должно быть верифицируемо.

## 2. Context & Knowledge Base (The "Obsidian" Engine)
- **Source of Truth**: GitHub Repo (`/`). Все пути — относительные.
- **Obsidian Path**: `/obsidian/` (внутри репозитория). Игнорировать `.obsidian/`.
- **Token Economy**: 
  - Перед работой читай `obsidian/Changelog/` (последние 2-3 файла) для понимания контекста последних правок.
  - Используй `obsidian/Prompts/` для сложных повторяющихся инструкций.
- **Workflow-Documentation**:
  - `obsidian/Database/` — схемы/миграции.
  - `obsidian/Architecture/` — общая структура.
  - `obsidian/Decisions/` — журнал архитектурных решений (ADR).
  - `obsidian/Changelog/` — краткие отчеты о выполненных задачах.

## 3. Repository & DB Rules
- `parser/` (Python), `schema/` (SQL), `/` (Web/Worker), `obsidian/` (Knowledge).
- **DB Truth**: «БД = слепок ЕГРН + ЭТП-профиль» (ADR-001). §1..§5 в `schema/egrn_current_schema.sql` восстанавливается из выписок ЕГРН; §6 (`object_etp_profile`, `lots`, `lot_items`) — не-ЕГРН слой с ручными правками экономиста / EXIF / NSPD / LLM, имеет поля `source` + `confidence`, при пересоздании БД из выписок НЕ восстанавливается.
- **Naming**: snake_case везде (Python, JS, SQL).
- **Migrations**: Изменения БД — только через файлы миграций в `schema/migrations/`.

## 4. Communication & Styles
- **Default Style**: **Caveman Full** (максимально кратко, только суть).
- **Thinking**: Karpathy-style (развернутое планирование) скрыто или кратко, **Output**: Сжатый.
- **Keywords**: `detailed` — для подробных объяснений, `ultra` — для экстремальной краткости.

## 🔄 EKCELO OPERATIONAL LOOP

### START (Initialization):
1. Прочитать `CLAUDE.md`, `SUMMARY.md`, `schema/egrn_current_schema.sql`.
2. Проверить `obsidian/Changelog/` на предмет последних изменений.
3. Озвучить краткий план (1-3 пункта) и список файлов под нож.

### EXECUTION:
1. Выполнить изменения в коде.
2. **Обязательно**: Создать/обновить файл в `obsidian/Changelog/YYYY-MM-DD-task-name.md` с кратким итогом.
3. Если найден новый эффективный паттерн — предложить обновить `obsidian/Prompts/`.

### DELIVERY:
- Предпочтительно: **ZIP-архив** (для >3 файлов).
- Инструкция: `Распакуй с заменой в E:\Code\ekcelo\code\`.
- Сообщение после подтверждения: `"✅ GitHub обновлён. Текущая задача: ..."`.