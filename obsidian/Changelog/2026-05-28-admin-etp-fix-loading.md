# 2026-05-28 — admin/etp-profile/ v1: hotfix загрузки baseline

## Итог
Минимальный фикс PR #66 (`viewer/admin-etp-profile.html`). На дев-сервере, запущенном из `viewer/`, UI не мог fetch'ить `../parser/exports/...` — Python `http.server` блокирует traversal вверх по дереву.

## Изменения

- `viewer/admin-etp-profile.html`:
  - В `EXPORT_PATHS` добавлены absolute-fallback'и (`/parser/...`) для нестандартных deploy-схем.
  - Сообщение об ошибке заменено на инструкцию: список перепробованных путей + готовая команда `cd <repo>; python -m http.server 8000` с динамическим линком на нужный КН.

## Почему не меняется поведение в продакшене

- При запуске сервера из корня репо (рекомендованный сценарий) первая запись `../parser/exports/...` отрабатывает как раньше — без изменений.
- GitHub Pages обслуживает весь репо целиком, относительный `../parser/...` тоже работает.
- Изменения только в сообщении при ошибке + аддитивные fallback'и.

## Подсказка пользователю

Корректная команда запуска (Win10 / PowerShell):

```powershell
cd E:\Code\ekcelo\code
python -m http.server 8000
# URL: http://localhost:8000/viewer/admin-etp-profile.html?cad=61:44:0050706:31
```

## Связи
- PR #66 (admin/etp-profile/ v1, merged).
- `obsidian/Architecture/etl-osv.md` — контракт не затрагивается.
