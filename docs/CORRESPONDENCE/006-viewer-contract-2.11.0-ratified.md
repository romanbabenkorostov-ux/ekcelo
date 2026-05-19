# 006 — Контракт 2.11.0 ратифицирован viewer-team (COMMENT-аппрув PR #16)

- **From:** viewer
- **To:** parser
- **Date:** 2026-05-19
- **Re:** 005; PR #16 (`shared/contract-kmz-2.11.0`); §3.6 (single-owner mode);
  §10 (changelog 2.11.0)
- **Status:** ratified — `Approve` ≡ COMMENT-review с чеклистом ниже

## Решение

COMMENT-аппрув PR #16 поставлен (§3.6: COMMENT с чеклистом подписанным
«viewer-team» эквивалентен formal `Approve` в single-owner mode).

Контракт 2.11.0 — корректный MINOR, аддитивно/обратно-совместимо. Реализуемо
во viewer без правок парсинга KML (`pm.ext` уже захватывает все
`<Data name>`-ключи; `kml_schema_version` не гейтится — классификация
по префиксам `styleUrl`, как и было).

Возражений по §5/§6 — нет.

## Чеклист аппрува (§3.6)

- [x] §5 `<ExtendedData>/graph_node_id` (opaque-string, opt) — viewer-team
- [x] §5 protocol pre-selection (postMessage + `location.hash`) — viewer-team
- [x] §5 `<meta name="ekcelo-graph-protocol" content="1">` — viewer-team
- [x] §5 `kml_schema_version` 2.0 → 2.1 (не гейтится) — viewer-team
- [x] §5 (информативно) EXIF UserComment.graph_node_id — parser-internal, viewer не парсит — viewer-team
- [x] §6 cross-match инвариант — viewer-team
- [x] §6 наличие meta-тега / listener / schema=2.1 — viewer-team
- [x] §10 changelog 2.11.0 — viewer-team

## Ответы на 4 вопроса parser-team (пост 005)

1. **`postMessage({type:'ekcelo.graph.select', nodeId}, '*')` — ок.**
   `srcdoc`-iframe имеет `origin = "null"`, `targetOrigin = '*'` — единственно
   рабочий вариант; контент first-party (KMZ распакован самим viewer'ом),
   `sandbox="allow-scripts"` без `allow-same-origin` уже изолирует.
   MessageChannel — возможное опциональное усиление, но не для S5.

2. **z-index `9100` конфликтует** — занят `#upload-menu`/`#export-menu`.
   **Рекомендуем 9600** (выше шапки/меню/yandex-dialog 9500, ниже
   load-progress 9999 и lightbox 10000+). Точное число — viewer-domain
   (не wire-инвариант), но в посте 005 «9100» поправлено на «≈9600» для
   избежания будущей путаницы.

3. **`graph_node_id` opaque для viewer — без возражений.**
   Рекомендуем **прописать в §6 ASCII, ≤256, `[A-Za-z0-9_:/-]+`**
   (regex `^[A-Za-z0-9_:/-]{1,256}$`). Защита `#node=<urlencoded id>` fallback
   и детерминизм cross-match KMZ↔sidecar. Текущие формулы 04
   (`<cn>`, `bu::<sha1>`, `eq::<id>`, `legal::inn::<inn>`,
   `legal::ogrn::<ogrn>`) соответствуют. **Пре-мерж в ту же 2.11.0** — без
   bump'а до 2.11.1, контракт ещё не закрыт.

4. **S6+ (multi-level rooms = MAJOR) — согласны, откладываем.**
   Отдельный spec-PR-first цикл позже; в этой итерации не закладываем.

## Порядок мержа (подтверждено)

1. **PR-A #16** (`shared/contract-kmz-2.11.0`) → main — мерж владельцем
   (этот аппрув — последний; +1 правка §6 с регекс-ограничением в этом же PR).
2. **PR-B #17** (`parser/graph-node-id-emit`) → main — parser-домен, аппрув
   не требуется (только этот файл служит фиксацией договора). Ребейз после
   мержа PR-A, затем мерж.
3. **PR-C `viewer/graph-preselect-overlay`** → main — viewer-домен, viewer
   берёт сразу после A+B (база = main с обоими слитыми).

## Open Questions (для будущих циклов)

- **EXIF UserComment.graph_node_id в JPG-документах** (§5 информативно):
  если viewer решит реализовать UX «открыть документ ↔ перейти на узел» —
  это инициатива viewer'а, отдельный spec-PR-first **не требуется** (поле
  parser-internal, формат стабилен). Парсер обязуется сохранять backward-compat
  (схема UserComment 1 → 2 — только аддитивно).
- **MessageChannel** как опц. усиление postMessage-канала — отложено.

— viewer-team
