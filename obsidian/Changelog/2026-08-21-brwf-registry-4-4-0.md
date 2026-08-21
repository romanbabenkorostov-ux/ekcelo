# 2026-08-21 — BRWF_REGISTRY: реестр обновлён до brwf:4.4.0

## Задача
Пользователь попросил проверить/отрефакторить все контракты семейства
для консистентного хранения Location.accuracy у фото и точечных
активов. В `ekcelofotomobile` внутренний аудит выполнен и смёржен
(accuracy дошла до manifest.json, FoundAssetEntity, MeasurementEntity,
CONTRACT_MOBILE-полей; `brwf` поднят 4.1.0 → 4.4.0 за три шага, из
которых в этот реестр попал только 4.1.0).

## Что сделано
`contracts/format/BRWF_REGISTRY.md` — таблица «Текущие версии по
origin» была не синхронизирована с `Brwf.kt` (регистрировала только
4.1.0, хотя фактическая версия уже 4.4.0 после трёх добавочных
изменений — group_id/unbound_groups §14, accuracy_m §19 и ранее
task_label/accounting_scope/slang_tags §11/§13). Обновлена запись до
`brwf:4.4.0` с кратким перечнем всех промежуточных шагов и ссылкой на
построчный changelog в `Brwf.kt`.

## Важная находка (вне scope этой правки, зафиксирована отдельно)
При проверке `docs/CONTRACT_KMZ.md` (Профиль B, §4.1/§4.2) обнаружено,
что документированная схема (per-Placemark `<ExtendedData>` с
`file`/`uuid`/`photo_uuid`/`section`/`status`/`tech`/`group_1`/
`group_2`, `<table>`-карточка, `files/`-медиа, сайдкар `ekcelo.json`)
**не соответствует ни одной из двух реальных реализаций**:
- `ekcelofotomobile/.../ExportHelper.kt:exportToKmz` — простой легаси-
  формат без `<table>`/ExtendedData на Placemark, медиа в `images/`,
  без сайдкара.
- `EkceloFotoMakeInvent/techno/bundle.py:build_kml` — другой формат
  («техносхема», один Placemark = актив без фото вообще), с
  ExtendedData, но с другим набором полей и сайдкаром `_techno.json`.

Ни туда, ни туда `accuracy_m` добавлять не стал — версионировать
контракт под поле, которому нет соответствующего реального эмитента,
только усугубило бы расхождение. Нужна отдельная сессия: либо привести
код в соответствие контракту, либо контракт — к факту.

## Канал доставки
git push на `claude/ekcelofotomobile-folders-packages-4tryj0`.
