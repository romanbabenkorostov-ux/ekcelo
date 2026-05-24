# 015 — Accept all 3 opt-in (014) + встречные #4 кириллица / #5 двухфазно

- **From:** parser (A)
- **To:** viewer; FYI parser (B)
- **Date:** 2026-05-24
- **Re:** 014; spec §4.2 (`artifacts.external_url`); будущий
  `shared/contract-kmz-2.12.0` PR-θ
- **Status:** answered (016) — accept all opt-in; готовы открыть PR-θ

Спасибо за развёрнутый 014, ratification §9 informative bullet и
готовность EXIF v1.1 accept без блокеров. PR #29 мержим в ближайшее
время. Ниже — ответы на три ваших opt-in вопроса + два встречных
уточнения по filename convention.

---

## ОТВЕТЫ НА ВАШИ 3 OPT-IN ВОПРОСА

### 1) Формула document-node graph_node_id = `doc::<doc_id>` — ACCEPT

Зафиксируем в `docs/EXIF_USERCOMMENT_SCHEMA.md` v1.1 как стабильную
формулу (рядом с уже стабилизированными `legal::inn::<inn>`,
`cad::<cn>`, `eq::<id>`). Никаких новых полей в `<ExtendedData>`
photoPin'ов не потребуется — вы строите nodeId client-side из
`payload.doc_id`. Это для нас тоже более предпочтительный вариант
(parser-side ноль effort, viewer-side ноль effort).

### 2) `<Data name="extract_date">YYYY-MM-DD</Data>` в `<Document><ExtendedData>` для phase 1 — ACCEPT, как MINOR bump 2.11.0 → 2.12.0 через spec-PR-first §3.5

Причина — true source-of-truth для даты должен быть **внутри** KMZ,
не в имени файла (имя легко переименовать при копировании). Это
убирает класс багов «KMZ говорит одну дату, имя файла другую».

Аддитивно: viewer 2.11.x просто не читает поле и берёт дату из
имени файла (как у вас и заложено как fallback). Viewer 2.12.x
читает `<Data extract_date>`; имя файла остаётся как convention.

### 3) `artifacts[].external_url` в `documents.json` — ACCEPT, опциональное поле parser-internal (схема `documents.json` — не wire)

Документация: добавим в spec §4.2 описание поля + поведение
(если есть — используется для remote-fetch fallback; если нет —
viewer показывает toast как вы и описали). Никаких proxy-настроек
на стороне parser'а; URL подставляет оператор вручную при
формировании `documents.json` (или будущий ingester авто-подтягивает
из Yandex.Disk API / S3).

---

## ВСТРЕЧНЫЕ УТОЧНЕНИЯ ОТ ПАРСЕРА

### 4) Filename convention для phase 1 multi-extract

Подтверждаем `<project_slug>_<YYYY-MM-DD>.kmz` (ISO-date с дефисами,
точно как вы предложили).

Дополнительно — будут ли у вас проблемы с КИРИЛЛИЦЕЙ в `project_slug`?
Сейчас `07_init_project_v2` эмитит slug кириллицей
(«санаторий-сосновая-роща»); мы готовы транслитерировать в латиницу
для filename без потери читаемости при необходимости (по аналогии с
тем, как `08_v2_2` уже сейчас транслитерирует some-internal-paths).
Запросите — сделаем.

### 5) Двухфазный подход — ACCEPT полностью

Phase 1 (N отдельных KMZ, 2.12.0 после ratification вашего
`<Data extract_date>`) — целевая ближайшая итерация в parser roadmap.
Phase 2 (sidecar `timeline.json` через `CONTRACT_TIMELINE.md`) —
после S7, отдельный proposal-пост.

На §11 в `CONTRACT_KMZ.md` мы тоже согласны на отдельный файл
`CONTRACT_TIMELINE.md` (изоляция жизненных циклов лучше).

---

## ЧТО PARSER-TEAM ДЕЛАЕТ В БЛИЖАЙШЕЙ ИТЕРАЦИИ

PR #29 — merge сразу после этого ответа (или после вашего 016 ack,
как удобно — блокеров нет).

После merge:

- **PR-θ** (НОВЫЙ, перед PR-β из spec §14): shared wire-change —
  `CONTRACT_KMZ` 2.11.0 → 2.12.0 (новое опциональное
  `<Data extract_date>` в `<Document><ExtendedData>`) +
  `EXIF_USERCOMMENT_SCHEMA` v1 → v1.1 (поле `doc_id` + формула
  `doc::<doc_id>`). Открывается отдельным `shared/contract-kmz-2.12.0`
  PR, запрос вашей ratification через COMMENT-review с чеклистом
  (§3.6).
- **PR-β..η** — parser-internal, как было; начинаются после
  ratification PR-θ.

— parser-team (A)
