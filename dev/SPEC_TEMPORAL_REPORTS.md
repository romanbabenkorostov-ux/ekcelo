# SPEC: Temporal Reports — документы во времени + console-CLI отчёты

- **Статус:** draft v1, parser-internal
- **Дата:** 2026-05-24
- **Автор:** parser-team (A)
- **Зона:** parser-internal (НЕ contract-KMZ wire-инвариант)
- **Связь:** `docs/CONTRACT_KMZ.md` §9 S6+ (informative reference);
  `docs/CORRESPONDENCE/013-parser-temporal-reports-spec.md`
- **Реализация:** последующие PR-α…ε (см. §14)

---

## §1. Goal & Non-goals

### Что spec покрывает (v1)

1. **Snapshot-overlay temporal модель** — алгоритм `resolve_state(target_date)`
   на базе последней выписки ЕГРН + overlay-документов.
2. **Регистр документов** — sidecar `<project>/_data/documents.json` (источник
   истины) + БД-индексер.
3. **Юниты-принадлежности без КН** — новый тип `principal_unregistered`
   в `cadastre_objects[]`.
4. **State-tag namespaces** — структура multi-tag описания юнита (юр.состояние,
   коммуникации, целевое использование, физ.состояние, формат использования).
5. **CLI-скрипт `09_make_reports_v1.py`** — два отчёта (ОСВ-сверка,
   залоговая таблица) с конвертацией в DOCX.
6. **Founder-chain pledge propagation** — алгоритм поиска залога в УК
   материнских ЮЛ.
7. **MD→DOCX util** — `parser/utils/md_to_docx.py` с fallback-цепочкой
   python-docx → LibreOffice → MS Word.
8. **Footnotes-схема источников** — `[^N]` inline + `<details>` блок.

### Что spec НЕ покрывает

- **multi-level Z** для помещений (отдельный MAJOR spec, §9 S6+ контракта).
- **e2e-обновление viewer-domain UI** для timeline-навигации (S7+; см.
  CORRESPONDENCE/013 §3).
- **Bitemporal** (валидность vs запись) — out-of-scope v1; см. §13.
- **Полный event-sourcing** (вместо snapshot+overlay) — out-of-scope v1.
- **Автоматический ingester** ОСВ как отдельный сервис (см. §14, future
  iteration).
- **Машинное извлечение state-tags** из ОСВ-комментариев / ЕГРН-описаний —
  out-of-scope v1; в v1 теги добавляются вручную через documents.json.
- **Стили документ-узлов в `04_nspd_graph_v14.py`** (чёрные точки с
  ссылкой на JPG) — S6+ wishlist, см. §14.

---

## §2. Domain Glossary

| Термин | Определение |
|---|---|
| **Юнит недвижимости** | Атомарная учётная единица: земельный участок (ЗУ), ОКС (здание, сооружение, ОНС), помещение, машино-место. Может иметь КН (главная вещь по ст.130 ГК) или быть принадлежностью без КН (текстовое описание). |
| **Актив юнита** | Параметры физического взаимодействия с юнитом (геометрия, площадь, ограничения по использованию). |
| **Пассив юнита** | Параметры юридического взаимодействия с юнитом (права, обременения, аренда, залог). |
| **Бизнес-актив (БА)** | Поименованная связь многие-ко-многим между юнитами недвижимости, оборудованием и бенефициарами. В `structure.json` — `business_units[]`. |
| **Бенефициар** | Конечный получатель экономической выгоды от юнита. ЮЛ (`_kind="legal"`), ИП (`_kind="ip"`), ФЛ (`_kind="person"`), упомянутый-но-не-загруженный ЮЛ (`_kind="legal_text"`). |
| **Документ** | Любой акт, выписка, договор, решение суда, нотариальный документ, формирующий или изменяющий состояние юнита или его пассивов. |
| **Артефакт документа** | Физический файл (JPG/PDF), привязанный к документу через `documents.json` и EXIF JPG (`docs/EXIF_USERCOMMENT_SCHEMA.md`). |
| **Точка актуальности T** | Дата, на которую отвечаем на вопрос «каково состояние юнита/пассива/бенефициара?». В CLI — `--as-of YYYY-MM-DD` или interactive prompt. |
| **Снимок** | Полное состояние всех юнитов/пассивов на дату выписки ЕГРН. Источник: один JSON ≈ результат 052 на конкретной выписке. В первичной реализации = единственный `structure_<slug>.json`. |
| **Overlay-документ** | Документ с `doc_date`, который **добавляет/снимает/изменяет** факты поверх снимка, до момента, пока следующая выписка их не поглотит или не подтвердит. |
| **OCC (Object Change Cohort)** | Сгруппированный набор overlay-эффектов на один и тот же `target`, отсортированный по `(doc_date, registered_at, doc_id)` для детерминизма. |
| **Founder-chain** | Цепочка учредителей от enterprise вверх по структуре уставного капитала (через ЮЛ-вершины графа). Источник: `04_nspd_graph_v14.py` `kind=founder` рёбра + `beneficiaries[*]["Бенефициар (ключ)"]` parent-pointers. |
| **Залогодержатель** | Лицо (ЮЛ/ФЛ), в пользу которого зарегистрирован залог. В цепочке founder-chain для отчёта о залоге УК — **исключается** из обхода (по требованию пользователя). |

