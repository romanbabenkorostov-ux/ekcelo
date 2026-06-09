# 2026-06-08 — Предложение модели ЗУ/ЕЗП/МКУ (контуры + техсвойства) + директора/реорг

## Суть
Два потока: (1) добивка ЕГРЮЛ/ЕГРИП — директора/управляющие/реорг-рёбра в БД;
(2) проектное предложение по трём представлениям земель (ЗУ/ЕЗП/МКУ) с
поконтурными технологическими свойствами.

## 1. Директора/реорг → entity_relations (код, 42/42)
См. Changelog 2026-06-05-egrul-egrip-entity-relations. Новая таблица
`entity_relations` (director|managing_org|predecessor|successor), `upsert_relations`.

## 2. ЗУ/ЕЗП/МКУ — ADR-005 (proposed, проект)
- **Онтология** в репо: `Architecture/zu-ezp-mku-ontology.md` (из присланного md).
- **ADR-005** (`Decisions/ADR-005-zu-ezp-mku-contours-and-tech.md`) — предложение:
  - **Тип представления**: `land_objects.land_layout_type` ∈ {ЗУ,ЕЗП,МКУ}, детект по
    маркеру `(Единое землепользование)` / дочерним КН / числу контуров.
  - **Контур как сущность**: новая `land_contours` (parent_cad, contour_no,
    contour_cad?, geom, источник). ЗУ→1, МКУ→N без своих КН, ЕЗП→N с дочерними КН.
  - **Связи (граф)**: через `linked_objects` — `ezp_child` (родитель→дочерний КН),
    `mku_contour` (родитель→контур-узел), `reorg_predecessor/successor`.
  - **Техсхема**: новая `contour_tech_profile` (§6-слой, source+confidence) —
    crop/variety/treatments[]/climate/soil/planting НА КОНТУР; техсхема лота =
    агрегат по контурам.

## Файлы под нож
- `obsidian/Decisions/ADR-005-zu-ezp-mku-contours-and-tech.md` (новый, proposed)
- `obsidian/Architecture/zu-ezp-mku-ontology.md` (новый)
- (код части 1 — отдельным коммитом c0be15b)

## Дальше (план ADR-005)
Детект layout_type → миграция `land_contours`+`contour_tech_profile` → backfill
из object_geometries/contours.json → расширение sidecar → граф/viewer-кластеры →
агрегатор техсхемы лота. Реализацию согласовать с граф-схемой соседнего чата.
