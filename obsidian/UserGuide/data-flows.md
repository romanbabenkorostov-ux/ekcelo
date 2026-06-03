# Потоки данных: от ввода до отражения в viewer

> Цель: пользователь должен **мысленно воспроизвести** путь данных от ввода (в любой последовательности) до появления в viewer. Каждый источник данных — отдельный «приток»; viewer — устье.

## Карта притоков

```
                    ┌──────────────── SQLite (ekcelo.sqlite) ───────────────┐
ЕГРН-выписки  ─1─►  │ objects / rights / entity_registry                    │
OSV YAML      ─2─►  │ object_etp_profile / lots / lot_items                 │
NSPD JSON     ─3─►  │   (gap-fill: osv/manual > nspd/exif/checko)           │
EXIF фото     ─4─►  │                                                       │
checko innogrn─5─►  │                                                       │
                    └────────────────────────┬──────────────────────────────┘
                                              │
                          ┌───────────────────┴───────────────────┐
                          ▼                                        ▼
              export_json_cli → object_etp_profile.json      cli (Stage 3) →
              (для viewer ЭТП-блока)                          out/etp/<lot>/*.txt + lot_appendix.md
                          │                                        │
                          │                          08_build_kmz → <project>.kmz
                          ▼                                        ▼
              ┌─────────────────────────── viewer/index.html ──────────────────────┐
              │  • KMZ-загрузчик → карта + карточки                                  │
              │  • ЭТП-профиль (фикстура ИЛИ экспорт) → бейджи source/confidence     │
              └─────────────────────────────────────────────────────────────────────┘
```

## Ключевой принцип: порядок ввода НЕ важен (кроме одного правила)

Притоки 2-5 — **идемпотентный gap-fill** в `object_etp_profile`. Можно вводить в любой последовательности; повторный ввод не ломает. Единственное жёсткое правило:

> **Приток 1 (ЕГРН) должен быть первым** — он создаёт строки в `objects` и `rights`. Притоки 2-5 ссылаются на `cad_number` через FK; без объекта будет `FOREIGN KEY constraint failed`.

Приоритет при конфликте (кто кого перекрывает): `manual` > `osv` > `nspd` > `exif` > `checko` > `llm`. Более авторитетный источник НЕ перезатирается менее авторитетным.

## Приток 1 — ЕГРН-выписки (обязательный, первый)

```powershell
egrn-parser migrate --db .\ekcelo.sqlite
egrn-parser dict-load --db .\ekcelo.sqlite
egrn-parser parse --input .\Выписки_PDF\ --db .\ekcelo.sqlite
python -m parser.exporters.etp.init_db_cli --db .\ekcelo.sqlite   # ЭТП-слой (один раз)
```

Что появилось: `objects`, `rights`, `entity_registry`, `object_etp_profile/lots/lot_items` (пустые).

## Приток 2 — OSV survey-лист экономиста

```powershell
python -m parser.exporters.etp.etl_osv_cli --yaml .\inbox\2026-06-01-pirushin.yml --db .\ekcelo.sqlite
```

Что появилось: `object_etp_profile` обогащено отделкой/инженеркой/рисками (`source=osv`), `lots`/`lot_items` заполнены.

## Приток 3 — NSPD (опц.)

```powershell
python -m parser.exporters.etp.nspd_enrich_cli --db .\ekcelo.sqlite --nspd-dir .\nspd_cache\
```

Заполняет `building_type`, `year_built`, `use_type_permitted` — **только пустые** поля (`source=nspd`, не трогает osv/manual).

## Приток 4 — EXIF фото (опц.)

```powershell
python -m parser.exporters.etp.etl_exif_cli --db .\ekcelo.sqlite --photos .\Фотографии\
```

Сводит категории фото в `extras.advantages[]`. (Per-photo `note` → `extras.notes` появится в EXIF v1.2, см. CORRESPONDENCE 027/028.)

## Приток 5 — checko (opt-in)

```powershell
python -m parser.exporters.etp.etl_checko --db .\ekcelo.sqlite --innogrn-db D:\checko\innogrn.db --lot lot:pirushin:001
```

Добавляет `legal_extra.owner_checko` (статус юрлица, ОКВЭД, уставный капитал). Только если есть `innogrn.db`; нет → no-op.

## Устье A — viewer показывает ЭТП-профиль

Два режима подачи данных в viewer:

### A1. Фикстура (Phase 1, по умолчанию)

viewer читает `parser/tests/fixtures/etp/object_etp_profile_sample.json`. Это **демо-данные**, не ваши. Показывает, как выглядят бейджи source/confidence.

