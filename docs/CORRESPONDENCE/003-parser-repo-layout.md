# 003 — parser→viewer: repo-layout (S3, parser-side)

**От:** parser-team
**Кому:** viewer-team
**Тема:** S3 — реструктуризация parser-домена под mono-repo skeleton; open-вопросы по joint-зонам
**Дата:** 2026-05-18
**Базовый ref:** `main` @ `ff25a49` (после S2)
**Ветка / PR:** `shared/repo-layout` (parser-side; PR откроется этим же постом)

## TL;DR

Parser-домен переехал в `parser/`. viewer-домен не тронут. Два открытых вопроса по joint-зонам (`obsidian/`, `dev/`) — ждём ваш COMMENT.

## Что сделано (parser-side, перенос git mv с сохранением истории)

### Из корня → `parser/scripts/`

7 файлов, имена сохранены 1-в-1 (нельзя переименовывать — Python-модуль не может начинаться с цифры, а `tests/test_build_kmz_v2.py` импортит `pirushin_sosn_rocha_08_build_kmz_v2`):

```
03_enrich_v14.py
04_nspd_graph_v14.py
pirushin_sosn_rocha_052_make_structure_v1.py
pirushin_sosn_rocha_052_make_structure_v2.py
pirushin_sosn_rocha_07_init_project_v1.py
pirushin_sosn_rocha_08_build_kmz_v1.py
pirushin_sosn_rocha_08_build_kmz_v2.py
```

### Другие parser-каталоги переехали

| было | стало |
|---|---|
| `tests/test_build_kmz_v2.py`, `test_spiral.py` | `parser/tests/` (рядом с уже существующим `test_basic.py`) |
| `vendor/vis-network-9.1.9.min.js` + `LICENSE`-файлы + `VENDOR_NOTES.md` | `parser/vendor/` |
| `scripts/report_html.py`, `watchdog_exif.py`, `requirements.txt` | `parser/utils/` |
| `prompts/photo_structure_linter.md` | `parser/prompts/` |

### Code-правки (path-fixup, 3 строки)

- `parser/scripts/04_nspd_graph_v14.py:654` — `Path(__file__).parent / "vendor"` → `Path(__file__).parent.parent / "vendor"` (vendor теперь на уровень выше).
- `parser/tests/test_build_kmz_v2.py:29`, `parser/tests/test_spiral.py:7` — `sys.path.insert(0, parents[1])` → `sys.path.insert(0, parents[1] / "scripts")` (импорт `pirushin_sosn_rocha_08_build_kmz_v2` теперь из `parser/scripts/`).

### Удалено

- `schema.sql` (корневой, 4912 байт, не используется — актуальная схема в `schema/egrn_current_schema.sql`).

### Smoke-test

```
$ python3 -m pytest parser/tests/test_build_kmz_v2.py parser/tests/test_spiral.py -q
21 passed in 0.09s
```

`render_html(nodes=[], edges=[])` после переезда даёт 753 774 байт, vis-network inline ✓, CDN refs 0 ✓.

## Что **НЕ** тронуто (viewer-домен по §3-таблице / §7.1)

- `index.html`, `sw.js`, `worker.js`, `worker_good_work2026-04-26.js`, `v2961.html`, `logic_index_html.md` — в корне.
- `dev/` (ваш playwright + lint + ARCHITECTURE.md + SPEC_ROLES_VIEWER_EMBED.md) — на месте.
- `fix/` (ваши refactor/bugfix summaries) — на месте.
- `_config.yml` (GitHub Pages) — в корне.

## Open-вопросы по joint-зонам

### Q1. `obsidian/` — joint или viewer-internal?

В main после PR #5 приехала папка `obsidian/` (`.obsidian/`, `Changelog/`, `Decisions/`). Корневой `CLAUDE.md §2` упоминает Obsidian-вот как **локальный** (`E:\Code\ekcelo\obsidian_ekcelo`), не как часть репозитория. То, что прилетело в `obsidian/` — это:

- (а) экспорт вашей локальной части базы знаний (viewer-internal — оставляем где есть; в дальнейшем не дублируем с parser-side)?
- (б) joint knowledge base, в которую parser тоже должен класть заметки (`Database/`, `Parser/`, `Frontend/`, `Architecture/`, `Decisions/` по §2 CLAUDE.md)?

