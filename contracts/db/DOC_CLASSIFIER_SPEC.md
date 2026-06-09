# DOC_CLASSIFIER_SPEC — парсер-классификатор документов EKCELO

> Каждый документ → «какие параметры каких сущностей он обогащает». Вход: один файл
> или рекурсивный обход папки оператора. Классификатор определяет тип и питаемые
> сущности/поля; у оператора спрашивается только начальная привязка (anchor), когда её
> нельзя вывести. Версия: 0.1 · 2026-06-04. Опирается на C2 (SCHEMA_SPEC) + образцы.

## 1. Конвейер

```
walk(folder) ─► detect(file) ─► classify(doc_type) ─► extract(fields)
            ─► anchor(entity)  ─► route(facts → §-таблицы + entities/relations/assertions/evidences)
            ─► provenance(source, confidence)  ─► doc_links
```

1. **detect** — MIME + расширение + имя файла + сигнатуры (regex по первым КБ / XML-корню).
2. **classify** — по декларативному реестру (§3). LLM — фолбэк при `conf < порога`.
3. **extract** — экстрактор типа документа → плоский dict полей.
4. **anchor** — найти сущность-якорь по ключам (КН/адрес/ИНН/ОГРН/№дела). Папка = группа:
   якорь подтверждается оператором **один раз на группу**, не на файл (ответ 22).
5. **route** — разложить факты по таблицам + создать `entities`/`relations`/`assertions`/`evidences`.
6. **provenance** — каждый факт несёт `source_type` + `weight` → `evidences`; `doc_links` фиксирует
   `документ → target_table.target_field` с `relation_code ∈ {ESTABLISHES, EVIDENCES, DEPICTS}`.

## 2. Когда спрашивать оператора

- Нет якоря (ни КН, ни адреса, ни ИНН) **или** `anchor_confidence < 0.7` → запрос привязки.
- Конфликт значений с существующим высокодоверенным фактом → очередь ревью (не блокирует).
- Иначе — авто, всё с провенансом (competing assertions разрулятся по confidence).

## 3. Декларативный реестр (карта документ → сущности/поля)

> Формат YAML-записи. Движок читает реестр; коды совпадают с `documents.doc_type`.
> `enriches.<entity>.<field>` ← поле документа; `establishes` — правоустанавливающие рёбра.

### 3.1 ЕГРН-выписка (XML/PDF) — `egrn_extract`
*Подтверждено образцом `extract_about_property_room` (КН 61:44:0040713:446, кв.8, Суворова 52).*
```yaml
doc_type: egrn_extract
source: EGRN            # weight 1.0
anchor_keys: [cad_number, readable_address]
detect: {xml_root: [extract_about_property_room, extract_about_property_land, extract_base_params_*]}
enriches:
  objects:
    cad_number:        object.common_data.cad_number
    quarter_cad_number: object.common_data.quarter_cad_number     # NEW поле
    object_type:       params.type.value                          # room/building/land...
    area:              params.area
    permitted_use:     params.permitted_uses[].name
    purpose:           params.purpose.value
    floor:             location_in_build.level.floor              # NEW
    inventory_number:  cad_links.old_numbers[type=01].number      # NEW (143/2)
    conditional_number: cad_links.old_numbers[type=02].number     # NEW (61-61-01/224/2006-333)
    parent_cad_number: cad_links.parent_cad_number.cad_number     # NEW
    cadastral_value:   cost.value                                 # NEW (1016079.04)
    okato:             address.location.okato                     # NEW
    kladr:             address...kladr                            # NEW
    status_egrn:       status                                     # NEW («актуальные ранее учтённые»)
  rights ⇒ relations[legal/OWNS]:
    right_type:        right_record.right_data.right_type.value   # Собственность
    registration_number: right_record.right_data.right_number
    holder(subject):   right_holder.legal_entity.entity.resident{name,inn,ogrn}
    holder_contacts:   {email, mailing_addess}                    # NEW (email any400@…, почт.адрес)
  geometries:          (если есть контур) WKT, original_srid=МСК-61 → srid=4326
establishes: ESTABLISHES(right_record → object)   # право подтверждено выпиской
```

### 3.2 ЕГРЮЛ (PDF) — `egrul_extract`
```yaml
doc_type: egrul_extract
source: EGRUL          # питает атрибуты Subject + corporate-рёбра, НЕ OWNS объекта (поправка)
anchor_keys: [inn, ogrn]
enriches:
  subjects:                                  # КАЖДЫЙ участник раздела — отдельный subject:
    - {inn, ogrn, name_current, subject_type: LEGAL_ENTITY}   # само ЮЛ
    - учредители (раздел «Сведения об учредителях»)           # ФЛ/ЮЛ
    - руководитель (раздел «Сведения о лице, имеющем право без доверенности         # 1.1:
        действовать от имени ЮЛ») — ФЛ ИЛИ ЮЛ (управляющая компания)                # директор
  subject_kpp: [kpp...]                    # доп. КПП = обособленные подразделения
  subject_names: [{name_full, valid_from}] # история наименований (1 ИНН)
relations[legal/corporate]:
  FOUNDER_OF:   учредитель → ЮЛ              # раздел «Учредители (участники)»
  MANAGES:      руководитель/УК → ЮЛ         # «лицо без доверенности» (ФЛ или ЮЛ)
  CONTROLS:     участник → ЮЛ (доля в meta)  # бенефициарная цепочка
  # ── реорганизация (раздел «Сведения о правопреемнике/правопредшественнике») ──
  SUCCESSOR_OF: правопреемник → правопредшественник   # завершённая реорганизация
                # meta.reorg_type ∈ {merger,affiliation,division,spin_off,transformation}
  REORGANIZING_WITH: ЮЛ ←→ ЮЛ                          # «участвующие в реорганизации»
                # реорг. НЕ завершена; tentative, confidence ниже; снимается при завершении
note: |
  Правопреемство (SUCCESSOR_OF) ≠ учредительство (FOUNDER_OF). Правопреемник наследует
  ПРАВА И ОБЯЗАННОСТИ реорганизованного ЮЛ (включая долги/налоги); сам факт
  правопреемства новых учредителей не создаёт. До завершения реорганизации в выписке
  правопреемник прямо не указан — только REORGANIZING_WITH. Основание: ФЗ-129 ст.5 п.1 пп «ж».
```

