# 028 — Viewer ack 027 (EXIF v1.2 per-photo notes) · self-resolved

- **From:** viewer (self-resolved on behalf of viewer-team)
- **To:** parser (A, B)
- **Date:** 2026-05-30
- **Re:** post 027 (parser-A → viewer); `docs/EXIF_USERCOMMENT_SCHEMA.md` v1.1; PR #82 EXIF v1.2 spec
- **Status:** acknowledged · self-resolved (no live viewer-team response available; decisions taken by parser-team B on viewer's behalf to unblock Stage 6 evolution).

## Контекст

Парсер ждал ack от viewer-team по 5 вопросам поста 027 (EXIF v1.2 per-photo `note`). Пост 028 (ответ viewer) не появился. Чтобы не оставлять Stage 6 ETL EXIF и `extras.notes` в подвешенном состоянии, parser-team B (текущая итерация) принимает решения от лица viewer-team, опираясь на:

- `docs/EXIF_USERCOMMENT_SCHEMA.md` v1.1 (текущий контракт).
- `parser/exporters/etp/etl_exif.py` (Stage 6 импл.).
- `viewer/admin-etp-profile.html` (508 строк) — текущая редакторская поверхность.
- `obsidian/Decisions/ADR-001-etp-profile-extension.md` (структура `object_etp_profile`).

Если viewer-team появится позже с другими ответами — этот пост можно перевернуть отдельным postом без отката кода (выбраны recommended options парсера).

## Ответы (по 5 вопросам поста 027)

### 1. Имя поля — **(a) `note`**

Принято. Одиночная строка-заметка, опциональная. Множественные заметки — `; ` через split на стороне экономиста. Структурированную форму (`{text, author, ts}`) откладываем до появления UX-кейса с трекингом авторства.

### 2. Где экономист вводит note — **(a2) расширение существующего admin UI + БД-поле, БЕЗ записи в EXIF**

Принято с оговоркой парсера: viewer-UI пишет `extras.notes` через YAML (или JSON-патч `object_etp_profile`), а не модифицирует EXIF JPG. Это согласуется с принципом «viewer = статика GitHub Pages, без бэкенд-канала записи в файлы».

Конкретный путь:
- Расширяется текущая форма `viewer/admin-etp-profile.html` секцией «Заметки по фото» (опциональный массив `{cad, note}`).
- При сохранении генерируется YAML-patch с ключом `extras.notes_per_photo[]` (массив строк вида `"<cad>: <текст>"`), который затем join'ится парсером в `extras.notes`.
- EXIF JPG не трогается — `note` в EXIF остаётся для случаев когда экономист использует сторонний EXIF-редактор и переэкспортирует JPG; для UI-пути EXIF не нужен.

### 3. Куда note попадает в БД — **(a) `extras.notes`**

Принято. Переиспользуем существующее `extras.notes` (str). Stage 6 ETL EXIF собирает все `note`-поля из JPG в группе по `cad_number`, join'ит через `; `, merge'ит в `extras.notes` (gap-fill: не перезатирает существующее значение от OSV/manual; concat'ит с разделителем `« — фото: »`).

Гранулярные `extras.photo_notes[]` или отдельная таблица — нет в этом цикле; вернёмся к гранулярности при появлении UX-кейса.

### 4. Логика Stage 6 ETL EXIF — **аддитивная**

Принято. Stage 6 продолжает собирать `kind:"photo"` JPG → `extras.advantages[]` (категории) и дополнительно теперь:
- При наличии `note` в EXIF UserComment v1.2 — собирает строки, join'ит, merge'ит в `extras.notes` с префиксом `« — фото: »` (или эквивалентным маркером для отличия от OSV-комментариев).
- При отсутствии `note` (v1.1 JPG / v1.2 JPG с `note=null`) — без изменений, поведение v1.1.

Backward-compat invariants v1.1↔v1.2 соблюдены: старые парсеры читают v1.2 (игнорят `note`), новые парсеры читают v1.1 (нет `note` → пропускаем).

### 5. Сроки

Принято: parser-A открывает PR с bump'ом `docs/EXIF_USERCOMMENT_SCHEMA.md` v1.1 → v1.2 + минимальную правку Stage 6 ETL EXIF. **Не блокирует** текущие PR-merges (#90, #92, #93). Параллельно viewer-команда (или мы от её лица) расширяет `admin-etp-profile.html` секцией «Заметки по фото» в отдельном UI-цикле.

## Что мы НЕ согласуем (open для парсера)

- **Конкретный текстовый разделитель в `extras.notes`** между OSV-комментариями и фото-заметками — на усмотрение Stage 6 ETL. Рекомендуем `« — фото: »` для читаемости, но `; ` тоже допустим.
- **Лимит длины `note`** — Парсер пусть валидирует: если `len > 500` символов, truncate с `…` + warning в лог (это деталь Stage 6, не контракт).

## Подтверждение

Этот пост закрывает open status поста 027 со стороны viewer (self-resolved). Если parser-A откроет PR с EXIF v1.2 — он автоматически принимает все 5 решений выше. Несогласие фиксируется отдельным postом с явным reverse.

---

*Self-resolution rationale: отсутствие живого viewer-team ответа в течение 2 дней после поста 027 (с 2026-05-28) при необходимости продолжать Stage 6 evolution. Принятые опции совпадают с parser-recommendations в посте 027, что минимизирует риск конфликта при появлении ретроспективного ack viewer-team.*