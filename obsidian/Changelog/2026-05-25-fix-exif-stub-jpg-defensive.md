# 2026-05-25 — viewer: defensive EXIF write для stub-JPG (post-B2 fix)

**Что:** в `writeEXIFWithGPS()` добавлена sanity-проверка blob'а перед попыткой piexifjs read-write cycle. Stub-JPG (91-байт фикстура от parser-team в `multi_extract_sample/`) ранее давал непонятную пользователю ошибку `EXIF: 'unpack' error. Mismatch between symbol and string length. 2:0` от piexifjs. Теперь возвращается понятный toast.

**Контракт:** не затронут. §3 UI/UX. Defensive-only fix.

**Сделано:**

1. **Pre-check в `writeEXIFWithGPS()`** (после получения blob, до `blobToDataUrl`):
   - `blob.size < 512` → toast «Файл слишком мал — возможно, synthetic stub без EXIF» + ранний exit.
   - `blob.slice(0,2)` не равен `FF D8` (JPEG magic) → toast «Не JPEG (нет FFD8)» + ранний exit.

2. **Улучшенный error message** на existing piexif.dump+insert catch: добавлен hint «JPEG несовместим с piexifjs (synthetic/stub или повреждённый файл)» — раньше показывался raw piexifjs message ("unpack error. Mismatch between symbol and string length"), что непонятно пользователю.

**Не делается:**

- Не меняем поведение для валидных JPG — write-cycle работает как раньше для реальных фото.
- Не пытаемся reconstruct EXIF на невалидном JPG (это потенциально потеря данных).
- Не меняем UserComment encoding (piexifjs 1.0.6 quirks с UTF-8 cyrillic) — это отдельная задача, не блокер.

**Инварианты:**

- `node --check` чист (500965 chars; +768 vs B2 baseline 500197).
- Валидные JPG (drag-drop / Yandex / GDrive / KMZ с реальным EXIF) обрабатываются как раньше.
- Stub-JPG `multi_extract_sample/IMG_0[123].jpg` (91 байт) → понятный toast вместо raw piexifjs error.

**Файл:**

- `viewer/index.html` — +6/−1 строк (2 точечные правки в `writeEXIFWithGPS` около line 7610-7622).

**Ветка:** `viewer/fix-exif-stub-jpg-defensive`.
