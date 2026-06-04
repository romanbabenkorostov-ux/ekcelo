# 2026-06-04 — Сведённое описание системы EKCELO (под C2-схему)

## Суть
Черновик-эссе (5 точек зрения: экономист/юрист, архитектор, технолог, консультант,
спец по БД) сведён в один непротиворечивый документ, дубли убраны, формулировки
приведены к утверждённой схеме C2.

## Сделано
- `obsidian/Architecture/ekcelo-system-description.md` — 12 разделов + Приложение A
  (12 корректировок относительно черновика).

## Ключевые корректировки (Приложение A документа)
- Субъект: типы = INDIVIDUAL/LEGAL_ENTITY/INDIVIDUAL_ENTREPRENEUR/STATE_BODY;
  бенефициар/асесор/админ — роли (C6), не типы.
- Граф логический над табличной C2 (не Neo4j); геометрия WKT/GeoJSON+srid, PostGIS опц.
- Право = ребро relations[legal], не узел; corporate-контроль = legal/corporate.
- Веса источников 1.0/0.8/0.6/0.5/0.4/0.3; EGRUL/ЕГРИП не доказывают OWNS.
- current_level не хранится (из flow_events); Telemetry вне проекта.
- УПД: vat_mode ∈ {OSNO,USN,USN_VAT}; USN_VAT ⇒ статус 1 (реформа УСН-2025).
- ADR-P03: innogrn/nma отдельные БД через subject_external_ref.

## Файлы под нож
- `obsidian/Architecture/ekcelo-system-description.md` (новый)

## Дальше (по плану)
Alembic-baseline из models.py + стадия импорта Block-2 БД (land/building_objects/
accessories → objects + граф-таблицы); сведение graph v1.1/v14 к одному эмиттеру.
