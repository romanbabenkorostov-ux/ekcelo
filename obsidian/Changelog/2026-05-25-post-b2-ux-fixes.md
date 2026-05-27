# 2026-05-25 — viewer: post-B2 UX fixes (defensive + marks + GPS panel)

**Что:** 4 точечных UX-улучшения после smoke-теста B2. §3 UI/UX, viewer-домен, контракт KMZ не затронут.

## A. Refactor defensive EXIF write (для stub-JPG)

В `writeEXIFWithGPS()` ранее (PR #40) на невалидном JPG (size<512 / нет FFD8) показывался блокирующий `❌ toast` и пользователь не мог изменить координаты вообще. Теперь — **quiet in-memory update**: координаты/угол обновляются в `photos[i]`, маркер перерисовывается, GPS-режим закрывается, выводится info-toast «Координаты обновлены в сеансе (EXIF не записан — stub-файл без валидного JPEG)». Запись в файл не происходит — это корректно для synthetic stub'ов; смысл — не блокировать UX для preview-сценариев.

## B. Hide empty marks-groups

В `renderMarksList()` пустые категории (`buckets[grp].length === 0`) ранее показывались как «Нет: ...» placeholder в раскрытом виде — занимали место. Теперь весь блок `<div id="marks-group-{grp}">` скрывается (`display:none`) пока в нём не появится хотя бы один маркер. Применяется ко всем 9 категориям (ЗЕМ.УЧАСТКИ, ОКС, ПОМЕЩЕНИЯ, СООРУЖЕНИЯ, ОНС, БИЗНЕС-ЕД., ОБОРУД., БЕНЕФИЦИАРЫ, ПОЯСНЕНИЯ). При загрузке KMZ только реально присутствующие категории видны; при создании нового маркера в сессии — категория автоматически появляется.

## C. Rename + raise z-index панели GPS

- Title: «📍 Ручной GPS» → «📍 Изменение геопривязки». В режиме edit: «📍 Изменение геопривязки — {filename}».
- `z-index`: 800 → 3100 (выше lightbox 2000). Раньше панель могла скрываться за lightbox'ом — теперь всегда сверху.

## D. Drag «Изменение геопривязки» по title-bar

Новая IIFE `initGPSPanelDrag` (по образцу `initLightboxDrag`):
- Handle: `#mgps-title` (cursor: move в CSS).
- При первом drag-start: переход с bottom/right якорей на left/top (через `dataset.draggedOnce`), чтобы корректно следовать курсору.
- Bounding по `#map-wrap` (как у lightbox).
- mousedown/mousemove/mouseup на document.

## Что не вошло (отложено)

- **Resizable «Структура объекта»** (drag-handle splitter для `#folder-tree-content max-height:200px`) — отдельный PR (нужен полноценный resizer + persist).
- **Compact + resizable marks-categories** (drag-handles между группами) — отдельный PR.
- **Lightbox card draggable в gps-active** — уже работает через `initLightboxDrag` по `#lb-filename-bar`, верифицировал в коде.
- **NSPD CORS на file://** — environmental: открыть `viewer/index.html` через `file://` блокирует CORS (Browser security). Решение — локальный HTTP-сервер (`python3 -m http.server 8000` в `viewer/`) или CDN-хостинг. Это **не код-баг**, не фиксится в viewer'е.

## Инварианты

- `node --check` чист (503347 chars; +2382 vs PR #40 baseline 500965).
- Валидные JPG (drag-drop / Yandex / GDrive / KMZ с реальным EXIF) — write-cycle работает как раньше.
- Stub-JPG → координаты обновляются в-памяти, EXIF не записан, info-toast.
- Пустые marks-категории скрыты, при появлении хоть одного маркера — категория автоматически возникает.
- GPS panel рендерится поверх lightbox (z-index 3100 > 2000), draggable.
- Контракт KMZ 2.12.0 не затронут.

## Файлы

- `viewer/index.html` — +70/−12 строк (5 точечных правок).

**Ветка:** `viewer/post-b2-ux-fixes-v2`.