---

## §3. Temporal Model — Snapshot-Overlay

### §3.1 Принцип

Состояние объекта на момент T = **(последняя выписка ЕГРН с
extract_date ≤ T)** + **(все overlay-документы с doc_date ≤ T, чьи
эффекты ещё не поглощены более свежими выписками)**.

### §3.2 Поглощение overlay-документов

Overlay-документ X с `doc_date(X)` **поглощается** выпиской V если
`extract_date(V) > doc_date(X)`. Поглощённый документ остаётся в журнале
(`documents.json`) для аудита и для запросов состояния на промежуточные
точки T ∈ `[doc_date(X), extract_date(V))`, но не участвует в
`resolve_state(T)` где T ≥ extract_date(V).

### §3.3 Алгоритм `resolve_state(target_date)`

```python
def resolve_state(structure: dict, documents: list[dict], target_date: date) -> dict:
    # 1. Базовый снимок — последняя выписка ЕГРН с extract_date <= target_date.
    extracts = [d for d in documents
                if d["kind"] in ("egrn_extract", "egrul_extract", "egrip_extract")
                and parse_date(d["doc_date"]) <= target_date]
    if not extracts:
        return structure  # нет выписок → отдаём структуру как есть (fallback)
    latest_extract = max(extracts, key=lambda d: parse_date(d["doc_date"]))
    state = deepcopy(snapshot_for(structure, latest_extract))

    # 2. Overlay — все non-extract документы с doc_date ∈ (extract_date, target_date].
    overlays = [d for d in documents
                if d["kind"] not in ("egrn_extract", "egrul_extract", "egrip_extract")
                and parse_date(latest_extract["doc_date"]) < parse_date(d["doc_date"]) <= target_date]
    overlays.sort(key=lambda d: (d["doc_date"], d.get("registered_at", ""), d["doc_id"]))

    # 3. Применяем эффекты детерминистично.
    for doc in overlays:
        for eff in doc.get("effects", []):
            apply_effect(state, eff, source_doc_id=doc["doc_id"])

    return state
```

### §3.4 Структура эффекта

```jsonc
{
  "op": "add" | "remove" | "change",
  "target": "cadastre_objects[id=cad_a1b2c3d4].restrictions",
  // путь в формате JSONPath-lite: <ключ>[id=<id>].<поле> или
  //                                <ключ>[key=<key>].<поле>
  "payload": {
    // для add: новая запись (dict)
    // для remove: критерий (например {"type":"арест","number":"..."})
    // для change: {"match":{...}, "set":{...}}
  }
}
```

### §3.5 Пример

```
Документ A: ЕГРН-выписка от 2026-01-15 — в restrictions объекта
            cad_a1b2c3d4 есть запись "Арест от 2025-12-01, основание...".
Документ B: уведомление о снятии ареста от 2026-03-01.
            effect: {op:remove, target:cadastre_objects[id=cad_a1b2c3d4].restrictions,
                     payload:{type:"арест"}}.
Документ C: новая ЕГРН-выписка от 2026-04-15 — restrictions объекта
            cad_a1b2c3d4 пуст (арест снят на уровне Росреестра).

resolve_state(2026-02-01) → restrictions = [Арест] (документ B ещё в будущем).
resolve_state(2026-03-15) → restrictions = []      (B применён, C ещё в будущем).
resolve_state(2026-05-01) → restrictions = []      (C поглотил B).
```

### §3.6 Конфликты при равной дате

