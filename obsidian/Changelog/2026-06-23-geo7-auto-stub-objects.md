# 2026-06-23 — Geo §7: auto-stub objects при KML-импорте

## Зачем
После A+C+D+F: импорт KML кладёт cad'ы в §7 (`asset_geo_link`), но если
этих cad'ов нет в `objects` — `build_object_viewmodel` падает с
`ObjectNotFound`. Пользователь должен был вручную INSERT'ить cad перед
verification. Это плохой UX.

## Решение

`import_kml_geo_cli` по умолчанию создаёт минимальные stub-записи в
`objects` для каждого cad, который встречается в primary/reference линках
импорта.

### Поля stub-записи
- `cad_number` — из KML;
- `object_type` — догадка по префиксу (`cad_zu_`→`land`,
  `cad_oks_`→`building`, `cad_ons_/cad_str_`→`construction`,
  `cad_room_`→`room`); default `land` для Yandex-формата без префиксов;
- `purpose='kmz-stub'` — маркер «пришло из KML, ЕГРН-выписки ещё нет»;
- остальные поля NULL — парсер ЕГРН-выписки перетрёт при поступлении.

### Безопасность
- `INSERT OR IGNORE` — если запись уже есть (даже не stub), не трогается.
- `--no-create-stub-objects` — флаг отключения (для случаев, когда нужно
  чистое поведение «§7 без побочного эффекта на §1»).
- Если таблицы `objects` нет вообще (минимальный test-DB) — silently skip.

### Совместимость с доктриной
ADR-001 говорит: «§1..§5 = ЕГРН-слой». Stub `purpose='kmz-stub'` —
прозрачный маркер, что эта запись НЕ из выписки. Парсер ЕГРН-выписок
работает через UPDATE по cad_number — stub перетирается полным содержимым
при поступлении выписки. Доктрина сохранена.

## Тесты (+5)
- `test_stub_objects_created_by_default` — default ON, 3 stub'а на KML_SAMPLE.
- `test_stub_objects_disabled_by_flag` — `create_stub_objects=False`.
- `test_stub_does_not_overwrite_existing_object` — настоящий объект цел.
- `test_stub_object_type_guessed_from_prefix` — cad_zu/cad_oks routing.
- `test_no_objects_table_skips_stub_creation_silently` — graceful без `objects`.

## E2E на Олимпе (без ручного INSERT)
```
python -m parser.exporters.etp.import_kml_geo_cli --kml olimp.kml --db olimp.sqlite
  primary линки:   22
  stub objects:    23 (в `objects`, purpose='kmz-stub')

python -c "from backend.app.services.viewmodel import build_object_viewmodel;
            vm=build_object_viewmodel('olimp.sqlite','23:15:0000000:2267',as_of='2026-06-15')"
  object_type:   land  (← из stub)
  geo.center:    [37.756, 45.001]
  geo.geometry:  Polygon, 85 pts
```

## Тесты
- backend: 174 passed (без изменений; stub-тесты — в parser/).
- parser: **+5** (24 теста в test_import_kml_geo_cli.py).
- orch-web: 297 passed.
- smoke: 33/33.

## Канал доставки
zip-handoff.