### 3.3 ЕГРИП (PDF) — `egrip_extract`
```yaml
doc_type: egrip_extract
source: EGRIP
anchor_keys: [inn]
enriches:
  subjects: {inn(12), subject_type: INDIVIDUAL_ENTREPRENEUR}
  ip_status_periods: [{ogrnip, registered_at, terminated_at}]   # статус ИП повторяем
```

### 3.4 ОСВ (XLSX/DOCX) — `osv`
*Подтверждено образцом: ООО «Лебеди», счёт 01.01.*
```yaml
doc_type: osv
source: OSV            # weight 0.8 — признаётся правом наравне (accounting-домен)
anchor_keys: [subject_from_filename]      # бенефициар по имени файла
enriches:
  subjects: {name_current from filename}
relations[accounting]:
  ON_BALANCE_OF:     account 01.01 → собственность
  LEASED_IN_BALANCE: account 01.03, 01.К → аренда/лизинг
note: accounting-связь ОТДЕЛЬНА от legal-OWNS; legal_owner может ≠ balance_holder.
```

### 3.5 Правоустанавливающие (PDF/скан) — `legal_basis`
```yaml
doc_type: legal_basis   # Акт ввода / Решение суда / ДКП / Свидетельство / Акт кад.инженера
source: COURT_DECISION|SURVEY_MANUAL|EGRN
anchor_keys: [cad_number, case_number, contract_number]
enriches:
  documents: {doc_type, number, issue_date, issuer}
establishes: ESTABLISHES(document → relation[legal])  # возникновение/переход/прекращение права
chain: формирует цепочку перехода прав (traversal по legal_documents)
correction:                                  # поправка терминов A1:
  возникновение: Акт ввода в эксплуатацию / Акт кад.инженера(техплан)
  прекращение:   Акт обследования (снятие с учёта при гибели/сносе)
```

### 3.6 Техплан/техпаспорт (PDF/XML) — `tech_plan`
```yaml
doc_type: tech_plan
source: EGRN|SURVEY_MANUAL
enriches:
  geometries: контуры ОКС/ЗУ (WKT, original_srid)
  objects: {floors, area уточнение, level z}
```

### 3.7 Фото с EXIF (JPG) — `photo`
```yaml
doc_type: photo
source: EXIF           # weight 0.5
anchor_keys: [gps → ближайший объект, cad_number из имени папки]
enriches:
  geometries: точка съёмки (gps)
  object_etp_profile: layout/current_condition (через LLM-разметку, source=llm)
establishes: DEPICTS(photo → object)
```

### 3.8 Договор снабжения — `supply_contract`
```yaml
doc_type: supply_contract
enriches:
  entities[demarcation_point]: точка разграничения баланс. принадлежности
relations[tech]: CONNECTED_TO разрывается узлом demarcation_point (сеть ↔ объект)
```

### 3.9 Коммерческие — `contract` / `invoice` / `upd_xml`
```yaml
doc_type: upd_xml
detect: {xml_root: Файл, xsd: УПД ФНС}
enriches:
  upd_documents: {number, date, status(1|2), xsd_version, validated}
rule: supplier.vat_mode == USN_VAT ⇒ status = 1   # с НДС, несмотря на УСН
```

## 4. Выход классификатора (на каждый документ)

```json
{
  "doc_type": "egrn_extract", "confidence": 0.98,
  "anchor": {"entity": "room:61:44:0040713:446", "by": "cad_number", "confidence": 1.0},
  "facts": [{"table":"objects","field":"cadastral_value","value":1016079.04,"source":"EGRN","weight":1.0}],
  "relations": [{"domain":"legal","code":"OWNS","from":"subj:2312122992","to":"room:61:44:0040713:446"}],
  "doc_links": [{"target_table":"objects","target_field":"area","relation_code":"EVIDENCES"}],
  "needs_operator": false
}
```

## 5. Реализация в ekcelo-parser

Новая стадия `stages/classify.py` + `core/pipeline.py: classify_folder(path)`; реестр —
`contracts/db/doc_registry.yaml` (vendored в parser). Переиспользует egrn-парсер (3.1),
enrich (3.2–3.3), ОСВ-ETL (3.4), nspd/exif (3.7). Выход замыкается на Bundle (C3) + §-таблицы.
