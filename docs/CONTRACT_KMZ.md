# CONTRACT_KMZ — единый источник истины формата KMZ (Ekcelo)

**Статус:** Ратифицирован (PR #1, мерж 2026-05-18).
**Версия контракта:** 2.11.0 · **SemVer-политика:** см. §4.
**Дата:** 2026-05-19 · **Арбитр:** владелец репозитория `romanbabenkorostov-ux`.
**Тех-тело (нормативная часть):** `docs/KML_INGESTION_SPEC_for_viewer_team_v2.10.0.md`
(pin SHA `22407643969f0c66875b9b86e376d265e5b53987`).
**Информативно (parser-internal, НЕ контракт):** `docs/CHANGELOG_052_v1_to_v2.md`.

> Этот файл — **источник истины** для формата обмена между командой parser и
> командой viewer. При расхождении кода и этого документа прав документ.
> Изменения — только через PR в этот файл (см. §3, «spec-PR-first»).

---

## 1. Назначение

Зафиксировать формат и правила его эволюции так, чтобы выход парсера и вход
просмотрщика были совместимы детерминированно, а изменения согласовывались
обеими командами до написания кода.

## 2. Scope и границы (контрактная поверхность)

**Контрактная поверхность — ТОЛЬКО KMZ-архив:**

```
project.kmz (ZIP, deflate):
├── doc.kml              (+ <ExtendedData>, <atom:author>, kml_schema_version)
├── images/<f>           (фото из photoPin_*)
├── docs/<f>             (сканы: ЕГРН/свид./техпасп./техплан/ЕГРЮЛ/ЕГРИП)
└── graph.html           (граф связей; самодостаточный статический HTML)
```

**НЕ входит в контракт (parser-internal, меняется парсером свободно):**
`structure_*.json`, `enriched_*.json`, `schema.sql`/БД, промежуточные дампы,
worker/тайлы nspd.gov.ru, файловая структура диска проекта.

Следствие (закрывает повторяющуюся путаницу): изменения формата
`structure_*.json` (например 052 v1→v2: `links.*_ids[]`, `photos[]`,
`z_meters`, `_geometry.extrude`) **не являются изменением контракта** — их
потребляет `pirushin_sosn_rocha_08_build_kmz_v2.py` и уплощает в KMZ. Чеклист
`CHANGELOG_052 §7 «для команды viewer»` относится к гипотетическому
JSON-потребителю; наш viewer читает **только KMZ** и от полей structure.json
не зависит.

## 3. Governance — дуальная мажоритарность

| Домен решения | Мажоритарная команда |
|---|---|
| Состав публикуемых **данных**: классы объектов, обязательные поля, семантика payload, что попадает в выгрузку | **parser** |
| **UI/UX просмотрщика** и совместимость/паритет с **Google Earth Pro** (целевой инвариант: фильтры viewer ≥ GE Pro, в идеале превосходят) | **viewer** |
| Кросс-доменное (данные **и** UI/UX одновременно) | обе; тупик → **владелец репо (финальный арбитр)** |

**Правило «spec-PR-first»** (обязательное):

1. Любое изменение контракта = PR, меняющий **этот файл** (и при необходимости
   тех-тело §5) + bump SemVer (§4).
2. Аппрув мажоритарной по домену команды **+ не-возражение** второй — **до**
   любого кода в parser/viewer. Не наоборот.
3. Кросс-доменное изменение — аппрув обеих; при тупике решает владелец.
4. Окно депрекации: ломающее/удаляемое поле живёт ≥ 1 MINOR-релиза с пометкой
   `DEPRECATED` в §5 и в `<ExtendedData>`-комментарии, прежде чем удаляется в
   MAJOR.
5. PR-метка `contract`; ревьюеры — по одному от каждой команды; мерж — только
   после обоих аппрувов (для кросс-доменных — после решения арбитра, если был
   тупик).
6. **Форма аппрува (single-owner mode).** Пока обе AI-команды действуют под
   одним GitHub-аккаунтом (`romanbabenkorostov-ux`), GitHub блокирует
   formal `Approve` review с тем же identity, что у автора PR
   («cannot approve own pull request»). В этом режиме «аппрув команды» = одно
   из эквивалентных подтверждений, фиксируемое в журнале PR:
   - formal `Approve` review (когда ревьюер и автор PR — разные GitHub-аккаунты);
   - либо `COMMENT`-review с явным чеклистом `[x]` по пунктам, подписанным
     командой («parser-team»/«viewer-team»);
   - либо запись в `docs/CORRESPONDENCE/NNN-*.md` с тем же чеклистом и
     ссылкой на PR.

   Мерж выполняет владелец репозитория (он же арбитр). При подключении
   реальных коллабораторов / выдаче отдельных PAT агентам — этот пункт
   автоматически становится излишним и заменяется требованием formal
   `Approve` (без правки §3.1–§3.5). Branch protection rule на `main`
   («Require pull request reviews») включается только после перехода на
   раздельные identity, иначе блокирует владельца.

## 4. Версионирование

SemVer `MAJOR.MINOR.PATCH` для контракта:

- **MAJOR** — ломающее изменение wire-формата (удаление/переименование
  префикса, обязательного ключа, смена семантики геометрии).
- **MINOR** — аддитивно и обратносовместимо (новый префикс/папка/опциональный
  ключ; старый viewer переживает через fallback).
- **PATCH** — уточнение текста, без изменения байтов на проводе.

Генератор обязан штамповать `kml_schema_version` в
`<Document><ExtendedData>`. Viewer читает его и включает стадийное поведение
**P0/P1/P2** (см. тех-тело §A.8/§A.10). Матрица совместимости — §8.

## 5. Нормативное тех-тело (по ссылке, не дублируется)

Полная нормативная спецификация базы 2.10.x — `docs/KML_INGESTION_SPEC_for_viewer_team_v2.10.0.md`
@ SHA `22407643969f0c66875b9b86e376d265e5b53987`. Аддитивные изменения 2.11.0 описаны
**в этом файле** ниже (новый pin тех-тела не выпускается — base + добавления). Кратко,
что зафиксировано (изменять только через §3):

- **9 префиксов** `styleUrl`/`Style id` (подстрока — сигнал типа):
  `cad_zu_`, `cad_oks_` (только здания), `cad_room_`, `cad_str_`, `cad_ons_`,
  `cad_bu_`, `cad_eq_`, `cad_ben_`, `cad_exp_` + `photoPin_` (фото).
- **10 `<Folder>`** верхнего уровня в строгом порядке; у «Фотографии» —
  4 подпапки.
- `<description>` — пары `Ключ: значение; ` (точка-с-запятой+пробел), без HTML.
  Кад.№ — токеном в `<name>` и продублирован в description.
- Фото: `photoPin_*` Placemark + `<Point>`; файл — ключ
  `Ссылка_фото_<i>: images/<f>` или `Файл:`; **без `<img>` в description**.
  Документы — `Ссылка_документ_<i>: docs/<f>`.
- `<ExtendedData>`: `object_type`, `cad_number`, `parent_cad`, `bu_id`,
  `ben_inn`, `z_meters_top`, `floors_above`, `schema_version`, `z_source`.
- Геометрия: одна на Placemark; `lon,lat[,Z]`; 3-й элемент Z = extrude
  (3 м/этаж). **2D-viewer (Leaflet) Z игнорирует — это контрактно допустимо**;
  Google Earth Pro использует Z для объёмов.
- Объект без геометрии (`cad_ben_*` без `<Point>`) — допустим: list-only.
- `<atom:author>` + `kml_schema_version` в `<Document>`.
- Граф: запись архива KMZ ОБЯЗАНА называться ровно `graph.html` (viewer ищет
  по `/(^|\/)graph\.html$/i`). Имя файла-источника в пайплайне парсера
  (напр. `graph_<source>_<ts>.html`) — parser-internal и контрактом не
  ограничивается; `08_build_kmz_v2` нормализует его в `graph.html` при упаковке.
- **(2.11.0+)** `<ExtendedData>` каждого Placemark с префиксом
  `cad_{zu,oks,room,str,ons,bu,eq,ben}_*` или `photoPin_*` СОДЕРЖИТ опциональный
  ключ `graph_node_id` (string, непустой), точно равный `id` соответствующего узла
  в `graph.html`. Для `photoPin_*` значение = кад.номер родительского КН. Для
  `cad_exp_*` ключ зарезервирован под будущие расширения (геопривязка, инициаторы
  новых КН), сейчас не эмитится. Значение непрозрачно для viewer'а — он передаёт
  его в граф как opaque string.
- **(2.11.0+)** `graph.html` ПОДДЕРЖИВАЕТ pre-selection узла двумя каналами:
  (i) `window.addEventListener('message', e => /* {type:'ekcelo.graph.select', nodeId} */)` —
      основной канал, viewer отправляет после `iframe.onload`;
  (ii) `location.hash = '#node=<urlencoded id>'` — fallback при прямом открытии
       `graph.html` вне viewer'а (например, из распакованного KMZ).
  Граф буферизует входящий nodeId до `network.once('stabilizationIterationsDone')`
  и применяет `network.selectNodes([id])` + `network.focus(id, {scale:1.2, animation:true})`.
- **(2.11.0+)** `graph.html` СОДЕРЖИТ `<meta name="ekcelo-graph-protocol" content="1">` в `<head>`.
- **(2.11.0+)** `kml_schema_version` в `<Document>` ОБНОВЛЯЕТСЯ `2.0` → `2.1` (MINOR wire-bump).
- **(2.11.0+, информативно — parser-internal, НЕ контрактный инвариант).** JPG-файлы
  внутри `docs/<f>` и `images/<f>` ОПЦИОНАЛЬНО несут `graph_node_id` в EXIF
  `UserComment` (JSON-payload, поле `graph_node_id`) — то же значение, что у узла
  графа, к которому документ/фото привязан. Источник истины — sidecar
  `_data/graph_node_index.json` от `04_nspd_graph_v14.py`; генерируется
  `07_init_project_v1.py` при конвертации PDF→JPG и при сортировке
  `Не_распределено/`. Поле parser-internal: viewer не обязан парсить EXIF JPG,
  но при наличии может использовать для синхронизации «открыть документ ↔
  перейти на узел графа». Wire-формат KMZ от этого поля не зависит.
- Детерминизм: одинаковый вход → побитово идентичный `sha256(project.kmz)`.

## 6. Контрактные инварианты (CI/линт обеих сторон)

- [ ] У каждого Placemark `styleUrl` с одним из 9 префиксов; `Style id` уникален.
- [ ] Кад.№ `\b\d{2}:\d{2}:\d{2,8}:\d{1,8}(?:/\d+)?\b` в `<name>` (где
      применимо) и в description ключом `Кадастровый номер:`. (3-й блок
      2–8 цифр; опциональный суффикс `/N` — часть/контур.)
- [ ] `<description>` — пары `Ключ: значение; `, без HTML, без `<img>`.
- [ ] Координаты `lon,lat[,Z]`; полигон замкнут (≥4 точки); WGS84.
- [ ] 10 `<Folder>` в фиксированном порядке; префикс ↔ Folder согласованы.
- [ ] Все `images/<f>`/`docs/<f>` из description физически в архиве.
- [ ] **`graph.html` самодостаточен** — без внешних CDN/ссылок/ресурсов
      (требование к парсеру; viewer рендерит в `<iframe sandbox="allow-scripts">`
      без `allow-same-origin`); запись архива названа ровно `graph.html`.
- [ ] `kml_schema_version` присутствует в `<Document>` и распознаётся viewer.
      Это версия wire-схемы генерации KMZ (напр. `2.0`), НЕ SemVer этого
      документа; viewer не гейтит на равенстве с версией контракта
      (классификация — по префиксам `styleUrl`).
- [ ] Идемпотентность: 2 прогона генератора на одинаковом входе → одинаковый
      `sha256(project.kmz)`.
- [ ] Старый KMZ предыдущего MAJOR открывается текущим viewer (через fallback).
- [ ] **(2.11.0+)** У каждого Placemark с префиксом `cad_{zu,oks,room,str,ons,bu,eq,ben}_*`
      или `photoPin_*` в `<ExtendedData>` присутствует `graph_node_id` (непустая строка).
      Исключение: `cad_ben_*` без `<Point>` (list-only) — допускается без `graph_node_id`,
      если у бенефициара нет идентификатора (ИНН/ОГРН/имя ФЛ).
- [ ] **(2.11.0+)** Для каждого значения `graph_node_id` существует узел с
      `id == значение` в `graph.html` (cross-match инвариант, проверяется тестом).
- [ ] **(2.11.0+)** `<meta name="ekcelo-graph-protocol" content="1">` присутствует в
      `<head>` `graph.html`.
- [ ] **(2.11.0+)** `graph.html` реализует listener `message`
      (`ekcelo.graph.select`) и читает `location.hash` на старте; апплай отложен до
      `stabilizationIterationsDone`.
- [ ] **(2.11.0+)** `kml_schema_version` в `<Document>` = `2.1`.
- [ ] **(2.11.0+)** Формат `graph_node_id`: непустая строка, длина ≤ 256, символы
      `[A-Za-z0-9_:/-]+` (regex `^[A-Za-z0-9_:/-]{1,256}$`). Защищает hash-fallback
      (`#node=<urlencoded id>`) и детерминирует cross-match. Текущие формулы 04
      соответствуют: `<cn>` (КН), `bu::<sha1>`, `eq::<id>`, `legal::inn::<inn>`,
      `legal::ogrn::<ogrn>`.

## 7. Открытые вопросы — зафиксированные ответы

1. **Merge в main:** только через PR+ревью, без прямого пуша в main. Порядок:
   ратификация этого файла → PR viewer (`claude/fix-image-tile-gaps-e4cre`,
   коммит `c20fb56`) + PR парсера; конфликт `index.html` решает **viewer**
   (домен UI), parser ревьюит; мерж viewer → затем PR парсера ребейзят.
   Тупик — владелец.
2. **Версионирование/сверка спеки:** подтверждено — viewer реализован под
   `KML_INGESTION_SPEC_for_viewer_team_v2.10.0.md` (SHA `2240764…`, текущий),
   совпадает с `08_build_kmz_v2.py` (`CHANGELOG_052 §6: «Совместим»`). 9
   префиксов / 10 папок / `photoPin_` / `Ссылка_фото_` сверены с исходником
   парсера. Здесь зафиксирован pin.
3. **graph.html:** статический HTML пайплайна парсера (`04_nspd_graph` из
   `enriched_*.json`+`structure_*.json`), бандлится `08_build_kmz_v2` из
   `<root>/_data/graph.html`. Контрактное требование — только §6
   (самодостаточность). Источник данных — parser-internal.
4. **052-v2 поля:** parser-internal (см. §2). Доп. раунд viewer не нужен,
   пока поверхность = только KMZ. Парсер: подтвердить KMZ-only.
5. **Реструктуризация каталогов:** отдельный PR `shared/repo-layout`
   (`git mv` без правок кода), руками viewer, **после** связки формата в main,
   **до** разделения ролей. Зоны/процесс — `docs/LETTER_to_viewer_team_publishing_workflow.md`.

## 8. Совместимость и откат

| parser \ viewer | viewer 2.9.x | viewer 2.10.0+ |
|---|---|---|
| KMZ 2.9.x (v1) | полный | полный (легаси `<img>`-путь сохранён) |
| KMZ 2.10.0 (v2) | P0: новые типы → fallback в ОКС/Пояснения; фото v2 не видны | полный (9 типов, миниатюры, граф) |

Откат контракта: revert PR в этом файле + согласованный revert кода обеих
сторон; `kml_schema_version` позволяет viewer-у не падать на смешанных входах.

## 9. Порядок интеграции (живёт здесь, обновляется через §3)

- **S1** Ратификация этого файла (PR `shared/contract-kmz`, аппрув обеих). ✅
- **S2** Merge формата в main: PR viewer `c20fb56` + PR парсера (см. §7.1).
  → связка формата зелёная. ✅
- **S3** PR `shared/repo-layout` (git mv → `viewer/`,`worker/`,`schema/`). ✅
- **S4** Разделение ролей/функционала (pro/view/embed) — отдельная итерация
  после S3 (`dev/SPEC_ROLES_VIEWER_EMBED.md`). ✅
- **S5** Мост маркер↔узел графа (контракт 2.10.2 → 2.11.0): `graph_node_id`
  в `<ExtendedData>` + protocol pre-selection (postMessage + hash) +
  `<meta ekcelo-graph-protocol>` + EXIF UserComment (parser-internal). ✅
  PR-A #16 (`e132a8b`), PR-B #17 (`30c380b`), PR-C #18 (`fc23ccb`/`092c710`).
- **S6+** Открытые направления (не в scope ни одной активной итерации):
  multi-level Z для помещений (MAJOR); ingesters ОСВ/ЕГРЮЛ/ЕГРИП;
  EXIF-роутинг lightbox (viewer-инициатива); MessageChannel; de-sandbox;
  визуальное различение `_kind = "ip" | "person" | "legal_text"` в overlay
  графа `04_nspd_graph_*` и пунктирное ребро `kind = "person_to_legal"`
  (parser/viewer overlay UX, не wire; см. CORRESPONDENCE/011);
  snapshot-overlay temporal model + `documents.json` registry для
  отчётов по проекту (parser-internal, ОСВ-сверка + залоговая таблица);
  см. `dev/SPEC_TEMPORAL_REPORTS.md` и CORRESPONDENCE/013.

## 10. Изменения

| Версия | Дата | Что | PR |
|---|---|---|---|
| 2.10.0 | 2026-05-18 | Первичная редакция; абсорбирует v2.10.0-спеку как тех-тело; фиксирует governance и ответы §7 | `shared/contract-kmz` (PR #1) |
| 2.10.1 | 2026-05-18 | PATCH §3.6: легализация формы аппрува для single-owner режима (COMMENT-review с чеклистом ≡ formal Approve, пока обе команды под одним GitHub-аккаунтом); статус → «Ратифицирован» | `shared/contract-kmz-patch-governance` (PR #3) |
| 2.10.2 | 2026-05-18 | PATCH: §6 регекс кад.№ → `\b\d{2}:\d{2}:\d{2,8}:\d{1,8}(?:/\d+)?\b` (3-й блок 2–8 цифр, суффикс части/контура `/N`); §5/§6 — запись KMZ обязана называться ровно `graph.html` (имя источника в пайплайне парсера — parser-internal); уточнён `kml_schema_version` (wire-схема генерации ≠ SemVer документа, viewer не гейтит) | `shared/contract-kmz-patch-2.10.2` |
| 2.11.0 | 2026-05-19 | MINOR: `ExtendedData/graph_node_id` (opaque link маркер→узел графа) для `cad_{zu,oks,room,str,ons,bu,eq,ben}_*` и `photoPin_*`; протокол pre-selection (postMessage `ekcelo.graph.select` + hash `#node=<id>`); `<meta name="ekcelo-graph-protocol" content="1">` в `graph.html`; `kml_schema_version` 2.0 → 2.1; формат `graph_node_id` (ASCII ≤256, `[A-Za-z0-9_:/-]+`, §6 — добавлено пре-мерж по уточнению viewer-team в посте 006); информативный пункт §5 про parser-internal EXIF UserComment.graph_node_id для JPG в `docs/`/`images/`. Аддитивно, обратно-совместимо: viewer 2.10.x просто не показывает highlight-кнопку, парсер 2.10.x генерит KMZ без поля и работает с viewer 2.11.x | `shared/contract-kmz-2.11.0` (PR #16) |
