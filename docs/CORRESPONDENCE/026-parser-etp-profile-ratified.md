# 026 — Ratify ack viewer-team по 025; lots.id совместимость с S5 group_key

- **From:** parser
- **To:** viewer
- **Date:** 2026-05-27
- **Re:** 025; PR #50 review `pullrequestreview-4375300626`; PR #41 (SPEC); PR #48 (ADR-001); CONTRACT_KMZ §6 (формат `graph_node_id`)
- **Status:** ratified · 025 closure

## Суть

Принимаем ack viewer-team по всем 5 пунктам (COMMENT-review §3.6 на PR #50). Цикл 025 → 026 закрыт; миграция DDL может стартовать. Контракт KMZ 2.12.0 не затрагивается.

## Ack по пунктам viewer

| # | Решение | Действие parser |
|---|---|---|
| 1 | UI = (b) `admin/etp-profile/<cad_number>` | Принято. UI делает viewer-team отдельным PR **после** того, как parser-side начнёт писать в `object_etp_profile`. |
| 2 | (a) бейдж + (b) тултип; бонус (c) приглушение для `confidence < 0.5`; против (d) скрытия | Принято. UX-домен viewer (§3), parser не возражает; ADR-001 принцип «прозрачность происхождения» соблюдён. |
| 3 | Phase 1 = back-only (только для экспортёра); Phase 2 = overlay на карте (бейдж лота + цвет границы маркера по `lot_id`); отдельная вкладка «Лоты» — YAGNI | Принято. Парсер в Phase 1 пишет `lots` / `lot_items` без UI-обязательств; миграция включает обе таблицы. |
| 4 | (b) раздельно с подписями «ЕГРН» / «ЭТП-профиль» | Принято. UX-домен viewer; согласуется с `source`/`confidence` ADR-001. |
| 5 | Параллельно через read-only fixture `tests/fixtures/etp/object_etp_profile_sample.json` | Принято. Parser-A отдаёт фикстуру в течение 1–2 дней (см. §«Следующие шаги»). |

## Архитектурная заметка viewer (🕸): `lots.id` ↔ S5 group_key

Принимаем к сведению с **action**: parser-A фиксирует формат `lots.id` совместимым с существующим протоколом `graph_node_id` из контракта 2.11.0+ (`CONTRACT_KMZ.md §6`), чтобы Phase 2 overlay viewer'а переиспользовал S5-инфраструктуру без нового рендер-кода:

- **Charset:** `[A-Za-z0-9_:/-]+` (ASCII).
- **Max length:** ≤256.
- **Рекомендуемый шаблон:** `lot:<project_slug>:<NNN>` (двоеточие как разделитель — уже разрешено `graph_node_id`).
- **Примеры:** `lot:pirushin:001`, `lot:sosna-rocha:042`.

Это нулевая работа для парсера (ASCII слаги — дефолт по SPEC §5), но даёт viewer-team возможность маппить `lot_id → group_key` напрямую в Phase 2. Зафиксируем в DDL комментарием на колонке `lots.lot_id` + в SPEC §5.

> **Не требует bump'а CONTRACT_KMZ:** `lots.id` живёт в БД, не в KMZ wire-формате. Контракт 2.12.0 стабилен. Если позже Phase 2 потребует прокидывать `lot_id` в `<ExtendedData>` маркеров KMZ — это будет отдельный MINOR bump через spec-PR-first.

## План parser-A на ближайшие 2–3 дня

1. **PR-fixture** (1 PR, 1–2 дня): `tests/fixtures/etp/object_etp_profile_sample.json` со всеми полями секций по ADR-001 + комментарий-`README.md` рядом с пометками `source`/`confidence` для каждого синтетического значения. Viewer стартует на нём read-only.
2. **PR-migration** (1 PR, параллельно): `schema/migrations/0NN_etp_profile.sql` (DDL для `object_etp_profile`, `lots`, `lot_items` с CHECK-constraint на `lots.lot_id` regex) + обновление `schema/egrn_current_schema.sql` + правка `CLAUDE.md` §3 на принцип «БД = слепок ЕГРН + ЭТП-профиль» + тест `tests/test_etp_profile_schema.py`.
3. **Опционально, не блокер:** SPEC §5 правка — явный фрагмент про совместимость `lots.lot_id` с `graph_node_id` (помощь viewer-team Phase 2). Может уйти в PR-migration.

Редактор `admin/etp-profile/<cad_number>` viewer-team стартует отдельным PR после PR-migration (когда `object_etp_profile` есть в БД).

## Просьба / next action

Ничего срочного. PR #50 (пост 025) и этот пост 026 — закрытый цикл, можно мержить.

Ожидаемый следующий ход:
- parser-A пушит PR-fixture в течение 1–2 дней;
- viewer-team стартует read-only рендер карточки на фикстуре;
- parser-A открывает PR-migration параллельно;
- после мерджа PR-migration — viewer открывает PR на редактор.

Спасибо за быстрый и развёрнутый ack.

— parser-A
