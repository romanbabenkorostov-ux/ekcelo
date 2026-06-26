# 2026-06-09 — Золотой путь для экономиста (нарратив + мок-данные + runnable-демо)

По запросу заказчика: отдельный экономист-facing материал — история одного лота от
исходников до Bundle, с обозначением задач/решений/проблем, + мок-данные + объяснение
ADR pkg-schema↔C2.

## Добавлено
- **`obsidian/Golden-Path-Economist/README.md`** — золотой путь в 8 шагов
  (земля → насаждения → техкарта → погода → оценка → ЭТП-правки → лот → Bundle).
  Каждый шаг: задача → решение → реальная проблема → как закрыли (ЕЗП≠МКУ;
  заголовки сметы; NSPD не затирает ручной ввод; Windows `:` в именах). Плюс: где
  что искать в Obsidian, copypaste-запуск демо, и **пояснение для Романа про ADR
  «pkg-schema ↔ C2 export-mapping»** (что решить, почему без него нельзя).
- **`obsidian/Golden-Path-Economist/mock_data/`**:
  - `perechen_nasazhdeniy.txt` — перечень насаждений (залог);
  - `etp_pravki_ekonomista.yaml` — ручные правки ЭТП (приоритет manual);
  - `lot.yaml` — определение лота (include/exclude).
- **`parser/scripts/golden_path_demo.py`** — runnable-демо: один прогон проводит
  лот «винодельческое хозяйство» через весь конвейер на мок-данных, печатает
  результат каждого шага. Не требует сети/тяжёлых зависимостей.

## Проверено
`python scripts/golden_path_demo.py` проходит все 8 шагов:
ЕЗП (не понижен геометрией) → 3 насаждения (Алиготе/Каберне) → 74 события техкарты →
погода (GDD 5400) → оценочный профиль → ЭТП (износ ручной сохранён, материал из NSPD)
→ лот (2 члена) → Bundle (manifest, целостность OK).

## Где искать (для заказчика)
`obsidian/Golden-Path-Economist/README.md` — основной документ; запуск —
`parser/scripts/golden_path_demo.py`.

## Файлы
- `obsidian/Golden-Path-Economist/README.md` (новый)
- `obsidian/Golden-Path-Economist/mock_data/{perechen_nasazhdeniy.txt,etp_pravki_ekonomista.yaml,lot.yaml}` (новые)
- `parser/scripts/golden_path_demo.py` (новый)
