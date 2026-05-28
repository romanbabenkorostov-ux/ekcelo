# 2026-05-28 — ETP Stage 5/6 поля в viewer + admin-UI

После мерджа PR #65 (Stage 5 NSPD-enrichment) и PR #67 (Stage 6 ETL EXIF)
парсер добавляет в JSON-секции `object_etp_profile` новые поля:

- `building_extra.building_type` (материал стен, нормализован: «кирпич» → «кирпичное»)
- `building_extra.year_built` (год постройки)
- `legal_extra.use_type_permitted` (разрешённое использование, строка через «; »)
- `extras.advantages[]` — теперь дополняется автоматически Stage 6 EXIF.

Parser-A написал «`_renderEtpBlock` подхватит автоматически», но это неверно —
Phase 1 рендер использует жёсткий список полей. Поэтому два маленьких
расширения:

## viewer/index.html — `_renderEtpBlock`

Добавлены 2 строки:

- `building_extra`: новая отдельная строка «Конструкция» (`building_type`
  + «постройка `<year_built>`»). Сохранена существующая строка «Здание»
  (`wear_degree` + ремонт) — семантически это другое.
- `legal_extra`: новая строка «Разрешённое использование» (`use_type_permitted`).

`extras.advantages[]` уже рендерилось — Stage 6 EXIF подхватится без правок.

## viewer/admin-etp-profile.html — `SECTIONS`

Добавлены поля в forms для редактирования экономистом (чтобы можно было
вручную override автоматическое NSPD-значение через `source=manual`):

- `building_extra.building_type` (str)
- `building_extra.year_built` (int)
- `legal_extra.use_type_permitted` (str)

## Тесты

- `node --check` inline JS admin-UI → OK.
- YAML-generator smoke 5/5 (без регрессий).
- E2E с новыми полями: UI buildYaml → load_osv → все 3 новых поля
  сохраняются 1-в-1.
- viewer/index.html — визуально grep'нуто, рендер-код в правильном месте.

## Контракт

Контракт `etl-osv.md` parser-A не тронут (forward-compat: парсер
игнорирует неизвестные ключи; новые ключи внутри существующих секций
не требуют schema bump'а — §«Расширение / совместимость»).