При двух документах с одинаковым `doc_date` сортировка по
`(registered_at, doc_id)` гарантирует детерминизм. Если оба — выписки
ЕГРН той же даты с противоречивыми restrictions — **v1 fails-fast**
(`AssertionError` с описанием конфликта); пользователь вручную правит
`documents.json` (удаляет дубликат или сдвигает дату). В v2 — interactive
resolution prompt (см. §13).

---

## §4. Documents Registry — `<project>/_data/documents.json`

### §4.1 Источник истины

Sidecar JSON в корне проекта, append-only, git-trackable. БД-таблица
`documents` (генерируется через `egrn_parser reindex-documents` — см. §14
PR-β) используется только для быстрых запросов отчётами; ground-truth —
JSON.

### §4.2 Схема

```jsonc
{
  "schema_version": "1.0",
  "project_slug": "sosnovaya-roscha",
  "documents": [
    {
      "doc_id": "ee_a1b2c3d4",       // [kind-prefix]_<sha8 по (kind+doc_date+subjects+artifact_sha256)>
      "kind": "egrn_extract",        // см. §4.3 enumeration
      "doc_date": "2026-04-15",
      "registered_at": "2026-04-20T11:32:00+03:00",  // когда добавлен в систему
      "subjects": {
        "cadastrals": ["61:44:0050706:31"],
        "inns": [],
        "ognrs": [],
        "bu_ids": []
      },
      "effects": [],                  // для выписок ЕГРН — пустой массив:
                                      // выписка не "добавляет" эффекты,
                                      // она создаёт новый snapshot-кадр
                                      // (см. §3.1: extract = base, не overlay).
      "artifacts": [
        {
          "file": "docs/egrn_zu_61_44_0050706_31_2026-04-15.pdf",
          "sha256": "ab12...",
          "page_count": 8
        }
      ],
      "source_id": null,              // для footnote-нумерации (см. §10);
                                      // null = генерируется автоматически
      "notes": null
    },
    {
      "doc_id": "nr_ef567890",
      "kind": "notarial_release",
      "doc_date": "2026-03-01",
      "registered_at": "2026-03-02T10:00:00+03:00",
      "subjects": {"cadastrals": ["61:44:0050706:31"]},
      "effects": [
        {
          "op": "remove",
          "target": "cadastre_objects[id=cad_a1b2c3d4].restrictions",
          "payload": {"type": "арест"}
        }
      ],
      "artifacts": [{"file": "docs/release_arrest_2026-03-01.jpg",
                     "sha256": "cd34...", "page_count": 1}],
      "source_id": null,
      "notes": "Снятие ареста по решению суда от 2026-02-25"
    },
    {
      "doc_id": "pc_12345678",
      "kind": "purchase",
      "doc_date": "2026-02-20",
      "registered_at": "2026-02-25T09:00:00+03:00",
      "subjects": {"cadastrals": ["61:44:0050706:32"],
                   "inns": ["7700000001"]},
      "effects": [
        {
          "op": "change",
          "target": "cadastre_objects[id=cad_b2c3d4e5].right_type",
          "payload": {"set": "собственность", "owner_inn": "7700000001"}
        }
      ],
      "artifacts": [{"file": "docs/purchase_2026-02-20.jpg",
                     "sha256": "ef56...", "page_count": 4}],
      "source_id": null,
      "notes": "Купля-продажа от ООО Прежний-Собственник → ООО АКМЕ-ПРОМ"
    }
  ]
}
```

### §4.3 `kind` enumeration

| kind | Описание | Префикс doc_id |
|---|---|---|
| `egrn_extract` | Выписка из ЕГРН | `ee_` |
| `egrul_extract` | Выписка из ЕГРЮЛ | `eul_` |
| `egrip_extract` | Выписка из ЕГРИП | `eip_` |
| `notarial_release` | Нотариально удостоверенное снятие обременения | `nr_` |
| `purchase` | Договор купли-продажи | `pc_` |
| `mortgage` | Договор ипотеки / залога | `mg_` |
| `court_decision` | Решение суда | `cd_` |
| `bank_letter` | Письмо банка-залогодержателя | `bl_` |
| `lease` | Договор аренды | `ls_` |
| `other` | Прочее (требует `notes`) | `ot_` |

### §4.4 Связь с EXIF JPG

`docs/EXIF_USERCOMMENT_SCHEMA.md` v1.1 (минорный аддитивный bump,
parser-internal) добавляет поле `doc_id` в payload:

```jsonc
{
  "app": "ekcelo",
  "kind": "egrn_extract",      // дублирует documents.json для self-check
  "doc_id": "ee_a1b2c3d4",     // ← новое поле, ссылка на documents.json
  // ...existing fields
}
```

