# Ekcelo Project Guidelines (Karpathy + Custom)

## Core Principles (Karpathy)

Behavioral guidelines to reduce common LLM coding mistakes. Merge with project-specific instructions as needed.

**Tradeoff:** These guidelines bias toward caution over speed. For trivial tasks, use judgment.

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

**These guidelines are working if:** fewer unnecessary changes in diffs, fewer rewrites due to overcomplication, and clarifying questions come before implementation rather than after mistakes.

## Project-Specific Rules

### 1. Multi-Subscription & Context Continuity
- Никогда не полагайся на память чата. Весь контекст должен храниться в файлах репозитория.
- При начале работы всегда делай: `git pull` (мысленно или явно напоминай пользователю).
- Перед завершением ответа всегда обновляй ключевые файлы: SUMMARY.md, decisions/, schema/current_schema.sql.

### 2. Knowledge Base — Obsidian (E:\Code\ekcelo\obsidian_ekcelo)
- Основная база знаний — локальный Obsidian-вот: `E:\Code\ekcelo\obsidian_ekcelo\`
- При работе с важными решениями/схемами/DB-структурой всегда предлагай обновить Obsidian (создать или обновить заметку).
- Структура заметок: `Database/`, `Parser/`, `Frontend/`, `Architecture/`, `Decisions/`.

### 3. Repository Structure (Mono-repo)
- `parser/` — Python-парсер (загружай сюда из локальной папки E:\Code\ekcelo\parcer\work_parser)
- `/` (корень) — HTML/JS просмотрщик + Cloudflare Worker
- `schema/` — текущая схема SQLite + migrations
- `docs/` + `decisions/` — документация

### 4. Database Consistency
- Единый источник правды — `schema/current_schema.sql`
- Все изменения через миграции.
- Python и JS/Worker используют одинаковые имена полей (snake_case).
- При генерации кода всегда сверяйся с текущей схемой.

### 5. Token Economy
- Будь максимально краток, если пользователь не попросил подробностей.
- Предлагай "short mode" или "detailed mode".
- Используй Caveman, если он подключён.

## Obsidian Knowledge Base
- Основная база знаний находится локально: `E:\Code\ekcelo\obsidian_ekcelo\`
- При важных решениях, изменениях схемы БД или архитектуры — всегда предлагай создать/обновить заметку в Obsidian.
- Рекомендуемая структура заметок:
  - Database/
  - Parser/
  - Frontend/
  - Architecture/
  - Decisions/