# 2026-05-29 — EXIF v1.2 потребитель в viewer (Phase 1c + admin-UI hint)

Закрывает «открытое» из roadmap после мерджа PR #78 (parser-A EXIF v1.2):

- viewer lightbox должен показывать новое опциональное поле
  `kind:"photo".note` (заметка экономиста, ≤1000 chars).
- admin/etp-profile должен подсказать экономисту, что `extras.notes`
  можно использовать как контейнер per-photo заметок joined через «; »
  (вариант a2 из CORRESPONDENCE/028 — write-path минуя EXIF, viewer
  остаётся статикой).

## viewer/index.html — `buildRows(p)` lightbox

Добавлен один блок после «📄 Документ»:

```js
if(p.docMeta?.kind === 'photo' && p.docMeta?.note){
  rows.push(`<tr><td colspan="2" …>📝 Заметка экономиста</td></tr>`);
  addRow('note', p.docMeta.note);
}
```

- Триггерится только когда payload это явно фото (`kind:"photo"`)
  и `note` непустой.
- v1.1-фото без поля → truthy-check `?.note` → блок не показывается,
  поведение прежнее (backward-compat по контракту EXIF v1.2).
- Стиль карточки — оранжевый акцент (rgba(255,200,120,.08) +
  `#f0c060`) рядом с синим «📄 Документ» — визуально разнесено,
  без расширения CSS.

## viewer/admin-etp-profile.html — `SECTIONS.extras.notes` label

Label расширен подсказкой:
```
notes (несколько заметок — через «; », Stage 6 EXIF мерджит так же)
```

Никакая логика генератора не меняется — экономист продолжает писать
свободный текст, парсер при `apply_osv` / `etl_exif` собирает по тому
же принципу join '; '. Контракт `etl-osv.md` форвард-совместим.

## Тесты

- `node --check` inline JS admin-UI → OK.
- YAML-generator smoke 5/5 (без регрессий).
- E2E: `extras.notes = "трещина по фасаду в правом углу; новая кровля 2024"`
  → `parser.exporters.etp.etl_osv.load_osv()` сохраняет всю строку 1-в-1.
- viewer/index.html — визуально grep'нуто, блок note вставлен после
  блока «📄 Документ» в `buildRows`.

## Контракт

- `docs/EXIF_USERCOMMENT_SCHEMA.md` v1.2 — не тронут (потребитель).
- `obsidian/Architecture/etl-osv.md` — не тронут (forward-compat).
- `CONTRACT_KMZ.md` 2.12.0 — не затрагивается (§3 UI/UX-домен).

## Что осталось из roadmap viewer-team

- viewer-layers scaffold (CORRESPONDENCE/029) — в ветке
  `claude/magical-mccarthy-3ZyU4`, ведётся параллельно другой сессией.
- Per-field `source` override в UI v2 — awaiting demand.
- Редактор `lots[]` в admin-UI — awaiting demand.
