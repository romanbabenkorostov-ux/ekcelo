# EkceloFoto — Архитектура (база 2.9.61, актуально для 2.9.62)

> Для нескольких несвязных кодеров. Номера строк — ориентир по чистому 2.9.61
> (= `v2961.html`); в 2.9.62 они сдвинуты на ~+120 (см. «Изменения 2.9.62»).
> Опирайтесь на **имена функций/якорные комментарии**, а не на абсолютные строки.

## Что это

Одностраничное приложение: один файл `index.html` (~10.8k строк, CSS+HTML+JS).
Карта Leaflet 1.9.4, EXIF (exifr/piexifjs), KML/KMZ (JSZip), XLSX. Без сервера,
без сборки. Деплой: push в `main` → GitHub Actions (`.github/workflows/deploy.yml`)
→ GitHub Pages. CORS-прокси — Cloudflare `worker.js` (whitelist
`nspd.gov.ru`, `pkk.rosreestr.ru`, Яндекс.Диск). Кэш кадастровых тайлов —
service worker `sw.js` (Cache API, FIFO, лимит 2 000 000, 30 дней).

## Внешние зависимости

Leaflet 1.9.4 · exifr 7.x · piexifjs · SheetJS XLSX · JSZip 3.10. Браузерные API:
File System Access (перезапись файлов), Cache API/SW (тайлы), localStorage
(реестр фото/слоёв ~4.5 МБ), Blob URL. Карта-подложка: OSM, Esri Satellite.

## Карта файла `index.html` (секции, прибл. строки 2.9.61)

| Секция | ~Строки | Содержание |
|---|---|---|
| Meta + CDN | 1–25 | библиотеки |
| CSS | 26–1032 | темы (тёмная/светлая/системная), все стили |
| **Защита шва** | 400–468 | 70-строчный комментарий + 5 CSS-правил тайлов — **НЕ ТРОГАТЬ** |
| DOM/UI | 1035–1413 | header (меню), сайдбар, карта, диалоги, лайтбокс |
| Service Worker | 1420–1432 | регистрация, индикатор кэша |
| Карта | 1434–1512 | `const map`, `TILES`, тема фона, zoom-индикатор |
| Кадастр НСПД | 1514–1700 | `L_NspdLayer`/`createTile`, `NSPD_GROUPS`, `_applyCadastreLayers`, `_tileInfo` |
| Редактор контуров | 2499–2806 | `_ce`, рисование/правка полигонов |
| Очистка/перенос | 2806–3100 | перенос объектов между проектами |
| Точка пояснения | 3100–3271 | `_ep`, аннотации |
| Инфо-карточки | 3298–3401 | плавающие карточки объектов |
| STATE | ~3791 | `photos[]`, `activeIdx`, `remotePhotos[]` |
| Меню загрузки | ~3796 | `toggleUploadMenu`, хинты путей |
| Яндекс/GDrive | ~3927 | удалённая загрузка фото |
| Реестр фото | 3952–4141 | `addPhoto`, EXIF, дедуп фото |
| Дерево папок | 4142–4301 | визуализация структуры |
| Парсинг KML | 4302–4437 | `parseKML`, стили |
| Импорт KMZ | 4497–5009 | распаковка ZIP, blob-карта |
| Дедуп + загрузка KML | 5068–5185 | `_dedupParsedPlacemarks`, `_loadKMLFromText` |
| Персист KML | 5187–5336 | localStorage |
| Видимость слоёв | 5337–5388 | `toggleKMLLayer`, `removeKMLLayer` |
| Маркеры фото | 5389–5475 | `addMarker`, конус FOV |
| Сайдбар | 5476–5943 | списки фото/меток |
| Перенос фото (FSA) | 5944–6163 | drag в папку |
| Лайтбокс | 6178–6511 | полноэкранный просмотр + EXIF-карточка |
| Toast | ~6518 | `showToast` |
| Ручной GPS | 6548–6609 | установка координат/угла |
| Запись EXIF | 6610–6785 | piexifjs |
| Таймлайн | 6786–8078 | слайдер по датам |
| Поиск кадастра | 8079–8478 | по кадномеру, WFS НСПД |
| Экспорт (роутер) | 8897–9135 | `toggleExportMenu`, `exportData` |
| Экспорт KML/XLSX/KMZ | 9136–10021 | эмиттеры |
| GeoJSON | 10022–10454 | KML↔GeoJSON |
| Темы | 10451–10689 | переключатель темы |

## Состояние (как есть — императивно, без observer)

Глобальные мутабельные переменные: `photos[]`, `kmlLayers[]`, `map`, `_ce`,
`_ep`, `_activeSidebarTab`, `manualGPSActive`, `remotePhotos[]`, `cadastreActive`,
`NSPD_GROUPS`. UI обновляется прямыми DOM-вызовами после мутации (нет pub/sub).
Персист — ручные вызовы `savePhotosToStorage()` / `saveKMLLayersToStorage()`.
Это и есть мишень рефакторинга (см. `REFACTOR_GUIDE.md`).

## Граница SW / прокси

- `sw.js`: перехватывает любой запрос с `nspd.gov.ru`, кэширует (Cache API,
  `CACHE_NAME='ekcelo-cadastre-v2'` — **менять нельзя**, `activate` сотрёт кэш).
  Сообщения: `getCacheSize`, `clearCadastreCache`, `dumpZ17Tiles`,
  `importZ17Tiles` (2.9.62).
- Тайлы WMS идут **напрямую** в `nspd.gov.ru` (Referer задаётся `fetch{referrer}`),
  Cloudflare-прокси `worker.js` — только для WFS-геометрии и Яндекс.Диска.

## Изменения 2.9.62 (поверх 2.9.61)

1. **46a**: `sw.js` лимит 40000→2 000 000; `index.html` `_requestPersistentStorage()`
   (`navigator.storage.persist()` + `estimate()`), бейдж кэша показывает 🔒 usage/quota.
2. **46b**: `_nspdWmsUrl(id,coords)` — единый билдер URL (createTile + префетч);
   `_prefetchCadastreZ17` / `_scheduleCadastrePrefetch` — догрузка z17 для
   центральных 70% в SW-кэш на `moveend/zoomend` и при включении кадастра.
3. **46c**: SW `dumpZ17Tiles`/`importZ17Tiles`; `_exportCadastreTiles()` (ZIP +
   `manifest.json` с дословными URL), `_onTilePackChosen()` (импорт-обогащение);
   кнопки в меню «Экспорт данных» и «Загрузить фото/объекты».
4. **47b**: `v2961.html` — замороженная 2.9.61; баннер-переключатель на обеих.
