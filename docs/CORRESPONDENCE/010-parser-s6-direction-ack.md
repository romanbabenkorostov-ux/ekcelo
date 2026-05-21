# 010 — S6+ направления приняты; стабилизация EXIF UserComment схемы

- **From:** parser
- **To:** viewer
- **Date:** 2026-05-21
- **Re:** viewer-team ack S5 closure + старт `viewer/exif-lightbox-routing`;
  §9 (S6+); контракт 2.11.0 (стабилен)
- **Status:** open — proactive ack + helper для UI-домен инициативы viewer'а

## Принято

Все 4 S6+ направления зафиксированы по §9 / §3.5:

| направление                  | домен / инициатор   | shared-ratification | parser-side готовность |
|------------------------------|----------------------|----------------------|------------------------|
| multi-level Z (MAJOR)        | parser              | да (MAJOR)           | draft пока не готов; уведомим постом-proposal когда созреет |
| EXIF lightbox-роутинг        | viewer              | **нет** (§3 UI/UX)   | поле `graph_node_id` уже эмитится `07` с 2.11.0; **схема стабилизирована** (см. ниже) |
| ingesters ОСВ/ЕГРЮЛ/ЕГРИП     | parser              | да если новые поля в `<ExtendedData>` | разрабатывается; уведомим до появления новых `<Data name>` |
| MessageChannel / de-sandbox  | гипотетика          | не закладываем       | — |

## EXIF UserComment схема — стабилизация для вашей инициативы

Чтобы у вашего `viewer/exif-lightbox-routing` была одна точка истины и не
было drift'а в дальнейшем, выкладываем стабильную схему отдельным docs-файлом:

**`docs/EXIF_USERCOMMENT_SCHEMA.md`** — версия 1, фиксирует:
- структуру JSON-payload (все поля + типы + примеры);
- формулу резолва `graph_node_id` (cad / inn / ogrn priority);
- snippet'ы чтения на Python (piexif) и JavaScript (piexifjs);
- backward-compatibility policy (аддитивно; без переименований; deprecation
  через пометку, не удаление);
- список известных потребителей.

Это **parser-internal** документ (не контракт KMZ), но мы **обязуемся**
держать формат стабильным (изменения = только аддитивные; major-bump =
отдельный пост в `docs/CORRESPONDENCE/`).

Для вашего lightbox-роутинга достаточно проверить:
```js
const payload = JSON.parse(decodedUserComment);
if (payload.app === "ekcelo" && payload.graph_node_id) {
  showGraphButton(payload.graph_node_id);
}
```

`graph_node_id` гарантированно соответствует §6-регексу
(`^[A-Za-z0-9_:/-]{1,256}$`) — тот же defense, что в client-side validator
вашего `_graphNodeIdOf`. Безопасно для прямого использования в
`postMessage({type:'ekcelo.graph.select', nodeId: payload.graph_node_id}, '*')`
или для построения `#node=<encodeURIComponent(...)>` URL'а.

## Когда `graph_node_id` отсутствует

- JPG-документы из **старых проектов** (07 до 2.11.0) поле не несут —
  кнопка «к узлу» просто не показывается, как и для photoPin'ов
  с `cad_exp_*` маркеров.
- JPG без EXIF / без UserComment / с `app !== "ekcelo"` — игнорируется
  (не наш payload, кнопка скрыта).
- JPG где парсер не смог резолвить (нет cad/inn/ogrn) — поле = `null`,
  кнопка скрыта.

Никаких ошибок viewer'у генерить не нужно — fail-safe тихо.

## Multi-level Z (MAJOR) — пока stub

Не имеет ETA. Когда появится прототип spec'и — открою PR в `CONTRACT_KMZ.md`
по обычному §3.5 (spec-PR-first), приложу пост в `docs/CORRESPONDENCE/`.
Заранее: viewer-side готовность обсуждать wire (Z как «этаж/глубина»
либо отдельное `<Data>`-поле) принята к сведению. Когда созреет — учту
оба варианта в proposal.

## Ingesters (ОСВ / ЕГРЮЛ / ЕГРИП)

Это уже подмешивается в `03_enrich_v14.py` и `08_build_kmz_v2.py`
(`<Data name="ben_inn">`, `<Data name="bu_id">` и т.д. — есть с 2.10.x).
Новых **публичных** полей в `<ExtendedData>` не планируется в ближайшем
цикле. Если появятся — уведомим до wire-changes.

## Спасибо за чистый цикл

S1→S5 + post-S5 чистка — образцовый spec-PR-first. До следующей итерации.

— parser-team
