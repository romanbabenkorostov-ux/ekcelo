# tests/fixtures/etp — фикстуры для ЭТП-профиля

Read-only фикстура `object_etp_profile_sample.json` — общий контракт между **parser** и **viewer** для разработки ЭТП-экспорта параллельно с миграцией БД.

Согласование зафиксировано в CORRESPONDENCE/025 (parser) и review-ack viewer'а на PR #50 (закрыто постом 026).

## Назначение

- **viewer-team:** read-only данные для рендера карточки объекта в режиме «ЭТП-профиль раздельно» (CORRESPONDENCE/025 §4) с бейджами `source` / `confidence` (§2). Стартует параллельно с миграцией парсера.
- **parser-team:** входные данные для теста миграции DDL (`tests/test_etp_profile_schema.py`) — каждая запись фикстуры должна корректно вставляться/читаться после применения `schema/migrations/0NN_etp_profile.sql`.

## Структура файла

Один JSON-объект с тремя массивами, соответствующими таблицам ADR-001:

| Поле | Таблица | Что внутри |
|---|---|---|
| `object_etp_profile[]` | `object_etp_profile` | По одной записи на КН. JSON-колонки `location_extra`, `building_extra`, `layout`, `legal_extra`, `risks`, `extras` + scalar `source`, `confidence`, `updated_at`. |
| `lots[]` | `lots` | Лот = группа КН. `lot_id` — ASCII `[A-Za-z0-9_:/-]+`, ≤256, шаблон `lot:<project_slug>:<NNN>` (совместимо с `CONTRACT_KMZ §6 graph_node_id` — см. CORRESPONDENCE/026). |
| `lot_items[]` | `lot_items` | Many-to-many лот ↔ КН с `role` (`building`/`land`/`room`/`equipment`/`structure`) и `ord`. |

Поля `$comment`, `$schema_version`, `$generated_at`, `$see_also` — метаданные фикстуры, **не** часть схемы БД (парсер их игнорирует при загрузке, viewer показывает только если хочет).

## Кейсы покрытия

| Кейс | КН | source | confidence | Что демонстрирует |
|---|---|---|---|---|
| **A** | `61:44:0050706:31` (офис) | `osv` | 1.0 | Полный профиль из ОСВ-листа экономиста. Все секции заполнены, без приглушения в viewer. |
| **B** | `61:44:0050706:42` (склад) | `nspd` | 0.65 | Автозаполнение из NSPD. Среднее доверие — viewer показывает бейдж «по данным внешних источников» + тултип. |
| **C** | `61:44:0050706:7` (участок) | `llm` | 0.35 | LLM-suggest, низкое доверие. `building_extra: null` и `layout: null` (нет здания). Viewer должен приглушить текст (CORRESPONDENCE/025 §2 — бонус (c) для `confidence < 0.5`). |

Лоты:
- `lot:pirushin:001` — имущественный комплекс из 2 КН (помещение + участок), процедура банкротства, две платформы.
- `lot:sosna-rocha:042` — одиночный лот, приватизация, одна платформа.

## Контракт совместимости

- **Schema version:** `1.0` (поле `$schema_version`). Bump при breaking-изменениях фикстуры. Аддитивные расширения JSON-колонок — без bump'а.
- **Связь с `CONTRACT_KMZ.md`:** не затрагивает (§3 UI/UX-домен). Wire-формат KMZ 2.12.0 прежний.
- **Связь с `graph_node_id`:** `lots.lot_id` совместим по charset/длине с `CONTRACT_KMZ §6` — позволяет Phase 2 overlay viewer'а переиспользовать S5 group-overlay инфраструктуру (см. CORRESPONDENCE/026 §«Архитектурная заметка»).

## Использование

### viewer
```js
const fixture = await fetch('/parser/tests/fixtures/etp/object_etp_profile_sample.json').then(r => r.json());
for (const profile of fixture.object_etp_profile) {
  renderEtpProfileCard(profile);  // см. CORRESPONDENCE/025 §2/§4
}
```

### parser (после миграции DDL)
```python
import json
import sqlite3
from pathlib import Path

with open(Path("parser/tests/fixtures/etp/object_etp_profile_sample.json")) as f:
    fixture = json.load(f)

conn = sqlite3.connect(":memory:")
conn.executescript(Path("schema/migrations/0NN_etp_profile.sql").read_text())

for prof in fixture["object_etp_profile"]:
    conn.execute(
        "INSERT INTO object_etp_profile(cad_number, location_extra, building_extra, layout, legal_extra, risks, extras, source, confidence, updated_at) "
        "VALUES (?, json(?), json(?), json(?), json(?), json(?), json(?), ?, ?, ?)",
        (prof["cad_number"],
         json.dumps(prof["location_extra"], ensure_ascii=False),
         json.dumps(prof["building_extra"], ensure_ascii=False),
         json.dumps(prof["layout"], ensure_ascii=False),
         json.dumps(prof["legal_extra"], ensure_ascii=False),
         json.dumps(prof["risks"], ensure_ascii=False),
         json.dumps(prof["extras"], ensure_ascii=False),
         prof["source"], prof["confidence"], prof["updated_at"]))

# lots / lot_items аналогично
```

## История

- 2026-05-27 — v1.0 создание. PR-fixture (parser-A) после ratification CORRESPONDENCE/026.
