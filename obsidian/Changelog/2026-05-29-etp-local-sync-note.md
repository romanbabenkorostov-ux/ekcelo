# 2026-05-29 — Заметка о локальной синхронизации ЭТП-пакета

## Итог
По инциденту `ModuleNotFoundError: No module named 'parser.exporters.etp.auto_export'`
зафиксирована корневая причина и канонический способ синхронизации.

## Причина (не баг кода)
Локальная копия (`E:\Code\ekcelo\code`) набиралась из выборочных ZIP, в которые
не попали `auto_export.py` / `appendix.py` (мёржены в репо ранее). При запуске
`etl_pipeline_cli` импорт падал — файла буквально не было на диске.

`python -m parser.exporters.etp.<module>` из корня репо работает через
namespace-пакет, `pip install` не нужен. Упаковка (`pyproject.toml`) ни при чём.

## Решение
- **Канон:** `git pull --ff-only origin main` после каждого мёржа — полное
  состояние без пропусков транзитивных зависимостей.
- **Если push/pull недоступны:** полный пакетный ZIP `parser/exporters/etp/`
  целиком, не diff-набор.
- Проверка целостности — однострочный import-чек (см. документ).

## Артефакт
- `obsidian/Architecture/etp-local-sync.md` — инструкция + полный список 20
  модулей пакета с привязкой к PR.

## Проверено
Воспроизвёл сценарий пользователя в чистой временной копии из полного
пакетного ZIP: `init_db_cli --with-template`, `etl_pipeline_cli --move-applied
--export`, `cli --appendix-format pdf` — все три отработали без
ModuleNotFoundError.
