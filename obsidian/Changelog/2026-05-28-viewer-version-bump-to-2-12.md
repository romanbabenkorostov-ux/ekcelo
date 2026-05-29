# 2026-05-28 — viewer title version bump v2.10.0 → v2.12.0

## Итог
Виewer показывал `v2.10.0` в title, хотя контент полностью соответствует CONTRACT_KMZ 2.12.0 (PR #16 + #31). Title и `sw.js` синхронизированы с актуальной версией контракта.

## Артефакты
- `viewer/index.html` — title: `EkceloFoto v2.12.0`.
- `viewer/sw.js` — заголовок: `sw.js v2.12.0`.
- `obsidian/Architecture/viewer-version-and-tabs-investigation.md` — расследование по репорту «вкладка Метки отсутствует».

## Что выяснили

**Title старый.** Был неизменным с момента релокации viewer в `viewer/` (commit `55aca1a`). PR'ы #16 (2.11.0) и #31 (2.12.0) добавили функциональность, но не bump'нули title.

**Вкладка «Метки» в коде есть.** `viewer/index.html:1265`:
```html
<button class="sb-tab" data-tab="marks" onclick="switchSidebarTab('marks')">🏷 Метки</button>
```

Добавлена в S5 PR-C (commit `90a0799`). Если пользователь её не видит — это **кэш браузера** (старый HTML до этого PR).

**SW не виноват.** `sw.js` кэширует только запросы к `nspd.gov.ru` (см. `CACHE_HOST`), а не сам viewer HTML/JS.

## Рекомендация пользователю

`Ctrl + Shift + R` (hard reload) — после этого вкладка «Метки» появится, title покажет `v2.12.0`.

## Связи
- `viewer/index.html`, `viewer/sw.js`.
- `docs/CONTRACT_KMZ.md` — version 2.12.0.
- S5 PR #16 (2.11.0), PR-θ #31 (2.12.0).
