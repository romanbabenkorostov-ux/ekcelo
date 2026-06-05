# Тестирование базы данных C2 — инструкция для экономиста

> Цель: собрать БД EKCELO нового поколения (C2) и убедиться, что объекты, права и
> граф собираются правильно. Два трека: **A — быстрая проверка C2** (без парсера,
> 5 минут) и **B — на реальных выписках** (через парсер).

## ⚠️ Почему упала прошлая попытка
Команда `import_block2` ждёт на вход **готовую БД парсера** (`*.db` со структурой
Block-2: таблицы `land_objects`, `rights` и т.д.). В прошлый раз путь указывал на
**исходный PDF** (`...pdf\parser_block2.db`) — такого файла там нет, отсюда
`unable to open database file`. БД парсера сначала нужно **создать** (трек B) —
или для быстрой проверки сгенерировать демо (трек A).

Ещё нюанс: `import_block2` импортирует слой **ЕГРН** (объекты+права). **ЕГРЮЛ/ЕГРИП**
(папка `EGRUL-EGRIP`) сюда подавать не нужно — они вливаются отдельной стадией
(классификатор, в работе).

---

## 0. Подготовка (один раз)
```powershell
cd E:\Code\ekcelo\code
pip install "sqlalchemy>=2.0" alembic pytest
$env:EKCELO_DB_URL = "sqlite:///E:/Code/ekcelo/code/contracts/db/ekcelo.db"
```
> Строку с `EKCELO_DB_URL` повторяй после каждого нового окна терминала.

## 1. Создать пустую БД C2 (33 таблицы)
```powershell
cd contracts\db
alembic upgrade head
cd ..\..
```
Ожидаемо: три строки `Running upgrade ... 0001 ... 0002 ... 0003`; появится файл
`contracts\db\ekcelo.db`.

---

## ТРЕК A — быстрая проверка C2 (без парсера)

### A1. Сгенерировать демо-данные парсера
```powershell
python -m contracts.db.make_demo_block2 contracts\db\demo_block2.db
```

### A2. Залить их в C2 и построить граф
```powershell
python -m contracts.db.import_block2 contracts\db\demo_block2.db
python -m contracts.db.graph_emit contracts\db\out\graph.json
```
Ожидаемо:
```
imported: {'objects': 3, 'entities': 6, 'geometries': 2, 'subjects': 2, 'relations': 4, 'assertions': 4}
graph.json: 6 nodes, 4 edges → contracts\db\out\graph.json
```
Если числа такие — **конвейер C2 рабочий**. Можно переходить к треку B на реальных данных.

---

## ТРЕК B — на реальных выписках ЕГРН

> **Импортёр идемпотентный** — повторный прогон не падает и не плодит дубли. Но
> демо и реальные данные **смешивать не нужно**. Перед треком B — чистая C2 БД:
> ```powershell
> Remove-Item contracts\db\ekcelo.db -ErrorAction SilentlyContinue
> cd contracts\db; alembic upgrade head; cd ..\..
> ```

### B1. Создать БД парсера из PDF выписок ЕГРН
Парсер строит свою БД командой `parse`. Запуск из папки `parser`:
```powershell
cd parser
python -m egrn_parser parse --input "E:\Code\ekcelo\primer_for_parsing\EGRN" --db output\egrn.db
cd ..
```
- `--input` — папка с **ЕГРН**-выписками (PDF/XML), НЕ ЕГРЮЛ.
- Результат — БД парсера `parser\output\egrn.db` (это и есть «Block-2 БД»).
- Если не хватает библиотек парсера — поставь их: `pip install -e parser` (один раз).

### B2. Залить БД парсера в C2 и построить граф
```powershell
python -m contracts.db.import_block2 parser\output\egrn.db
python -m contracts.db.graph_emit contracts\db\out\graph.json
```
Числа в `imported: {...}` должны быть **больше нуля** и примерно соответствовать
числу разобранных выписок.

---

## 2. Приёмка (что проверить в `contracts\db\out\graph.json`)
- **`nodesByKind`** (в конце файла): типы `land`, `building`, `room`, `accessory`,
  `beneficiary_legal` с правдоподобными количествами.
- В **`edges`** есть:
  - `owns` / `leases` — кто чем владеет/арендует (из ЕГРН), `confidence: 1.0`;
  - `contains` — что в чём расположено (ЗУ→здание→помещение→принадлежность);
  - `controls` — корпоративные цепочки (если были), достоверность ниже.

## 3. Автотест (необязательно)
```powershell
$env:PYTHONPATH = "E:\Code\ekcelo\code"
pytest contracts\db\tests -q
```
Ожидаемо: `2 passed`.

## 4. Что сообщить команде
(а) строку `imported: {...}`; (б) совпало ли число `objects` с ожидаемым по выпискам;
(в) есть ли `owns`-рёбра с `confidence 1.0`; (г) любые ошибки красным — целиком.

---

## Чего пока НЕТ (в работе, не баг)
- **ЕГРЮЛ/ЕГРИП, ОСВ, EXIF-фото, NSPD** ещё не вливаются автоматически — это следующая
  стадия (парсер-классификатор документов). Сейчас трек B проверяет слой ЕГРН.
- Доимпорт `company_groups`/`business_units`/`valuations` из БД парсера — следующий слайс.
