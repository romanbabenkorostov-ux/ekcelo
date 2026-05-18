# parser/vendor/ — сторонние библиотеки, бандленные локально

Эта папка содержит сторонние JS-библиотеки, **встраиваемые** парсером в
генерируемые HTML-артефакты (`graph.html`). Цель — выполнить контрактный
инвариант **`CONTRACT_KMZ §6` №7 «`graph.html` самодостаточен»**: при
открытии HTML офлайн / в `<iframe sandbox>` без сети — никаких сетевых
запросов не выполняется.

## vis-network 9.1.9

- **Файл:** `vis-network-9.1.9.min.js` (688 911 байт)
- **sha256:** `f53f833ddb9bf97efe856bb0637d4fe88f39e39999c7e94a4b8afc8de8a1a2e5`
- **Источник:** `npm pack vis-network@9.1.9` → `package/standalone/umd/vis-network.min.js`
- **Дата получения:** 2026-05-18
- **Лицензия:** dual MIT / Apache-2.0 (см. `vis-network-LICENSE-MIT.txt` и
  `vis-network-LICENSE-APACHE-2.0.txt`)
- **Потребитель:** `parser/scripts/04_nspd_graph_v14.py:render_html()` — читает этот файл и
  встраивает в HTML через `<script>…</script>` вместо
  `<script src="https://cdn.jsdelivr.net/…">`

## Правила обновления

1. Любая замена/обновление = PR с проверками:
   - sha256 нового файла указан в этом README;
   - smoke-test `render_html(nodes=[], edges=[])` отрабатывает без ошибок;
   - в выводе нет внешних сетевых ссылок в HTML-атрибутах (`<script src>`,
     `<link href>`, `<img src>`, `<iframe src>`); URL внутри
     JS-комментариев лицензий допустимы — браузер их не загружает.
2. Pin версии — bump SemVer в README + bump MAJOR/MINOR контракта, если
   это меняет публичный wire-формат.
3. Не редактировать минифицированный код руками. Брать только официальные
   npm-релизы (`npm pack <pkg>@<version>`) или GitHub release artifacts с
   проверенной sha.
