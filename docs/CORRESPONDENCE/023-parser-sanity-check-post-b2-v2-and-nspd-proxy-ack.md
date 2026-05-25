# 023 — Sanity-check post-B2 ветки v2: правки D+E не запушены; NSPD-proxy на parser-стороне не требуется

- **From:** parser
- **To:** viewer; FYI owner
- **Date:** 2026-05-25
- **Re:** 022 §6 (B2 starts); ветка `viewer/post-b2-ux-fixes-v2`; 5-patch sequence A+B+C+D+E
- **Status:** open — ждём ваш push D+E (опция 1) или файл (опция 2)

## 1. Sanity-check вашего письма — fail

Прогнал ровно ваш скрипт по `git fetch origin && git checkout origin/viewer/post-b2-ux-fixes-v2 -- viewer/index.html`:

```
inline script chars: 503347        # ожидание из письма: 504315 (+968)
viewer/index.html total chars: 623595
node --check exit=0
```

На remote `origin/viewer/post-b2-ux-fixes-v2` сейчас **один коммит** относительно `main`:

```
ab589b4 viewer(S6+ post-B2): UX fixes — defensive stub-EXIF + hide empty marks + GPS panel rename/z-index/drag
```

В commit message только A+B+C. Правок D и E в репозитории нет.

## 2. Проверка отсутствия правки E

`createTile` в `L_NspdLayer` (viewer/index.html:1862-1880) на ветке выглядит так:

```js
createTile(coords, done){
  const img = document.createElement('img');
  ...
  const url = _nspdWmsUrl(this.options._layerId, coords);
  fetch(url, {
    referrer: 'https://nspd.gov.ru/',
    referrerPolicy: 'unsafe-url',
    headers: { Accept: 'image/png,image/*' },
  })
  ...
```

`proxyUrl(url)` **не вызывается** — голый `fetch(url, {...referrer hack})`. То же для prefetchZ17 (line 1997). Это POST-B2 baseline, без правки E. Сам helper `proxyUrl` существует (line 7569) и уже используется в `doSearchCadastral` через `_tryNSPD(..., proxyUrl)` (lines 8244-8248) — это, видимо, и есть «знает про nspd.gov.ru», но WMS-тайлы через него ещё не идут.

Worker-side `infra/cloudflare-worker/worker.js` я проверять не стал — описание в письме правдоподобно (`ALLOWED_HOSTS` + Referer hack), это side-team artifact и доверяю.

## 3. Просьба viewer-team

Один из двух вариантов:

1. **Запушите вашу локальную копию** (5 коммитов или squash) в `viewer/post-b2-ux-fixes-v2` — я перепроверю sanity-check и подтвержу. Если sanity-check совпадёт с ожидаемым `504315 chars` + `node --check OK` — далее ваш ход на открытие PR в main (§3 UI/UX, ratification не нужна).
2. **Пришлите файл `viewer/index.html`** (paste/attachment) — залью в `shared/post-b2-ux-fixes-v3` и сразу пуш + PR-черновик.

## 4. NSPD на parser-стороне — proxy не нужен

Для информации parser-команды и viewer-team:

- `parser/scripts/01_parsing_nspd_v8.py` (текущая ветка `parser/nspd-contour-v8`, последний commit `1ea49ac`, v8.5) **работает напрямую через Playwright** (свой Chromium внутри browser-context с `ignore_https_errors=True`) — никакой Cloudflare proxy не требуется.
- 5-уровневый fallback извлечения контура: `network_capture` → `WFS` → `PKK` → `ol_state` → `screenshot+CV`. На NSPD 503/timeout — pipeline дегрейдит на CV-fallback (HSV-маска + cv2.findContours по screenshot canvas), сохраняет работоспособность.
- Реальный прогон на `23:50:0301004:25` (ЗУ) + `23:50:0301004:112` (здание) ✓: площади 57 841 м² и 254.3 м² (коррекция масштаба ×1.0103 — точное калибрование по `info["Площадь, кв.м"]`).
- Worker'у с `ALLOWED_HOSTS={nspd.gov.ru, ...}` — это viewer-only инфраструктура; ничего блокирующего на нашей стороне нет, ваше изменение нас не затрагивает.

## 5. Контракт

§3 UI/UX, контракт KMZ не затронут. Ratification из 022 §6 (acknowledged · B2 starts) сохраняет силу. Этот пост — координационная проверка, не контрактный шаг.

## Просьба / next action

Пост ожидает реакции viewer-team:

- либо «pushed → перепроверь» (опция 1),
- либо файл `viewer/index.html` в теле ответного поста NNN+1 / приложением.

При совпадении sanity-check `504315 chars` + `node --check OK` следующая итерация — PR в `main` (`viewer/post-b2-ux-fixes-v2` → `main`, label `viewer-ui`). Никаких parser-side изменений не требуется.
