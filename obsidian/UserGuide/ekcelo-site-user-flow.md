---
type: userguide
status: active
date: 2026-06-03
scope: ekcelo.ru
---

# ekcelo.ru: user-flow от ссылки до данных во viewer'е

> **Контекст.** Этот документ — пошаговая ментальная модель того, что видит и
> делает обычный пользователь на `ekcelo.ru` (виджет + viewer). Цель —
> воспроизводимость: прочитав документ, можно пройти любой сценарий из головы,
> предсказать, что должно случиться на каждом шаге, и поймать регрессию.

## 0. Карта ссылок

| URL | Что показывает | Кто пускает |
|---|---|---|
| `https://ekcelo.ru/` | Лендинг scrollytelling | Все |
| `https://ekcelo.ru/viewer/` | Viewer без проекта (пустая карта) | Все |
| `https://ekcelo.ru/viewer/?t=<токен>` | Viewer с проектом | Все (токен решает режим) |
| `https://ekcelo.ru/viewer/?t=<токен>&mode=pro` | Viewer с проектом, режим pro | Все (но нужен пароль) |
| `https://ekcelo.ru/viewer/?t=<токен>&mode=embed` | Viewer без хрома (для iframe) | Все |
| `https://ekcelo.ru/admin-encode.html` | Генератор токенов + QR | Все (по факту — владелец) |

## 1. Лендинг (`/`) — сценарий «оставить заявку»

### Что грузится