Чтобы фикстура загрузилась:
- Раздача из корня репо (`python -m http.server` в корне) → viewer пробует `parser/...` (404) затем `../parser/...` (200). **Работает автоматически.**
- Открыли `/viewer/index.html` и видите в DevTools 404 на `/viewer/parser/...` — это нормально, следом успешный `../parser/...`.

### A2. Экспорт из вашей БД (production)

```powershell
python -m parser.exporters.etp.export_json_cli --db .\ekcelo.sqlite
# → parser/exports/etp/object_etp_profile.json
```

Чтобы viewer показал **ваши** данные вместо демо — замените фикстуру экспортом (скопируйте `object_etp_profile.json` на место фикстуры) ИЛИ дождитесь привязки viewer к экспорту (формат идентичен, см. комментарий в `viewer/index.html::loadEtpFixture`).

## Устье B — viewer показывает KMZ (карта + объекты)

KMZ собирается отдельной веткой пайплайна (не через `object_etp_profile`):

```powershell
python parser\scripts\pirushin_sosn_rocha_07_init_project_v3.py
python parser\scripts\pirushin_sosn_rocha_052_make_structure_v2_2.py
python parser\scripts\pirushin_sosn_rocha_08_build_kmz_v2_2.py   # → <project>.kmz
```

Затем в viewer: UI «Загрузить KMZ» → выбрать `.kmz`. Карта рисует объекты; клик по объекту → карточка. Если для `cad_number` объекта есть ЭТП-профиль (из устья A) — карточка дополняется блоком «— ЕГРН —» с бейджем.

## Сценарии «в разной последовательности» (mental-reproduce)

### Сценарий 1: минимальный (только ЕГРН → KMZ)

1 → 07 → 052 → 08 → загрузить KMZ. Viewer показывает объекты на карте, **без** ЭТП-блока (профиль пуст).

### Сценарий 2: ЭТП-карточка без KMZ

1 → 2 → export_json → раздать viewer из корня. Viewer показывает ЭТП-профиль из вашего экспорта (если заменили фикстуру), без карты KMZ.

### Сценарий 3: полный, фото раньше OSV

1 → 4 (EXIF) → 2 (OSV) → 3 (NSPD) → 5 (checko) → export_json + 08. Порядок 4→2 безопасен: EXIF создаёт `extras.advantages`, OSV дополняет `building_extra/layout/risks` — разные поля, не конфликтуют. Если бы OSV и EXIF писали одно поле — выиграл бы OSV (выше приоритет).

### Сценарий 4: checko первым (ошибка)

5 → 1 → … Приток 5 на пустой БД: `lot_items` пуст → `enrich_lot_from_checko` вернёт empty report (нет КН лота). Не падает, но и не обогащает. Сначала 1 и 2.

### Сценарий 5: повторный прогон (идемпотентность)

Любой из 2-5 запущен дважды → второй раз no-op для уже заполненных полей (`skipped_reason`). Безопасно.

## Проверка «дошло до viewer»

| Что проверить | Как |
|---|---|
| Объект на карте | Загрузить KMZ → объект виден, клик → карточка |
| ЭТП-профиль | Карточка объекта содержит блок «— ЕГРН —» + бейдж |
| source/confidence | Цвет бейджа: зелёный=osv/manual, жёлтый=nspd/exif, оранжевый=низкая уверенность |
| owner_checko | В карточке (если шаблон отображает) или в `legal_extra` экспортированного JSON |

## Troubleshooting потоков

| Симптом | Причина | Фикс |
|---|---|---|
| `FOREIGN KEY constraint failed` | приток 2-5 раньше притока 1 | сначала `egrn-parser parse` + `init_db_cli` |
| Viewer не показывает ЭТП-блок | фикстура не загрузилась / профиль пуст | DevTools Network: должен быть 200 на `../parser/.../sample.json`; проверьте `object_etp_profile` непуст |
| Viewer показывает чужие (демо) данные | загружена фикстура, не ваш экспорт | замените фикстуру на свой `export_json_cli` вывод |
| checko ничего не обогатил | INN не в innogrn / нет right_holder | проверьте `rights.right_holder_inn` и `subjects` в innogrn.db |
| 404 `/viewer/parser/...` в логе | ожидаемо (первая попытка пути) | игнорировать — следом `../parser/...` 200 |

## Связи

- Полный пошаговый путь: [[golden-path]].
- Импорт OSV: [[etp-osv-import]]. checko: [[etp-checko]]. Карточки: [[etp-export]].
- Программистский аналог: `obsidian/Architecture/mechanisms-for-maintainers.md`.
