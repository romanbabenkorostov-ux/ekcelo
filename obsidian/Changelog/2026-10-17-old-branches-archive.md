# 2026-10-17 — разбор старых веток ekcelo

История main перезапущена 2026-06-05; ~100 веток остались от прежней истории
(общего предка с main нет, слить git-ом нельзя). Сверка по содержимому файлов:
всё, кроме перечисленного ниже, в main уже есть (часто в более новой версии)
или устарело (pycache, zip, старые корневые скрипты, viewer — переехал в
ekcelo-site).

Перенесено как архив (только документы, без изменения кода):
- из `claude/magical-mccarthy-3ZyU4` (2026-05-29, раскладка viewer на слои):
  `Decisions/ADR-002-db-portability.md`, `Database/dialect-portability.md`,
  `Decisions/ADR-003-viewer-layers.md`, `Architecture/viewer-layers.md`,
  `Changelog/2026-05-28-viewer-layers-scaffold.md`. Код каркаса
  (`viewer/core`, `viewer/ui/bridge.js`) живёт в ekcelo-site.
- из `claude/affectionate-goldberg-b9Cnn` (2026-06-03, декомпозиция
  ekcelo-site): `Architecture/ekcelo-site-decomposition.md`,
  `UserGuide/ekcelo-site-user-flow.md`,
  `Changelog/2026-06-03-ekcelo-site-decomposition.md`.

Не перенесено:
- скилл `db-portability` и агент `viewer-extract`, скилл `viewer-layers`:
  срабатывают автоматически и требуют SQLAlchemy/alembic, а миграции в репо —
  файлами `schema/migrations/` (CLAUDE.md §3); viewer уже вынесен.
- `claude/epic-knuth-NgObz` — переделка tile-seam CSS в старом viewer без
  UA-сниффинга, не слита и не проверена в браузерах; в main остаётся рабочий
  вариант v2.9.53.
- `dev-cadastre-proxy`, `fix-nspd-cors` — правки старого viewer (май),
  в ekcelo-site решено иначе.

Статус ADR-002-db-portability / ADR-003-viewer-layers — исторический, не
подтверждён заново.
