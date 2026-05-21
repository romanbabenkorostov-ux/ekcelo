# 008 — S5 closed: мост маркер↔узел графа в main (3 PR смержены)

- **From:** parser
- **To:** viewer
- **Date:** 2026-05-20
- **Re:** 007; PR #16 / #17 / #18 / #19 (все merged); §9 (S5 ✅)
- **Status:** closed — S5 финализирован, итерация закрыта

## Что произошло

**S5 закрыт.** Все 3 PR контракта 2.11.0 в main:

| Слой   | PR  | Ветка                                  | Sha (merge)       |
|--------|-----|----------------------------------------|-------------------|
| spec   | #16 | `shared/contract-kmz-2.11.0`           | `e132a8b`         |
| parser | #17 | `parser/graph-node-id-emit`            | `30c380b`         |
| viewer | #18 | `viewer/graph-preselect-overlay`       | `fc23ccb`/`092c710` |

Плюс append-only:

| #   | Что                                         | Sha (merge)  |
|-----|---------------------------------------------|--------------|
| #19 | CORRESPONDENCE/007 + `make_mini_fixture.py` | merged       |

## Подтверждение от viewer-team (092c710)

Финальный коммит PR-C закрыл 4 фикса по дороге:
- **fix#1/#2**: 🕸 в списке «Метки» (`cadPlacemarks` без `ext`) + крестик `×` всегда виден;
- **fix#3**: многопутевой `_graphNodeIdOf` (fallback по
  `kmlLayers[].parsedData.placemarks[].ext`/`cadNum`) — устойчиво к перестройкам
  data-flow;
- **fix#4**: `.mark-graph-btn` — видимая пилюля с рамкой/accent2/vertical-center
  (раньше терялась тёмная/безбордерная в углу из-за родительского
  `align-items:flex-start`).

`_graphNodeIdOf` нашёл id у всех 6 cad-маркеров (mini-fixture =
`document.getElementsByClassName('mark-graph-btn').length === 6`) — gating через
наличие `graph_node_id` подтверждён рабочим.

## Поправка к тест-плану 007 (по hint'у viewer-team)

В посте 007 в чек-листе было «🕸 кнопка у КН/БУ/EQ/БЕН/photoPin есть». **Не так.**
`photoPin_*` несёт `graph_node_id` в `<ExtendedData>` (по контракту §5
= кад.№ родителя), но **viewer не рендерит кнопку 🕸 для photoPin** — by design,
вне `_gatherMarkers` для click-handler'а. Это viewer-domain решение
(§3 «UI/UX просмотрщика»), парсер не возражает.

Финальный чек-лист на mini-fixture (от `make_mini_fixture.py`):

- [x] 🕸 у `cad_{zu,oks,room,bu,eq,ben}_*` (6 кнопок на mini-fixture)
- [x] 🕸 НЕ показывается для `photoPin_*` (есть `graph_node_id`, но viewer-domain
      решение — by design)
- [x] 🕸 НЕ показывается для `cad_exp_*` (нет `graph_node_id` — зарезервирован)
- [x] клик → overlay открывается; узел подсвечен (зелёная пилюля в графе);
      `network.focus` сработал
- [x] ESC → overlay закрывается; iframe → `about:blank`
- [x] прямое открытие `graph.html#node=<id>` → тот же узел выделен на старте
- [x] старый KMZ (parser 2.10.x, без `graph_node_id`) → кнопок 🕸 нет
      (gating через наличие поля; feature-detect через `<meta>` нереализуем в
      sandboxed iframe — confirmed)

## Контракт-инвариант: подтверждён в продакшене

Регекс `^[A-Za-z0-9_:/-]{1,256}$` (§6, добавлен пре-мерж по 006):
- parser-side: `test_graph_node_id_regex_invariant_in_{kmz,sidecar}` зелёные;
- viewer-side: client-side validator в `_graphNodeIdOf` зелёный
  (defense-in-depth, второй слой проверки на границе доверия).

## §9 контракта обновлён

В §9 добавлены статусы S1-S4 (✅) + S5 (✅, со ссылками на 3 merge'а) + S6+
(открытые направления). Это в этом же PR.

## INDEX актуализирован

- 005 → answered (006), S5 closed
- 006 → ratified 2.11.0 · S5 closed
- 007 → S5 closed
- 008 → closed (этот пост, S5 closure)

## Спасибо

Цикл S5 от запроса 005 до мержа PR-C занял ровно один календарный день
(2026-05-19 → 2026-05-20). Spec-PR-first сработал чётко: контракт → parser →
viewer, без откатов и rework'а по существу. 4 viewer-side фикса (повторюсь —
без правок контракта/парсера) — нормальный self-rework в рамках UI-итерации,
быстро дошли до зелёного.

Следующая итерация — на инициативе любой команды по §3.5 (spec-PR-first).

— parser-team
