# Экспорт лота на ЭТП

> Как сгенерировать текст карточки лота + PDF-приложение для torgi.gov.ru, sberbank-ast.ru, roseltorg.ru.

## Когда использовать

После того как ЕГРН-выписки разобраны, OSV survey-лист импортирован, а опционально — checko-данные подтянуты. Это финальный шаг перед публикацией на ЭТП.

## Что получите на выходе

```
out/etp/<lot_id>/
├── lot_appendix.md                  # Markdown-приложение (можно конвертировать в PDF/DOCX)
├── torgi.gov.ru/
│   ├── description.short.txt        # 3 абзаца для карточки ЭТП
│   ├── description.full.txt         # 6 абзацев для PDF/виджета
│   └── long_description.json        # JSON ядро для отладки
├── sberbank-ast.ru/                 # Аналогично, оценочно-процедурный тон
└── roseltorg.ru/                    # Аналогично, разговорно-развёрнутый тон
```

## Базовый запуск

```bash
python -m parser.exporters.etp.cli \
    --lot lot:pirushin:001 \
    --db ekcelo.sqlite \
    --platforms torgi.gov.ru,sberbank-ast.ru,roseltorg.ru \
    --modes short,full \
    --out out/etp/
```

## Параметры

| Параметр | Обязательный | Что делает |
|---|---|---|
| `--lot` | да | `lot_id` лота (см. `lots.lot_id` в БД). |
| `--db` | да | Путь к `ekcelo.sqlite`. |
| `--out` | да | Куда сложить артефакты (создаётся если нет). |
| `--platforms` | нет | Через запятую. По умолчанию — все три. |
| `--modes` | нет | `short`, `full` или оба. По умолчанию — `short,full`. |
| `--target-cad` | нет | Опционально: КН-якорь для identity. По умолчанию — `lots.primary_cad_number`. |
| `--appendix-format` | нет | `md` (default), `pdf`, `docx`. Для PDF/DOCX нужен LibreOffice или pandoc. |
| `--quiet` | нет | Не печатать список созданных файлов. |

## PDF-приложение

```bash
python -m parser.exporters.etp.cli ... --appendix-format pdf
```

Требует один из:
- **LibreOffice** (рекомендуется): `apt install libreoffice` / `choco install libreoffice`
- **pandoc**: `apt install pandoc` / `choco install pandoc`

Если ни одного нет — CLI выдаст warning и оставит только `.md` версию.

## Bulk-обработка (несколько YAML-OSV за раз)

Если у вас несколько проектов в `parser/inbox/etp/`:

```bash
python -m parser.exporters.etp.etl_pipeline_cli \
    --db ekcelo.sqlite \
    --move-applied \
    --export --commit
```

Это:
1. Применит все YAML из `parser/inbox/etp/`.
2. Переместит успешные в `_applied/<YYYY-MM-DD>/`.
3. Перегенерирует JSON-экспорт для viewer'а.
4. Сделает auto-commit.

См. [[etp-osv-import]] для деталей по YAML-формату.

## End-to-end smoke

Если хотите убедиться что пайплайн работает на тестовых данных:

```bash
python -m parser.exporters.etp.smoke_cli
```

Возвращает rc=0 на happy path; rc=1 если что-то сломано (с детализацией в stderr).

## Troubleshooting

### `error: db not found: ekcelo.sqlite`

Создайте dev-БД с baseline-данными:

```bash
python -m parser.exporters.etp.init_db_cli --db ekcelo.sqlite --with-template
```

### `unknown platforms: ['sberbank']`

Используйте полное доменное имя: `sberbank-ast.ru`. Список валидных платформ — см. вывод `--help`.

### Описание без слов «зон охраны ОКН» / неполное

Это значит что соответствующие данные не пришли в БД. Проверьте:
1. YAML-OSV содержит ли секцию `legal_extra.special_restrictions`?
2. checko-обогащение запускалось? (см. [[etp-checko]])
3. NSPD-обогащение запускалось? (`python -m parser.exporters.etp.nspd_enrich_cli`)

### Текст в неправильном падеже («центр город» вместо «центр города»)

Это работает morphology-фильтр pymorphy3. Проверьте что pymorphy3 установлен:

```bash
pip install pymorphy3
```

И что в шаблоне используется `{{ value | inflect_gen }}` для нужного слова.

## Что дальше

- Скоординируйте текст с экономистом и опубликуйте на ЭТП вручную (UI самой ЭТП).
- Если хотите автоматическую сборку «меморандум + слайды» — см. [[orchestrator-cli]] или [[orchestrator-web]].
