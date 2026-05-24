# 2026-05-21 — S6+ v1: EXIF lightbox routing (viewer-инициатива)

**Что:** реализован минимальный фрагмент-роутинг для lightbox'а в
`viewer/index.html`. URL вида `…#p=<имя_файла>` синхронизируется с открытым
фото — deeplink, шеринг и обновление страницы сохраняют состояние.

**Контракт:** не расширяется. Чисто viewer-домен (§3 UI/UX), без
shared-ratification (договорено в CORRESPONDENCE/009, §9 контракта).

**Сделано:**
- `_setLightboxFragment(name)` — `history.replaceState` с `#p=<encoded>`
  при `openLightbox()` (строка ~7012).
- `_clearLightboxFragment()` — очистка хэша при `closeLightbox()`
  (строка ~7175).
- `_readLightboxFragment()` + `_tryOpenFromFragment()` — после
  `loadPhotosFromUrl()` (deeplink `?photo=URL[#p=name]` или
  `?photo1=…&photo2=…#p=name`) ищется фото по `photos[].name` и
  открывается в lightbox.
- `hashchange` listener — реагирует на ручное изменение URL
  (типизация / back-forward / переход по якорю): открывает/закрывает
  lightbox без перезагрузки.
- `copyShareLink()` — если lightbox открыт, к ссылке дописывается
  `#p=<имя>`. Без открытого lightbox'а — ссылка чистая, как раньше.

**Идентификатор:** `photos[i].name` (имя файла, стабильное в EXIF/KMZ),
а не индекс. Безопасно при пересортировках/удалениях/мульти-source.

**Что НЕ вошло в v1 (явно):**
- Pushstate (history back/forward) — только `replaceState`, без захламления
  истории браузера.
- Роутинг по индексу маркера KMZ (`?marker=N` / `#m=N`) — не нужно для
  фото-flow.
- Auto-open после KMZ-загрузки (только после remote-photo deeplink) —
  KMZ открывается через file picker, deeplink-сценария нет.
- Обратная совместимость со старыми shared-ссылками без `#p=…` — они
  работают по-старому (хэша нет → lightbox не открывается автоматом).

**Инварианты:**
- `node --check` инлайн-скрипта чист (490 253 chars).
- Дефолтное поведение байт-в-байт прежнее: без `#p=…` lightbox открывается
  только по клику пользователя, как раньше.
- Контракт KMZ 2.11.0 не затронут.

**Файлы:**
- `viewer/index.html` — +9 строк (routing helpers + 2 hook'а в open/close +
  1 hook в loadPhotosFromUrl + 1 hook в copyShareLink + hashchange listener).

**Ветка:** `viewer/exif-lightbox-routing`.
