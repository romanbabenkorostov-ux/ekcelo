# 2026-06-04 — Проект БД EKCELO (табличная C2 + графовые принципы + классификатор)

## Задача
Спроектировать табличную (SQLAlchemy/Alembic, SQLite↔PG) и графовую БД объединённого
проекта (ekcelo + ekcelo-parser + ekcelo-site) по описанию сущностей/связей заказчика
(5 точек зрения) + вложение «разделение графовых доменов» + образцы документов.

## Сделано
- 24 уточняющих вопроса → заказчик выбрал «оптимальные» (все ⭐). Применено
  `разделение графовых доменов.md` (Entity/Relation/Assertion/Evidence + 5 доменов).
- `contracts/db/SCHEMA_SPEC.md` — каноника C2: §1–§6 (ЕГРН-слепок+ЭТП) сохранены,
  NEW §7 граф знаний, §8 геометрия, §9 технологический, §10 субъекты+, §11 коммерческий,
  §12 документы. DIFF новых таблиц/полей к `egrn_current_schema.sql`.
- `contracts/db/models.py` — SQLAlchemy 2.0, переносимо (JSON↔JSONB, Uuid), битемпоральные
  миксины. Импорт + `create_all` на SQLite зелёные (25 NEW-таблиц).
- `contracts/db/GRAPH_DB_PRINCIPLES.md` — логический граф над таблицами, 5 доменов,
  вероятностная истина, согласование C1(`graph_node_id`)/C4(facets), выводимость узлов.
- `contracts/db/DOC_CLASSIFIER_SPEC.md` — конвейер + декларативный реестр «документ→поля»
  (9 типов, на образцах: ЕГРН-XML кв.8 Суворова-52, ОСВ ООО «Лебеди» сч.01.01, ЕГРЮЛ/ЕГРИП).

## Ключевые решения
- KG **поверх** §1–§5 (ЕГРН = Evidence weight 1.0), не замена (ADR-001).
- UUID PK + `cad_number`/`inn` natural-keys + стабильный `graph_node_id` (C1).
- Accounting-связь (ОСВ) ≠ legal-OWNS: `legal_owner` может ≠ `balance_holder`.
- Геометрия МСК-61 → WGS-84(4326) для KMZ; в графе только bbox.
- innogrn/nma — мост `subject_external_ref`, не уплощаем (ADR-P03).

## Поправки терминов (в описании заказчика)
A1 «прекращение недвижимости» = Акт обследования (не «госрегистрация по Акту кад.инженера»);
A2 `BENEFICIARY` — роль, не `SubjectType`; A3 `EGRUL` не доказывает OWNS (питает Subject/FOUNDER_OF);
A4 confidence SURVEY 0.3 (унифицировано); A5 `current_level` считается из flow_events, не колонка;
A7 SRID: ЕГРН=МСК-61, KMZ=4326.

## Дальше
- Согласовать с заказчиком расширение `viewmodel.schema.json` (C4) `graphNode.kind`
  (+device/state_body/flow_node/demarcation_point/business_asset/lot/order).
- По согласовании — архитектор корректирует планы 3 команд (ekcelo: миграции+импортёр Bundle+ViewModel;
  ekcelo-parser: стадия `classify` + реестр + новые поля egrn/enrich/structure; ekcelo-site: ViewModel+граф-рендер).
- Образцы Drive по-прежнему недоступны коннектору — нужны для финальной выверки форматов техплана/KML.
