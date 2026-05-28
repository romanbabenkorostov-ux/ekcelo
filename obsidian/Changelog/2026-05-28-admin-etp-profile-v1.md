# 2026-05-28 — admin/etp-profile/ v1 (генератор YAML)

## Суть

`viewer/admin-etp-profile.html` — мини-UI редактирования полей
`object_etp_profile` под ack п.1 в CORRESPONDENCE/026 (вариант b).

Генерирует YAML survey-лист по контракту
`obsidian/Architecture/etl-osv.md` без обращения к серверу.
Pipeline для экономиста:

```
UI → скачать .yml → положить в parser/inbox/etp/<YYYY-MM-DD>-<slug>.yml
   → parser-A прогоняет etl_osv_cli + export_json_cli
   → новый parser/exports/etp/object_etp_profile.json коммитится в репо
   → UI и Phase 1 viewer подхватывают при следующем заходе.
```

## Архитектурные решения

- **Stateless / static.** Viewer остаётся GitHub Pages-статикой. Никакого
  REST endpoint'а на parser-стороне (явно отказались в письме).
- **Источник baseline — JSON-экспорт** `parser/exports/etp/object_etp_profile.json`
  (Stage 4b parser-A, PR #64) с fallback на фикстуру при 404.
- **UI редактирует только `profiles[]`.** `lots`/`lot_items` идут через
  прямой YAML по решению ack п.3 (Phase 1 back-only).
- **`source`/`confidence` на уровне профиля** (default `manual`/`1.0`).
  Per-field override не сделан — добавим, если будет реальный запрос.
- **Список полей зашит в JS-константу `SECTIONS`** по контракту
  etl-osv.md. Forward-compat: парсер игнорирует неизвестные ключи,
  поэтому расширение схемы не ломает старые YAML; добавление новых
  полей в UI — правка одной константы.
- **YAML-генератор написан вручную** (~40 строк JS). Без зависимостей.
  Все строки — double-quoted с escape `\`, `"`, `\n`, `\r`, `\t`.
  Пустые секции опускаются (NULL в БД).

## Защита

Минимальная: `<meta name="robots" content="noindex">`. Доступ по
прямому URL `…/viewer/admin-etp-profile.html`. В контексте задачи —
этого достаточно: GitHub Pages статичен, а write-канал (drop в
`parser/inbox/etp/`) требует merge в репо, что сам по себе является
точкой контроля.

## Тестирование

Прогнаны вручную:

1. **JS syntax** — `node --check` на извлечённом inline-скрипте → OK.
2. **YAML-генератор smoke (5 кейсов)** — пустой профиль (warning),
   только cad (header без секций), полный профиль из фикстуры
   (все 6 секций, кириллица сохранена), escaping кавычек и `\n`,
   массивы + nested engineering. Все 5 passed.
3. **E2E**: UI buildYaml() → файл → `parser.exporters.etp.etl_osv.load_osv()`.
   Все поля baseline-фикстуры сохранены 1-в-1 (включая кириллицу
   `«Тверская»`, ceiling_height_m=3.1, engineering nested object,
   amenities array).

## Открытые вопросы

- Если parser-A потребует per-field `source` override — добавить
  ещё одну колонку в каждом поле формы (TODO в коде).
- Если экономист попросит редактировать `lots[]` через UI — расширим
  в v2. Сейчас лоты редактируются прямым YAML.
- `viewer/index.html` НЕ ссылается на admin-страницу (изоляция по
  ack 026). Доступ — через закладку / прямой URL.

## Контракт с parser-A

UI генерирует YAML по `obsidian/Architecture/etl-osv.md` (PR #62, immutable).
Любое breaking-изменение контракта (новые required поля, переименование
enum'ов) — отдельный correspondence-цикл.