EXIF остаётся для viewer-routing (lightbox → graph node). Источник
истины для temporal-обработки — `documents.json`.

---

## §5. State-tag Schema (multi-tag описание юнита)

### §5.1 Хранение

`cadastre_objects[].state_tags[]` — массив объектов:

```jsonc
{
  "namespace": "legal_state",
  "value": "введён_в_эксплуатацию_по_суду",
  "since": "2024-11-12",         // YYYY-MM-DD; null = с момента создания
  "until": null,                 // null = действующий
  "source_doc_id": "cd_99887766" // ссылка на documents.json
}
```

### §5.2 Namespaces (v1)

| namespace | значения (примеры) |
|---|---|
| `legal_state` | `введён_в_эксплуатацию`, `введён_в_эксплуатацию_по_суду`, `подготовлен_к_демонтажу`, `разрешено_проживание`, `сертификат_гостиница_5*`, `сертификат_отозван`, `признан_аварийным` |
| `utility_water` | `проектируется`, `работает_локальное`, `работает_сетевое`, `демонтировано` |
| `utility_gas` | `получено_разрешение_на_подключение`, `подключено`, `демонтировано` |
| `utility_electricity` | `проектируется`, `работает`, `демонтировано` |
| `utility_sewage` | `проектируется`, `работает_локальное`, `работает_сетевое`, `демонтировано` |
| `highest_best_use` | `музей`, `гостиница`, `жилой_дом`, `офисный_центр`, `гараж`, `эллинг`, `апарт_отель` |
| `physical_state` | `возводится`, `отличное`, `хорошее`, `удовлетворительное`, `требуется_косметический_ремонт`, `требуется_капитальный_ремонт`, `руинировано` |
| `actual_use_format` | `апартаменты`, `музей`, `гараж`, `мотель`, `не_используется`, `заброшено` |

### §5.3 Resolve через тот же overlay

`state_tags` resolve'ятся тем же `resolve_state(T)`: тег действует если
`since ≤ T < (until or +∞)`. Изменение тега = два effect'а:
`{op:change, ..., set:{until: T}}` для старого + `{op:add, ...}` для
нового.

### §5.4 Источники тегов в v1

Только **ручное** добавление через `documents.json` `effects[].target =
cadastre_objects[id=...].state_tags`. Машинное извлечение из
ОСВ-комментариев/ЕГРН-описаний — v2 (см. §13).

---

## §6. Юниты-принадлежности без КН — `principal_unregistered`

### §6.1 Мотивация

Принадлежность главной вещи (ст. 135 ГК) с признаками недвижимости,
но без КН (нет постановки на кадастровый учёт): сараи, навесы,
ограждения, объекты НЗС на счёте 08. Учитываются в бухгалтерии (счета
01.01, 01.03, 08), но не в Росреестре.

### §6.2 Представление в `cadastre_objects[]`

```jsonc
{
  "id": "unc_a1b2c3d4",
  "cadastral_number": null,                       // ← ключевое отличие
  "object_type": "principal_unregistered",
  "text_descriptor": "Хозблок с погребом, литер Г",
  "accounting_account": "01.01",                  // 01.01 / 01.03 / 01.К / 08
  "parent_cadastral": "61:44:0050706:31",         // принадлежность к КН-юниту
  "address": "Краснодарский край, ...",
  "area": 24.5,
  "inv_number": "ОС-12345",                       // из ОСВ
  "right_type": "собственность",
  "sources": ["osv:row_142"],
  "state_tags": [],
  "_raw_text": "...",
  "_geometry": null
}
```

### §6.3 ID-схема

`id = "unc_" + sha8(text_descriptor + "|" + inv_number_or_empty)`.

Детерминистично; при изменении descriptor/inv_no ID меняется (это
сигнал для оператора — переименование = новый юнит, разбираться вручную).

### §6.4 Downstream-совместимость

- **052_make_structure_v2_2** — должен генерировать такие записи при
  парсинге ОСВ (PR-β/δ; сейчас ОСВ парсится но `principal_unregistered`
  не выделяется как отдельный тип).
- **04_nspd_graph_v14** — игнорирует `cadastral_number = null` (узлы
  не рисуются); ребро от parent КН рисуется как обычное «компонент».
  Стили для документ-узлов и principal_unregistered — S6+ wishlist.
- **08_build_kmz_v2_2** — KMZ wire не меняется (KMZ работает только с
  объектами с КН — это §6 контракта). `principal_unregistered`
  остаются в `structure.json`, в KMZ не попадают. Это не breaking для
  контракта 2.11.0.

