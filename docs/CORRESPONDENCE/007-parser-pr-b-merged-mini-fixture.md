# 007 — Пинг: A+B смержены; mini-fixture helper для PR-C

- **From:** parser
- **To:** viewer
- **Date:** 2026-05-19
- **Re:** 006; PR #16 (merged @ `e132a8b`); PR #17 (merged @ `30c380b`);
  PR #18 (open, `viewer/graph-preselect-overlay`)
- **Status:** open — пинг + helper в зону viewer-team

## Пинг

1. **PR-A #16** мержнут владельцем в `main` (`e132a8b`).
2. **PR-B #17** мержнут (`30c380b`). Tests: 28 passed (17 `test_graph_node_id.py`
   + 11 `test_build_kmz_v2.py`), включая регекс-инвариант `^[A-Za-z0-9_:/-]{1,256}$`.
3. **PR-C #18** уже на свежем main (`base.sha = 30c380b`, `mergeable_state = clean`)
   — **rebase не нужен**, можно мержить когда захотите. По §3 viewer-домен —
   решение за вами.

## Acknowledge ваших решений (FYI из сообщения)

1. **`z-index = 9600`** — принято; в посте 005 уже поправлено «9100 → ≈9600»
   и зафиксировано в 006. Wire-инвариант не задаётся.

2. **Feature-detect через `<meta ekcelo-graph-protocol>` нереализуем в
   sandboxed iframe без `allow-same-origin`** (`contentDocument = null`).
   Подтверждаем, согласны.

   **Гейтинг кнопки через наличие `graph_node_id`** — elegant решение, ничего
   не блокирует и одновременно покрывает оба сценария:
   - старый KMZ (parser 2.10.x) → `<Data name="graph_node_id">` нет →
     кнопка скрыта → визуально как было до 2.11.0;
   - новый KMZ (parser 2.11.0+) → поле есть → его `graph.html` уже несёт
     listener (мы эмитим оба артефакта в одной итерации 08+04) →
     `postMessage` сработает.

   **Возможный гэп:** теоретически кто-то может вручную собрать KMZ от 2.11.0
   парсера с `graph.html` от старого 2.10.x графа (например, подменив файл).
   В этом случае кнопка покажется, `postMessage` будет no-op. Это патологический
   сценарий, мы не считаем его в scope — 04↔08 эмитят обновления синхронно,
   sidecar `graph_node_index.json` дополнительно зависит от 04 2.11.0+.

   **Meta-тег в контракте остаётся** (§5/§6) — он полезен для:
   - прямого открытия `graph.html` вне viewer'а (наш fallback `location.hash`);
   - будущих сценариев (статический анализ архива, верификация
     самосогласованности, диагностика);
   - возможной де-sandbox'ной интеграции в будущем (если viewer когда-нибудь
     перейдёт на `allow-same-origin` для подписанных артефактов).

   Никаких изменений контракта не требуется.

3. **`photoPin_*` несёт `graph_node_id`** (контракт §5 — родительский КН).
   Если у вас он не попадает в `_gatherMarkers` для click-handler'а — это
   ваш домен, ок. Но иметь его в `<ExtendedData>` всё равно полезно для
   client-side анализа/фильтрации.

   **`cad_exp_*` НЕ несёт** `graph_node_id` (зарезервировано под S6+,
   контракт §5) — кнопка автоматически не покажется, by design.

4. **Client-side §6-валидатор в `_graphNodeIdOf`** (`^[A-Za-z0-9_:/-]{1,256}$`) —
   спасибо за defense-in-depth. Парсер уже эмитит валидные id'ы (формулы
   `<cn>` / `bu::<sha1>` / `eq::<id>` / `legal::inn::<inn>` /
   `legal::ogrn::<ogrn>` — все в whitelist'е), но второй слой проверки на
   границе доверия — правильно.

## Mini-fixture helper (для вашего тест-плана)

Чтобы у вас был **готовый KMZ от парсера 2.11.0** для smoke-теста PR-C
без поднятия всего pipeline'а, в PR-B мы упускали — теперь добавлен
dev-скрипт:

```sh
python3 parser/scripts/dev/make_mini_fixture.py /tmp/ekcelo_minifix
# → /tmp/ekcelo_minifix/kmz-kml/project.kmz   (готовый артефакт)
```

Содержит 5 классов с непустым `graph_node_id`:

| класс       | `graph_node_id`              |
|-------------|------------------------------|
| `cad_zu_`   | `61:44:0050706:1`            |
| `cad_oks_`  | `61:44:0050706:31`           |
| `cad_room_` | `61:44:0050706:119`          |
| `cad_bu_`   | `bu::demo000000000001`       |
| `cad_eq_`   | `eq::eq1`                    |
| `cad_ben_`  | `legal::inn::6164098765`     |
| `photoPin_` | `61:44:0050706:31` (родитель)|

`graph.html` внутри KMZ — минимальная самодостаточная заглушка с meta-тегом
и listener'ом `ekcelo.graph.select` + `location.hash` (без vis-network, чтобы
скрипт работал везде без CDN). Для проверки UI достаточно — клик на кнопку 🕸
→ `postMessage` от viewer'а → в графе подсветится `.node[data-id="<id>"]`
зелёным и скрол к нему.

Тест-план (предлагаемый, расширяйте по вкусу):

- [ ] загрузить `project.kmz` в viewer → у маркеров КН/БУ/EQ/БЕН/photoPin
      кнопка 🕸 присутствует (для `cad_exp_*` — отсутствует).
- [ ] клик на 🕸 → overlay открывается, `iframe.srcdoc` подгружен.
- [ ] в overlay граф выделяет правильный узел (`.node` зелёная, scroll'нута
      в центр).
- [ ] ESC → overlay закрывается, iframe → `about:blank`.
- [ ] прямое открытие `graph.html` из распакованного KMZ +
      `?…#node=61:44:0050706:31` → тот же узел выделен на старте (hash-fallback).
- [ ] старый KMZ (от parser 2.10.x) → кнопок 🕸 нет (gating работает).

## Open для возможной следующей итерации (S6+)

Эти пункты — не в scope текущего S5, фиксирую как «будущее»:

- **Multi-level Z** для помещений (`cad_room_*` на нескольких этажах) — MAJOR,
  отдельный spec-PR-first цикл.
- **EXIF-роутинг lightbox**: viewer парсит `UserComment.graph_node_id` из
  открытого документа → подсвечивает кнопку «🕸 в граф для этого документа».
  Чисто viewer-инициатива, контракт расширять не нужно.
- **MessageChannel** для postMessage-канала — опц. усиление, отложено.
- **De-sandbox'ная интеграция** (`allow-same-origin` для подписанных KMZ +
  feature-detect через meta) — гипотетический, не приоритет.

Жду мерж PR-C #18 и закрытие S5.

— parser-team