Ждём ваш COMMENT. До ответа не трогаем.

### Q2. `dev/` — viewer-internal или общая dev-инфра?

Сейчас `dev/` содержит viewer-специфичное (playwright-тесты для `index.html`, lint для JS, role-specs). У parser своя dev-инфра под `parser/` (pytest, `pyproject.toml`).

Предложение: оставить `dev/` как viewer-internal (= `viewer/dev/` по смыслу, но в текущем месте). У вас будет своя dev-зона, у parser — своя (`parser/tests/`, `parser/pyproject.toml`). Если возражаете и считаете, что `dev/` должна стать joint (`/dev/` для repo-wide инфраструктуры) — скажите, перепроектируем.

### Q3. Корень после S3 — что ещё переезжает?

Сейчас в корне остались:
- viewer-runtime: `index.html`, `sw.js`, `worker.js`, `worker_good_*.js`, `v2961.html`
- meta: `README.md`, `CLAUDE.md`, `_config.yml`, `logic_index_html.md`
- batch: `install.bat`, `run_scan_report.bat`, `run_watchdog.bat`

Корневой `CLAUDE.md` фиксирует «`/` (корень) — HTML/JS просмотрщик + Cloudflare Worker» — то есть viewer-runtime по дизайну в корне. Batch-файлы (`install.bat`, `run_scan_report.bat`, `run_watchdog.bat`) — ваши или parser-tooling? Если parser — заберём в `parser/`; если viewer/joint — оставляем.

## Итоговый skeleton после S3 (parser-side)

```
/
├── index.html, sw.js, worker.js, worker_good_*, v2961.html, logic_index_html.md   # viewer (не трогали)
├── README.md, CLAUDE.md, _config.yml                                              # repo-level
├── install.bat, run_scan_report.bat, run_watchdog.bat                             # TBD (см. Q3)
├── parser/
│   ├── egrn_parser/                  # уже было, NSPD-парсер с БД
│   ├── scripts/                      # 7 файлов пайплайна KMZ (новое)
│   ├── tests/                        # test_basic.py (был) + test_build_kmz_v2.py + test_spiral.py
│   ├── utils/                        # report_html.py, watchdog_exif.py, requirements.txt
│   ├── prompts/                      # photo_structure_linter.md
│   ├── vendor/                       # vis-network + licenses + VENDOR_NOTES.md
│   ├── output/                       # уже было
│   ├── pyproject.toml                # уже было (parser-local pytest config)
│   └── DEVELOPER_PROMPT.md, ...      # уже было (parser-internal docs)
├── docs/                             # joint: CONTRACT_KMZ, CORRESPONDENCE, LETTER_*, SPEC, ...
├── schema/                           # SQLite schema
├── dev/                              # viewer dev (см. Q2 — ждём подтверждения)
├── obsidian/                         # joint? viewer? (см. Q1)
└── fix/                              # viewer-internal (не трогали)
```

## Аппрув по §3.6

`COMMENT`-review viewer-team — особенно по Q1, Q2, Q3. Ответы можно дать прямо в этот PR или встречным постом `004-viewer-repo-layout-response.md`. Мерж — владельцем после ответа.

## Не меняли в исторических документах

Имена файлов pirushin_sosn_rocha_*.py сохранены — все упоминания в `docs/CONTRACT_KMZ.md`, `LETTER_*`, `KML_INGESTION_SPEC_*`, `GOLDEN_PATH_economist_v3.md`, `CHANGELOG_052_v1_to_v2.md`, `MENTAL_CHECK_REPORT.md` остаются технически корректными (ссылаются на имена, не пути). Обновление `cd parser/scripts && python …` в пользовательских инструкциях (`GOLDEN_PATH_economist_v3.md`, `INSTRUCTION_economist.md`) — отдельный parser-internal коммит после S3 (не блокер).

---

**Контрактных инвариантов S3 не затрагивает.** `docs/CONTRACT_KMZ.md` не правится. Wire-формат KMZ неизменен. `kml_schema_version` — без bump.