---

## §7. Founder-chain Pledge Propagation

### §7.1 Граф founder-цепочки

Источник истины — `beneficiaries[*]["Бенефициар (ключ)"]` parent-pointer
из `enriched.json` (тот же, что использует 052_v2_2 в
`link_with_enriched`). Граф рёбер `kind=founder` в
`04_nspd_graph_v14.py` — валидатор (структура должна совпадать).

### §7.2 Алгоритм

```python
def founder_chain_has_pledge(
    enterprise_key: str,
    beneficiaries: dict[str, dict],
    exclude_pledge_holders: set[str],
) -> tuple[bool, list[str]]:
    """
    BFS вверх от enterprise_key через "Бенефициар (ключ)" parent-pointer.
    Возвращает (есть_ли_залог, путь_до_первого_залогодателя).

    exclude_pledge_holders: ключи бенефициаров, которые являются
        залогодержателями — их исключаем из обхода (по требованию
        пользователя: «исключая самих залогодержателей из цепочки»).
    """
    visited: set[str] = set()
    queue: deque[tuple[str, list[str]]] = deque([(enterprise_key, [enterprise_key])])

    while queue:
        cur, path = queue.popleft()
        if cur in visited or cur in exclude_pledge_holders:
            continue
        visited.add(cur)

        ben = beneficiaries.get(cur)
        if not isinstance(ben, dict):
            continue

        if ben.get("has_pledge") or ben.get("Обременения доли"):
            return True, path

        parent_key = ben.get("Бенефициар (ключ)") or \
                     ben.get("attrs", {}).get("Бенефициар (ключ)")
        if parent_key and parent_key not in visited:
            queue.append((parent_key, path + [parent_key]))

    return False, []
```

### §7.3 Свойства

- **Глубина** — без лимита (до корня); защита от циклов через `visited`.
- **Залогодержатели исключаются** — `exclude_pledge_holders` собирается из
  `cadastre_objects[*].restrictions[*].beneficiary_inn` (залоги объекта)
  и `beneficiaries[*].Обременения доли[*].Сведения о залогодержателе.ИНН`
  (залоги долей) — затем resolve'им ИНН → ben_key через `beneficiaries`.
- **Path returned** — для footnote-источников в отчёте: показываем какой
  материнский ЮЛ дал залог.

---

## §8. CLI `parser/scripts/pirushin_sosn_rocha_09_make_reports_v1.py`

### §8.1 Запуск

```bash
python3 parser/scripts/pirushin_sosn_rocha_09_make_reports_v1.py [--as-of YYYY-MM-DD] [project_dir]
```

- Без аргументов: интерактивный prompt на `project_dir` (как 052_v2_2:
  search для `structure_*.json` в текущей папке).
- `--as-of` опционально; default = `max(extract_date)` среди выписок в
  `documents.json` (или `today()` если документов нет).

### §8.2 Главное меню (паттерн 052_v2_2 `ask`/`ask_yn`)

```
=== ekcelo: Отчёты по проекту "Санаторий «Сосновая Роща»" ===
Точка актуальности (T): 2026-04-15 (последняя выписка)
Документов в реестре: 12 (5 выписок + 7 overlay)

[1] ОСВ-сверка (счета 01.01 / 01.03 / 01.К / 08)
[2] Таблица залогов (4 секции)
[3] Конвертировать сгенерированные отчёты в DOCX
[Q] Выход

Выбор: _
```

### §8.3 Подменю 1: ОСВ-сверка

**Условие:** в проекте найден ОСВ XLSX или JSON-кеш ОСВ. Если нет —
сообщение «ОСВ не загружен; пропустите этот пункт или подключите
ОСВ через 052».

**Output:** `<project>/reports/report_osv_recon_<ts>.md` со структурой:

