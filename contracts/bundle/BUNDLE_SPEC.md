# C3 — Bundle (каноническая единица экспорта-импорта)

> Единица обмена данными по **объекту** и по **лоту** между локальным
> парсером (Win10) и веб-бэкендом. Идемпотентна: повторная сборка на тех же
> входах даёт побайтово те же файлы.

## Состав каталога Bundle

```
<bundle_root>/
├── manifest.json          # обязателен — реестр содержимого + версии контрактов
├── project.kmz            # C1 wire 2.12.0 (для скачивания / Google Earth / локального вьюера)
├── db.sqlite              # C2, §1–§6 (слепок ЕГРН + ЭТП-профиль)
├── json/
│   ├── structure_<TS>.json    # parser-internal иерархия (выход 052)
│   ├── enriched_<TS>.json      # parser-internal свод (выход 03_enrich v17)
│   └── objects/<cad>.json      # паспорт объекта (выход 07)
└── raw/                   # ОПЦИОНАЛЬНО, по запросу: исходные PDF/XML/DOCX/XLSX/JPG/KML
```

- `manifest.json`, `project.kmz`, `db.sqlite` — **обязательны**.
- `json/` — обязателен (нормализованные промежуточные данные; помечены
  `parser-internal`, формат вне C1, см. `CONTRACT_KMZ.md` §2).
- `raw/` — опционально (выдаётся по явному запросу заказчика: «полная папка с
  raw документами и фотографиями»).

## manifest.json (нормативно)

Минимальные поля (полная JSON Schema — `bundle.schema.json`):

```json
{
  "bundle_version": "1.0.0",
  "contracts_version": "1.0.0",
  "kmz_contract_version": "2.12.0",
  "kind": "object | lot",
  "lot": {                         // присутствует если kind=lot (см. C5)
    "lot_id": "…",
    "as_of_date": "YYYY-MM-DD",
    "include": {…}, "exclude": {…},
    "members": ["<cad>", "…"]
  },
  "primary_cad_number": "61:44:0050706:31",
  "extract_date": "YYYY-MM-DD",    // true source-of-truth даты выписки (= C1 extract_date)
  "objects": ["<cad>", "…"],
  "files": [
    { "path": "project.kmz", "sha256": "…", "bytes": 12345 },
    { "path": "db.sqlite",   "sha256": "…", "bytes": 4096 }
  ],
  "etp_layer_present": true,       // §6 — ручной слой, при пересоздании БД не восстанавливается (ADR-001)
  "generated_by": "egrn-parser / golden-path",
  "generated_at": "ISO-8601"
}
```

## Идемпотентность

- Каждая запись в `files[]` несёт `sha256`. Round-trip
  `export → import → export` обязан давать те же `sha256` для `project.kmz` и
  стабильный набор id в `db.sqlite`/`structure.json`.
- Реализация хешей переиспользует `parser/egrn_parser/merge/content_hash.py`.

## Граница ответственности

- `project.kmz` — под контрактом C1 (менять только через `CONTRACT_KMZ.md` §3).
- `db.sqlite` — под контрактом C2 (§1–§6).
- `json/` — parser-internal: парсер меняет свободно, но manifest фиксирует хеши.
- `manifest.json` — под этим контрактом C3.