1. `index.html` (HTML + SEO `<head>` + scrollytelling DOM).
2. `<script defer src="tokens.js">` — определяет `window.Ekcelo` (encode/decode/resolveToViewer).
3. `<script type="module" src="app.js">` — модуль-контроллер лендинга (с PR #7).

Порядок гарантирован: defer-классика и module — оба после парсинга HTML, в HTML-порядке.
`app.js` исполняется ПОСЛЕ `tokens.js` → `window.Ekcelo` уже определён к моменту первого
обращения к нему.

### Что видит пользователь

1. Header sticky (логотип + поле токена + «Связаться»).
2. Фрейм 1 ("пустой участок") + neon-сетка.
3. **Скролл** ↓:
   - 5 фаз crossfade'ятся в порядке: пустой участок → коммуникации → стройка → готовый дом → финал с табличкой ekcelo.
   - На каждой фазе одни SVG-линии загораются (`.lit`), другие гаснут.
   - Документ-карточки (выписки ЕГРН и пр.) появляются на соответствующей фазе.
4. **5-я попытка скролла вниз на самом низу** → выезжает контакт-модалка.
5. Кнопка «Связаться» → та же модалка открывается мгновенно.

### Что делает скролл (механика)

`progress` (0..1) считается по тому, насколько проскроллена вся страница. На основе progress:
- `frameLerp(progress, FRAME_STOPS)` → дробный индекс фрейма [0..4]; opacity 5 PNG-фреймов
  считается как линейный кросс-фейд между соседями.
- `getPhase(progress)` → целая фаза [0..6] (intro, 5 фаз, final).
- `updatePhase(phase, progress)` → подсвечивает/гасит линии и карточки.

### Контакт-модалка

- Список партнёров читается из inline `<script type="text/csv" id="partners-data">`
  (для open-from-file://), резервно — `fetch('partners.csv')` (для HTTP).
- `parseCSV(text)` (core/) → массив `{name, phone, email, city, contact, site}`.
- `renderPartners(rows)` строит DOM-список с кнопками copy / vCard.
- Клик «Скопировать» → `navigator.clipboard.writeText` → toast «Скопировано».
- Клик «Скачать контакт» → `buildVCard(row)` (core/) → `.vcf` blob → автоскачивание.
  Имя файла транслитерируется через `asciiSlug(name)` (core/) для iOS-совместимости.

### Токен-инпут (вход во viewer)

Поле в header / контакт-модалке. Пользователь вставляет либо:
- сырой токен (base64url),
- ссылку `https://ekcelo.ru/?t=…`,
- полный «исходный» URL проекта (Я.Диск/GDrive/…) — `tokens.js` его сам закодирует.

Что происходит: `window.Ekcelo.resolveToViewer(input, VIEWER_BASE)` → `{token, target, viewerUrl, param}`.
Если резолв успешный — `location.assign(viewerUrl)` (прямой переход, **не** iframe).
В адресной строке появится `ekcelo.ru/viewer/?t=<токен>` или `?t=…&photo=…&kmz=…` —
**но не** сырая Я.Диск-ссылка.

## 2. Viewer (`viewer/`) — сценарий «открыть проект»

### Грузится

1. CDN-библиотеки в `<head>`: piexifjs, xlsx-js-style, jszip (классические скрипты).
2. `viewer/index.html` (12k строк inline-JS, классический `<script>`).
3. Leaflet + exifr в середине `<head>`.
4. **В конце `<body>`:** `<script type="module" src="./ui/bridge.js">` — регистрирует
   на `window` все pure-функции из `viewer/core/*`.
5. Service Worker `viewer/sw.js` — кэширует только NSPD-тайлы (cadastre).

### Что видит пользователь

#### Открытие без токена (`/viewer/`)
- Карта Leaflet, центр Москвы, базовый слой OSM.
- Заголовок `EkceloFoto v2.X.Y`.
- Sidebar: вкладки «📸 Фото» (пусто), «🏷 Метки» (пусто), «🕸 Граф» (скрыт).
- Кнопка «☰ Загрузить» (visible only в `pro`).
- Кнопка «□ Кадастр ▾» (всегда).

#### Открытие с токеном (`/viewer/?t=<токен>`)
- Токен декодируется через `Ekcelo.decode(t)` → исходный URL.
- В зависимости от типа URL:
  - **KMZ** → автозагрузка KMZ-файла, parse через JSZip, рендер маркеров/контуров,
    sidebar заполняется.
  - **Фото-папка Я.Диск** → загрузка изображений через worker-прокси, EXIF читается,
    маркеры на карте по GPS.
  - **Прямая ссылка на src/photo/kmz/exifLib** — соответствующий handler.

#### Smoke-минимум

| Шаг | Ожидание |
|---|---|
| Открыть `/viewer/?t=<тест>` | Карта рендерится, тайлы не белые, sidebar заполнен |
| Включить «Кадастр» | NSPD-слой накладывается, появляются границы участков |
| Импортировать KMZ (drag-and-drop) | Точки/полигоны появляются на карте |
| Клик на маркер | Popup открывается, если есть фото — отображается, EXIF читается |
| В `view`: кнопки экспорта | СКРЫТЫ |
| Переключить в `pro` (невидимая зона справа от лого + пароль `редактировать`) | Появляются «Экспорт KMZ», «Экспорт XLSX», «Загрузить» |
| Экспорт KMZ | Скачивается файл, открывается обратно во viewer без ошибок |
| Экспорт XLSX | Файл со стилями строк 1/2/3 (заголовок/подзаголовок/данные) |
| Запись EXIF (в `pro`) | Добавить заметку к фото → перезагрузить → заметка видна |
| Линейка | Измеряет расстояние «N м» или «N.NN км» (формат через `rulerFormatDist`) |
| DevTools Console | Нет ошибок (warnings можно) |

### Режимы (role-state)

Что определяет роль (порядок проверки):

1. URL `?mode=pro` / `?mode=view` / `?mode=embed` — выигрывает.
2. `localStorage['ekcelo_role'] === 'pro'` — если URL не указал.
3. Дефолт — `ROLE_CFG.DEFAULT_ROLE` = `'view'`.

В `embed` role — отключаются все picker'ы (showDirectoryPicker и др.), скрывается chrome.
В `pro` role — открыт экспорт, редактирование EXIF, добавление маркеров. Защита `pro` —
sha256 пароля `редактировать` (`PRO_PASS_SHA256`, hardcoded). Не криптостойкая —
**мягкое гейтирование UI**.

### Что разрешено в каждом режиме

| UI / действие | view | pro | embed |
|---|---|---|---|
| Открыть проект по токену | ✅ | ✅ | ✅ (без chrome) |
| Включить/выключить NSPD-слой | ✅ | ✅ | ✅ |
| Импорт KMZ (drag-and-drop) | ❌ | ✅ | ❌ |
| Экспорт KMZ | ❌ | ✅ | ❌ |
| Экспорт XLSX | ❌ | ✅ | ❌ |
| Запись EXIF | ❌ | ✅ | ❌ |
| File System Access API | ❌ | ✅ | ❌ |

### Кэширование NSPD

`viewer/sw.js` (service worker) перехватывает запросы к `https://nspd.gov.ru/*` и
кладёт ответы в Cache Storage. При повторном включении кадастра — мгновенная отрисовка
из кэша.

«□ Кадастр ▾» dropdown показывает счётчик закэшированных тайлов; клик на счётчик →
очистить кэш.

## 3. Admin-encode (`admin-encode.html`) — сценарий «выдать ссылку клиенту»

### Кто пользуется
Владелец (Роман). Гостям отдаём готовую короткую ссылку, не admin-encode.

### Грузится (с PR #8)

1. Inline `<script>` с vendored `qrcode-generator` lib (третий-сторонний код).
2. `<script src="tokens.js">` — `window.Ekcelo`.
3. `<script type="module" src="ui/admin-encode.js">` — модуль UI.

Порядок: classic → classic → module. Модуль грузится отложенно → `window.qrcode` и
`window.Ekcelo` уже доступны.

### Поток

1. Вставить исходный URL проекта (Я.Диск-папка с фото / прямая KMZ-ссылка / любой http(s) URL).
2. Кнопка **«Закодировать»** (`run`):
   - `Ekcelo.encode(url)` → токен (base64url).
   - `Ekcelo.buildShortUrl(url, base)` → длинная ссылка `ekcelo.ru/?t=<токен>`.
   - 2 QR-кода: один для токена, один для длинной ссылки. Каждый — JPG (canvas, белый
     фон, 256-модульный код).
3. Кнопка **«Укоротить через clck.ru»** (`runShorten`):
   - Cloudflare Worker (`ekcelo-proxy.…workers.dev`) проксирует запрос к `clck.ru/--?url=…`
     (clck.ru CORS-захлёб обходим через worker).
   - Результат — короткая ссылка `https://clck.ru/XXXXX` (1 редирект → длинная →
     откроется во viewer).
   - 3-й QR (clck) рисуется.
4. Кнопки copy / download — копируют токен/ссылку в буфер, скачивают QR как JPG.

## 4. Cross-cutting concerns

### 4.1 Тёмная / светлая тема

Темы переключаются классом на `<html>`. CSS-переменная `--map-bg` отличается:
светлая тема использует `#f2efe9` (тёплый бежевый), тёмная — почти чёрный. Tile-seam
fix (см. Architecture/ekcelo-site-decomposition §7) учитывает обе.

### 4.2 SEO / Schema.org

Лендинг `<head>` содержит OG / Twitter / Schema.org JSON-LD. **Не трогается** ни одной
декомпозицией. То же относится к `CNAME`, `robots.txt`, `sitemap.xml`, `yandex_*.html`.

### 4.3 PWA / install-prompt

Сейчас отсутствует. Service Worker есть только во viewer'е и только для кэширования
NSPD. install-prompt лендинга не реализован.

## 5. Что должно случиться в каждом браузере

| Браузер | OSM-тайлы | NSPD-тайлы | KMZ-import | EXIF | XLSX-export | File System Access |
|---|---|---|---|---|---|---|
| Chrome (новый) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| Edge (новый) | ✅ | ✅ | ✅ | ✅ | ✅ | ✅ |
| YaBrowser (новый) | ✅ (без белой сетки после PR #12 / v2.9.62c) | ✅ | ✅ | ✅ | ✅ | ✅ |
| YaBrowser (старый) | ✅ (`tile-seam-fallback` без plus-lighter) | ✅ | ✅ | ✅ | ✅ | ✅ |
| Firefox | ✅ | ✅ | ✅ | ✅ | ✅ | ⚠ (Save As fallback) |
| Safari | ⚠ (требуется отдельная проверка после фазы 3) | ⚠ | ⚠ | ⚠ | ⚠ | ❌ |

## 6. Что **не должно** случиться (sanity checks)

- В адресной строке viewer'а **никогда** не появляется сырая Я.Диск-ссылка
  (`disk.yandex.ru/...`). Токен — единственный публичный идентификатор проекта.
- В `view` режиме **не показывается** ни одна кнопка экспорта.
- В режимах `view`/`embed` `localStorage['ekcelo_role']` **не должен** становиться `'pro'`
  без явного ввода пароля.
- Service Worker **не кэширует** сам `viewer/index.html` / `app.js` / `tokens.js` — только
  `nspd.gov.ru/*` тайлы. Это значит обновление сайта = `Ctrl+F5` (hard reload) у пользователя.

## 7. Связанные документы

- `obsidian/Architecture/ekcelo-site-decomposition.md` — devops/repair-уровень
  (механизмы внутри).
- `obsidian/CONTRACT_KMZ.md` — формат KMZ-файлов, которые viewer понимает.
- `obsidian/Changelog/2026-06-03-ekcelo-site-decomposition.md` — журнал текущей сессии.
- `ekcelo-site/docs/VERIFICATION_PROTOCOL.md` (reference-ветка
  `claude/site-decomposition-handoff`) — полный smoke-чеклист для прода.