```markdown
# ОСВ-сверка по проекту X на YYYY-MM-DD

## §1. Счёт 01.01 (Основные средства — собственные)

### В ОСВ есть, в кадастровом учёте отсутствуют
| Инв.№ | Наименование | КН-подсказка | Сумма (БС) | Источник |
| ---   | ---          | ---          | ---        | ---      |
| ОС-001 | Здание гостиницы корпус 1 | 61:44:0050706:31 | 12 500 000,00 | [^1] |

**Рекомендация:** проверить наличие объекта в учёте. Если объект существует
de facto — рекомендовать руководству поставить на кадастровый учёт
(заявление в Росреестр через МФЦ; пакет: технический план + правоустанавливающий
документ).

### В кадастре есть, в ОСВ отсутствуют
...

## §2. Счёт 01.03 (Аренда)
...

## §3. Счёт 01.К (Арендные платежи накопленные)
...

## §4. Счёт 08 (Капвложения в строительство)
...

---

<details>
<summary>Источники (служебный блок, нумерация для внутрифайлового использования)</summary>

[^1]: ОСВ-выгрузка из 1С от 2026-04-10, файл `osv_april2026.xlsx`,
      строка 142, doc_id=osv:row_142

</details>
```

### §8.4 Подменю 2: Таблица залогов

**Output:** `<project>/reports/report_pledges_<ts>.md`:

```markdown
# Таблица объектов по типам залога на 2026-04-15

## §1. Без залога
| Адрес | Вид | КН | Площадь, м² | Источник |
|---|---|---|---|---|
| ... | ЗУ | 61:44:0050706:31 | 1 500 | [^1] |

## §2. С залогом объекта (группировка по залогодержателям)

### АО «Банк-Залогодержатель-1» (ИНН 7700000099)
| Адрес | Вид | КН | Площадь, м² | Договор залога | Источник |
|---|---|---|---|---|---|
| ... | ОКС | 61:44:0050706:32:1 | 850 | №123 от 2025-06-15 | [^2] |

## §3. С залогом доли в УК (группировка по залогодержателям)

### АО «Банк-Залогодержатель-2» (ИНН 7700000088)
*Через материнскую компанию: ООО «Холдинг» → ООО «АКМЕ-ПРОМ»*

| Адрес | Вид | КН | Площадь, м² | Founder-chain | Источник |
|---|---|---|---|---|---|
| ... | ЗУ | 61:44:0050706:33 | 2 000 | АКМЕ-ПРОМ → Холдинг (заложен) | [^3] |

## §4. С залогом и объекта, и долей бенефициаров
...

<details>
<summary>Источники (служебный блок)</summary>

[^1]: ЕГРН от 2026-04-15, doc_id=ee_a1b2c3d4
[^2]: ЕГРН от 2026-04-15, restrictions, doc_id=ee_a1b2c3d4
[^3]: ЕГРЮЛ ООО Холдинг от 2026-04-12, Обременения доли, doc_id=eul_b2c3d4e5

</details>
```

### §8.5 Подменю 3: DOCX-конвертация

Показывает список MD-файлов в `<project>/reports/` с timestamp ≥
session-start. Чекбоксы → конвертация → результат рядом с MD-файлом.
Stdout-сообщение: `Использован канал: python-docx | LibreOffice | MS Word`.

### §8.6 Выход

Перед выходом — если есть несконвертированные отчёты, повторно
предлагается конвертация (`Y/n`).

### §8.7 Timestamp

`<ts> = YYYYMMDD_HHMMSS` (локальная зона), **одинаков** для всех файлов
одной сессии CLI (одна сессия = одна точка T). Это позволяет
объединить файлы одной сессии в архив для отправки руководству.

---

## §9. DOCX Conversion Util — `parser/utils/md_to_docx.py`

### §9.1 API

```python
def md_to_docx(md_path: Path, out_path: Path | None = None) -> tuple[Path, str]:
    """
    Конвертирует MD → DOCX.

    Returns (out_path, channel) где channel ∈ {"python-docx", "libreoffice", "ms-word"}.
    Raises RuntimeError если ни один канал недоступен.
    """
```

### §9.2 Detection порядок

```
1. python-docx + markdown (offline, pure-Python):
   - markdown lib → HTML
   - htmldocx или mini-HTML2DOCX converter → DOCX
   - footnotes преобразуются в endnotes-абзацы
   - таблицы и заголовки сохраняются
   - <details> → раскрытый параграф с heading "Источники"

2. LibreOffice (если установлен):
   - shutil.which("soffice") или ("libreoffice")
   - На Win10 typical paths: C:\Program Files\LibreOffice\program\soffice.exe
   - subprocess: soffice --headless --convert-to docx --outdir <dir> <md>

3. MS Word (Win-only):
   - pywin32 (win32com.client.Dispatch("Word.Application"))
   - Documents.Open(md_path).SaveAs2(out_path, FileFormat=16)
   - Закрытие через Application.Quit()
```

### §9.3 Логирование

Stdout-сообщение «Использован канал: X». Если первый канал упал с
exception — переход к следующему, исключение логируется в DEBUG.

