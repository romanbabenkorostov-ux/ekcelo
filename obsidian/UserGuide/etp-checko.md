# Подключение checko-обогащения

> Как opt-in подтянуть данные о юрлицах из checko.ru → `object_etp_profile.legal_extra.owner_checko`.

## Когда использовать

Если вы (или другой пользователь) ранее запустили [parser_checko_ru](https://github.com/...) — standalone-инструмент, который кэширует данные checko.ru в `innogrn.db`. Этот кэш можно подключить к ekcelo, чтобы:

- Видеть статус юрлица-правообладателя (Действует/Ликвидировано/Банкротство).
- Получать ОКВЭДы и спецрежимы (УСН/ПСН).
- Уставный капитал, численность работников, регион регистрации.

Эти данные попадают в `legal_extra.owner_checko` и используются в ЭТП-карточке (когда экономист добавит соответствующие фразы в шаблон).

## Что нужно

1. **`ekcelo.sqlite`** — с заполненной таблицей `rights` (есть `right_holder_inn`).
2. **`innogrn.db`** — кэш от parser_checko_ru. Если у вас его нет — пропустите этот раздел, ничего не сломается.

## Базовый запуск

```bash
python -m parser.exporters.etp.etl_checko \
    --db ekcelo.sqlite \
    --innogrn-db /путь/к/innogrn.db \
    --lot lot:pirushin:001
```

## Что произойдёт

Для каждого КН в лоте:
1. Найти INN правообладателя в `rights.right_holder_inn`.
2. Найти запись в `innogrn.subjects` (для не-филиалов).
3. Записать `legal_extra.owner_checko = {is_active, status_text, special_regime, reg_date, termination_date, ust_kap, schr, region, main_okved}`.

Пропускается:
- Если у КН нет правообладателя в `rights` → `no_right_holder_inn`.
- Если INN не в `innogrn.subjects` → `inn_not_in_innogrn`.
- Если `owner_checko` уже есть в профиле → `owner_checko_already_present` (gap-fill, не перезатираем).
- Если `innogrn.db` не найден → no-op без ошибки.

## Параметры

| Параметр | Обязательный | Что делает |
|---|---|---|
| `--db` | да | Путь к `ekcelo.sqlite`. |
| `--innogrn-db` | да | Путь к `innogrn.db` (выход parser_checko_ru). |
| `--lot` | да | `lot_id` для обогащения. |
| `--source` | нет | Default `checko`. |
| `--confidence` | нет | Default `0.9`. |
| `--dry-run` | нет | Не коммитить транзакцию; печатать только отчёт. |

## Пример dry-run

```bash
python -m parser.exporters.etp.etl_checko \
    --db ekcelo.sqlite \
    --innogrn-db ~/checko_cache/innogrn.db \
    --lot lot:pirushin:001 \
    --dry-run
```

Вывод:
```
[OK  ] 61:44:0050706:31  inn=7707083893 fields=['owner_checko']
[skip] 61:44:0050706:7   no_right_holder_inn
summary: changed=1 skipped=1 (dry-run, rolled back)
```

## Troubleshooting

### `error: db not found: ekcelo.sqlite`

Аналогично [[etp-export]]: создайте БД через `init_db_cli`.

### Все КН пропускаются с `inn_not_in_innogrn`

Возможные причины:
- `innogrn.db` от старой версии parser_checko_ru (схема v8.0 vs v8.2). Перезапустите checko-парсер.
- INN в ЕГРН-выписке записан с пробелами/некорректно. Проверьте `SELECT inn FROM entity_registry`.

### `owner_checko_already_present` для всех КН

Это OK — значит данные уже подтянуты раньше. Если хотите перезатереть:

1. Сначала удалите ключ:
   ```sql
   UPDATE object_etp_profile
   SET legal_extra = json_remove(legal_extra, '$.owner_checko')
   WHERE cad_number IN (...);
   ```
2. Запустите `etl_checko` снова.

### Я не вижу `owner_checko` в ЭТП-карточке

Шаблон `torgi_long_description.j2` пока не упоминает `owner_checko`. Если хотите добавить фразу про статус юрлица — отредактируйте шаблон вручную или попросите программиста (см. `Architecture/etp-exporter.md`).

## Связи

- ADR-002 (отложенная политика интеграции): `obsidian/Decisions/ADR-002-parser-checko-integration-policy.md`.
- Маппинг полей: `obsidian/Architecture/etp-exporter.md` или changelog `2026-05-30-etp-etl-checko.md`.
- parser_checko_ru остаётся standalone (не в этом репо).