### §9.4 Тест-план

- CI: только python-docx ветка (linux + python-docx + markdown lib).
- Manual smoke-test на Win10: README с шагами проверки LibreOffice
  и MS Word веток.

---

## §10. Footnotes-Sources Schema

### §10.1 Формат

- **Inline:** `[^N]` в ячейке таблицы или строке текста, где факт.
- **Блок в конце файла:**

```markdown
<details>
<summary>Источники (служебный блок, нумерация для внутрифайлового использования)</summary>

[^1]: <kind> от <date>, <subjects>, doc_id=<doc_id>
[^2]: ...

</details>
```

### §10.2 Поведение в рендерах

- **GitHub Markdown:** `<details>` свёрнут по умолчанию (как и задумано).
- **DOCX через python-docx:** `<details>` рендерится как раскрытый параграф
  с заголовком "Источники" и списком footnote-описаний.
- **LibreOffice/Word import:** MD импортируется через стандартный фильтр;
  `<details>` обычно сохраняется как параграф.

### §10.3 Pipeline нумерации в скрипте

```python
class SourceTracker:
    def __init__(self):
        self._map: dict[str, int] = {}    # source_id → footnote_n
        self._descs: list[str] = []       # порядок появления

    def ref(self, source_id: str, description: str) -> str:
        if source_id not in self._map:
            self._map[source_id] = len(self._descs) + 1
            self._descs.append(description)
        return f"[^{self._map[source_id]}]"

    def render_block(self) -> str:
        if not self._descs:
            return ""
        lines = ["<details>", "<summary>Источники (служебный блок, "
                 "нумерация для внутрифайлового использования)</summary>", ""]
        for i, desc in enumerate(self._descs, 1):
            lines.append(f"[^{i}]: {desc}")
        lines.append("")
        lines.append("</details>")
        return "\n".join(lines)
```

### §10.4 source_id format

| Тип источника | source_id |
|---|---|
| Документ из `documents.json` | `doc:<doc_id>` (например `doc:ee_a1b2c3d4`) |
| Строка ОСВ-выгрузки | `osv:row_<N>` |
| Запись в `structure.json` без явного документа | `structure:<key>` |
| ЕГРЮЛ-обогащение в `enriched.json` | `enrich:<ben_key>` |

---

## §11. Acceptance Criteria

Для v1 (PR-γ + PR-δ):

1. На любом валидном `structure_<slug>.json` (с опциональным
   `documents.json`) — генерируется оба отчёта без ошибок.
2. **Unit-тесты (4 + 2):**
   - `test_resolve_state_no_documents` — fallback на structure as-is.
   - `test_resolve_state_extract_only` — базовый snapshot без overlay.
   - `test_resolve_state_overlay_active` — snapshot + overlay активен.
   - `test_resolve_state_overlay_absorbed` — overlay поглощён новой
     выпиской → не применяется.
   - `test_founder_chain_pledge_found` — есть залог в материнской ЮЛ.
   - `test_founder_chain_pledge_with_cycle` — циклы безопасны.
3. **Integration:** mini-fixture (`parser/scripts/dev/make_mini_fixture.py`
   с расширением — синтетические `documents.json` и `enriched.json` с
   pledge-цепочкой) → запуск `09_v1` end-to-end → проверка обоих MD.
4. **DOCX-конвертация:** CI — только python-docx ветка; Win10 manual
   smoke-test описан в README скрипта.

---

## §12. Test Plan (e2e для будущих PR)

```bash
# PR-β: documents.json schema + validator
python3 -m pytest parser/tests/test_documents_schema.py -v

# PR-γ: 09_v1 пункт 2 (залоги)
python3 parser/scripts/dev/make_mini_fixture.py --with-pledge-chain --out /tmp/test_project
python3 parser/scripts/pirushin_sosn_rocha_09_make_reports_v1.py /tmp/test_project --as-of 2026-04-15
# Ожидание: /tmp/test_project/reports/report_pledges_<ts>.md существует
# Проверка содержимого: 4 секции, footnotes присутствуют.

# PR-δ: пункт 1 (ОСВ) + md_to_docx
python3 parser/scripts/dev/make_mini_fixture.py --with-osv --out /tmp/test_osv
python3 parser/scripts/pirushin_sosn_rocha_09_make_reports_v1.py /tmp/test_osv
# Меню → 1 → файл создан → меню → 3 → DOCX создан.

python3 -m pytest parser/tests/test_md_to_docx.py -v
```

---

## §13. Open Questions (будущие итерации)

1. **Bitemporal extension** — добавить `effective_at` (когда факт случился
   в реальности) vs `recorded_at` (когда узнали). Требуется для
   late-arriving документов (юр.факт случился раньше, чем мы получили
   подтверждение). Spec-bump v2.
2. **State-tags машинное извлечение** — NLP/regex по комментариям ОСВ и
   описаниям ЕГРН. Спецификация v2 (отдельный документ).
3. **Multi-source conflict resolution** — две выписки той же даты с
   разными restrictions. v1 fails-fast; v2 — interactive prompt.
4. **04_nspd_graph styling для документ-узлов** — чёрные точки с
   наименованием/№/датой и ссылкой на JPG (по требованию пользователя).
   S6+ wishlist; либо S6+ task для команды B (см. CORRESPONDENCE/012 §4
   wishlist).
5. **Viewer-side UI timeline** — slider дат → постмесседж в graph для
   обновления состояния узлов. S7+; требует wire-инвариант в KMZ →
   MAJOR bump CONTRACT_KMZ.
6. **DB-миграция полная**: таблицы `documents`, `document_effects`,
   `state_tags` в `parser/egrn_parser/db/schema.sql`. В v1 — только
   JSON sidecar + индексер.

---

## §14. Implementation Order (декомпозиция последующих PR)

| PR | Что | Зависимости |
|---|---|---|
| **PR-α** *(этот)* | spec в `dev/SPEC_TEMPORAL_REPORTS.md` + пост 013 + §9 контракта (informative bullet) | — |
| **PR-β** | `documents.json` JSON-схема + validator + 4 unit-теста + `make_mini_fixture.py` extension (флаги `--with-pledge-chain`, `--with-osv`, `--with-overlay`) | α |
| **PR-γ** | `09_make_reports_v1.py` (только пункт 2 меню — залоги; ОСВ — `--unimplemented`); `SourceTracker` util; интеграция с `resolve_state` и `founder_chain_has_pledge` | β |
| **PR-δ** | пункт 1 меню (ОСВ-сверка); `parser/utils/md_to_docx.py` util; пункт 3 меню (DOCX-конвертация) | γ |
| **PR-ε** | state-tags v2 — расширенный namespace handling + 1 ingester (например, парсер юр.состояния из ОСВ-комментариев) | δ |

Владелец сам решает приоритет и порядок PR-β..ε; spec — отправная точка.

---

## §15. Reuse существующих компонентов

| Что | Где | Как используется |
|---|---|---|
| Интерактивный `ask`/`ask_yn` pattern | `parser/scripts/pirushin_sosn_rocha_052_make_structure_v2_2.py` | Копируем в `09_v1` |
| Детектор `project_root` | 052_v2_2 (search `structure_*.json`) | Копируем в `09_v1` |
| Чтение `enriched.json` / `enriched_*.json` | 052_v2_2 `load_enriched_extras` (canonical-приоритет, hotfix PR #27/#28) | Импортируем напрямую |
| `right_category='encumbrance'` (залоги объекта) | `parser/egrn_parser/db/schema.sql` view `v_pledges_prohibitions` | Источник для §8.4 §2/§4 |
| `beneficiaries[*]["Обременения доли"]` (залоги долей) | `enriched.json` schema, parsed by `03_enrich_v17.py` | Источник для §8.4 §3 |
| `kind=founder` edges | `parser/scripts/04_nspd_graph_v14.py` | Валидатор parent-pointer'ов в §7 |
| JPG EXIF UserComment schema | `docs/EXIF_USERCOMMENT_SCHEMA.md` v1 → v1.1 (добавить `doc_id`) | §4.4 |
| ОСВ XLSX parser | внутри 052_v2_2 (счета 01.01/01.03/01.К/08) | Источник для §8.3 |
| append-only correspondence | `docs/CORRESPONDENCE/INDEX.md` | Пост 013 |

---

## §16. Контракт CONTRACT_KMZ.md — что меняется

**Ничего wire.** В §9 S6+ добавляется informative bullet:

> Snapshot-overlay temporal model + `documents.json` registry для отчётов
> по проекту (parser-internal, ОСВ-сверка + залоговая таблица); см.
> `dev/SPEC_TEMPORAL_REPORTS.md` и `docs/CORRESPONDENCE/013-parser-temporal-reports-spec.md`.

**SemVer не двигается** (parser-internal, не wire-инвариант).

---

— parser-team (A), 2026-05-24
