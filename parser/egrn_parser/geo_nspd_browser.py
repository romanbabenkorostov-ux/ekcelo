"""
egrn_parser/geo_nspd_browser.py — геометрия из NSPD через БРАУЗЕР (Playwright).

ПОЧЕМУ ПЕРЕПИСАНО (2026-06-27)
------------------------------
Прошлый путь пассивно слушал сеть через `v8.NetworkCapture` и ловил 0 feature,
хотя карта **показывала** контур после клика по лупе. Причина найдена по
сохранённой странице заказчика: современный NSPD отдаёт геометрию объекта
эндпоинтом поиска `https://nspd.gov.ru/api/geoportal/v2/search/geoportal`
(именно его дёргает лупа), а `NetworkCapture` **пропускает любой URL c
`/search/`** (старое правило «search = extent квартала» верно для ПКК, но не
для нового geoportal). Поэтому реальный ответ с геометрией молча отбрасывался.

КАК СЕЙЧАС
----------
1. Открываем карту NSPD в браузере → устанавливается сессия/куки/анти-бот.
2. **Активно** дёргаем geoportal-search через `page.request.get` (наследует
   cookies/Referer страницы → проходит анти-бот там, где голый urllib даёт 403).
   Ответ — FeatureCollection; геометрия в EPSG:3857 → репроекция в WGS84.
3. Параллельно вешаем **разрешающий** слушатель ответов (в отличие от v8 НЕ
   режет `/search/geoportal`) — он копит feature карты для обнаружения ОКС в
   границах ЗУ (centroid-in-polygon) и как пассивный fallback.

Выход: {cad: {"polygon": coords|None, "buildings": [{name, geometry}],
              "captured": int}}. polygon — список колец [[ [lon,lat],… ] ].
Требует playwright+chromium+сеть; иначе fetch_parcels бросит RuntimeError.
"""
from __future__ import annotations

import asyncio
import json
import math
import urllib.parse
from typing import Any, Optional

from egrn_parser import geo_nspd as _N

# Современный geoportal-API NSPD (тот, что дёргает строка поиска / лупа).
GEOPORTAL_SEARCH = "https://nspd.gov.ru/api/geoportal/v2/search/geoportal"
# Варианты запроса: универсальный + тематический по ЗУ. Пробуем по очереди.
_SEARCH_VARIANTS = (
    "{base}?query={q}",
    "{base}?thematicSearchId=1&query={q}",
)
_R_MERC = 20037508.34
# Поля с КН в properties geoportal-feature (в т.ч. вложенные в options).
_CAD_KEYS = ("cad_num", "cad_number", "cadastral_number", "kadnum",
             "cadNumber", "label", "descr")


# ── чистые помощники (тестируются офлайн) ────────────────────────────────────
def _reproject(geom: Optional[dict]) -> Optional[dict]:
    """EPSG:3857→WGS84, если координаты вне градусной сетки. Иначе как есть."""
    if not geom or "coordinates" not in geom:
        return geom
    p = geom["coordinates"]
    while isinstance(p, list) and p and isinstance(p[0], list):
        p = p[0]
    if not (isinstance(p, list) and len(p) >= 2):
        return geom
    if abs(p[0]) <= 180 and abs(p[1]) <= 90:
        return geom

    def pt(c):
        x, y = float(c[0]), float(c[1])
        lon = (x / _R_MERC) * 180.0
        lat = math.degrees(math.atan(math.exp((y / _R_MERC) * math.pi)) * 2 - math.pi / 2)
        return [round(lon, 7), round(lat, 7)]

    t, c = geom.get("type"), geom["coordinates"]
    if t == "Polygon":
        return {"type": t, "coordinates": [[pt(q) for q in ring] for ring in c]}
    if t == "MultiPolygon":
        return {"type": t, "coordinates": [[[pt(q) for q in r] for r in poly] for poly in c]}
    if t == "Point":
        return {"type": t, "coordinates": pt(c)}
    return geom


def _geom_to_coords(geom: Optional[dict]) -> Optional[list]:
    """GeoJSON (после репроекции) → coords полигона (внешние кольца) для geo_kmz."""
    g = _reproject(geom)
    if not g:
        return None
    t, c = g.get("type"), g.get("coordinates")
    if t == "Polygon":
        return c
    if t == "MultiPolygon" and c:
        return c[0]
    return None


def _feature_cad(feat: dict) -> Optional[str]:
    """Достать КН из feature: properties + вложенный properties.options."""
    props = (feat or {}).get("properties") or {}
    pools = [props, props.get("options") or {}]
    for pool in pools:
        if not isinstance(pool, dict):
            continue
        for k in _CAD_KEYS:
            v = pool.get(k)
            if isinstance(v, str) and ":" in v:
                return v
    return None


def extract_features(payload: Any) -> list[dict]:
    """Из ответа geoportal вытащить список GeoJSON-feature с геометрией.

    Терпим к обёрткам: {data:{features}}, {features}, FeatureCollection, Feature."""
    feats: list[dict] = []

    def walk(node, depth=0):
        if depth > 4 or node is None:
            return
        if isinstance(node, list):
            for x in node:
                walk(x, depth + 1)
            return
        if not isinstance(node, dict):
            return
        if node.get("type") == "Feature" and node.get("geometry"):
            feats.append(node)
            return
        if node.get("type") == "FeatureCollection":
            for f in node.get("features") or []:
                walk(f, depth + 1)
            return
        for k in ("data", "result", "features", "response", "body"):
            if k in node:
                walk(node[k], depth + 1)

    walk(payload)
    return feats


def pick_parcel_feature(feats: list[dict], cad: str) -> Optional[dict]:
    """Выбрать feature нужного ЗУ: точное совпадение КН > первый полигон."""
    want = cad.replace(" ", "").upper()
    polys = [f for f in feats if (f.get("geometry") or {}).get("type") in ("Polygon", "MultiPolygon")]
    for f in polys:
        fc = (_feature_cad(f) or "").replace(" ", "").upper()
        if fc == want:
            return f
    return polys[0] if polys else None


# ── браузерный прогон ────────────────────────────────────────────────────────
async def _close_modals(page):
    """Закрыть видимые модальные диалоги (кнопка X, overlay click, ESC)."""
    try:
        await page.evaluate("""
            () => {
                const close_btns = document.querySelectorAll('[aria-label*="Close"], [aria-label*="close"], button[title*="Close"]');
                for (const btn of close_btns) {
                    if (btn.offsetParent !== null) { btn.click(); break; }
                }
                const overlays = document.querySelectorAll('[role="dialog"], .modal, .modal-overlay, .dialog');
                for (const o of overlays) {
                    if (o.offsetParent !== null) {
                        const x = o.querySelector('[aria-label="Close"], .close');
                        if (x && x.offsetParent !== null) { x.click(); }
                    }
                }
            }
        """)
    except Exception:
        pass


async def _trigger_lupa(page, cad: str) -> dict:
    """Имитировать клик по лупе: NSPD грузит контур И «остальные данные» (ОКС
    в пределах ЗУ) только после фактического запуска поиска через UI.

    Компоненты NSPD — web-components с OPEN shadow root, поэтому ищем поле ввода
    и кнопку поиска рекурсивно по всем shadow-деревьям, заполняем КН, шлём Enter
    и кликаем лупу. Перехват ОКС — пассивным слушателем _on_resp."""
    try:
        return await page.evaluate("""
            (cad) => {
                const findDeep = (root, pred) => {
                    const stack = [root];
                    while (stack.length) {
                        const node = stack.pop();
                        const kids = (node.querySelectorAll ? node.querySelectorAll('*') : []);
                        for (const el of kids) {
                            if (pred(el)) return el;
                            if (el.shadowRoot) stack.push(el.shadowRoot);
                        }
                    }
                    return null;
                };
                const input = findDeep(document, el =>
                    el.tagName === 'INPUT' &&
                    (el.type === 'text' || el.type === 'search' || !el.type) &&
                    el.offsetParent !== null);
                if (input) {
                    input.focus();
                    input.value = cad;
                    input.dispatchEvent(new Event('input', {bubbles: true}));
                    for (const t of ['keydown', 'keyup']) {
                        input.dispatchEvent(new KeyboardEvent(t,
                            {key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true}));
                    }
                }
                const btn = findDeep(document, el =>
                    (el.tagName === 'BUTTON' ||
                     (el.getAttribute && el.getAttribute('role') === 'button')) &&
                    el.offsetParent !== null &&
                    (((el.getAttribute('aria-label') || '').toLowerCase().match(/поиск|search/)) ||
                     (el.querySelector && el.querySelector('[class*="search"],[class*="loupe"],[class*="magnif"]'))));
                if (btn) btn.click();
                return {input: !!input, button: !!btn};
            }
        """, cad)
    except Exception:
        return {"input": False, "button": False}


async def _search_geoportal(page, cad: str) -> list[dict]:
    """Активный session-aware запрос geoportal-search по КН → список feature.

    Пробует несколько раз с закрытием модалей и задержками."""
    q = urllib.parse.quote(cad, safe="")
    for attempt in range(3):
        if attempt > 0:
            await page.wait_for_timeout(500)
        await _close_modals(page)
        for tpl in _SEARCH_VARIANTS:
            url = tpl.format(base=GEOPORTAL_SEARCH, q=q)
            try:
                resp = await page.request.get(url, headers={
                    "Referer": "https://nspd.gov.ru/map",
                    "Accept": "application/json, */*",
                }, timeout=20000)
                if not resp.ok:
                    continue
                data = json.loads(await resp.text())
                feats = extract_features(data)
                if feats:
                    return feats
            except Exception:
                continue
    return []


async def _run(cads: list[str], *, discover: bool, headless: bool,
               timeout_ms: int) -> dict[str, dict[str, Any]]:
    from playwright.async_api import async_playwright

    out: dict[str, dict[str, Any]] = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        ctx = await browser.new_context(ignore_https_errors=True,
                                        user_agent="Mozilla/5.0")
        page = await ctx.new_page()

        # Разрешающий слушатель: копим geoportal-feature (в т.ч. из /search/),
        # которые v8.NetworkCapture отбрасывает. Источник ОКС + пассивный fallback.
        captured: list[dict] = []

        async def _on_resp(resp):
            try:
                url = resp.url
                if "nspd.gov.ru" not in url or "geoportal" not in url:
                    return
                ct = (resp.headers or {}).get("content-type", "")
                if "json" not in ct.lower() and "json" not in url.lower():
                    return
                data = json.loads(await resp.text())
                captured.extend(extract_features(data))
            except Exception:
                return

        page.on("response", lambda r: asyncio.create_task(_on_resp(r)))

        try:
            for cad in cads:
                captured.clear()
                layers = ",".join(str(x) for x in (_N.NSPD_ZU_LAYERS + _N.NSPD_OKS_LAYERS))
                url = (f"https://nspd.gov.ru/map?query={urllib.parse.quote(cad, safe='')}"
                       f"&active_layers={layers}")
                for wait in ("domcontentloaded", "load"):
                    try:
                        await page.goto(url, wait_until=wait, timeout=timeout_ms)
                        break
                    except Exception:
                        continue
                # дать карте/анти-боту прогрузиться, модалям появиться и закрыться
                await page.wait_for_timeout(2500)
                await _close_modals(page)
                await page.wait_for_timeout(1000)
                feats = await _search_geoportal(page, cad)
                if not feats and captured:               # пассивный fallback
                    feats = list(captured)

                parcel = pick_parcel_feature(feats, cad)
                poly = _geom_to_coords(parcel.get("geometry")) if parcel else None

                # имитировать клик по лупе → карта грузит контур + ОКС в пределах ЗУ;
                # пассивный _on_resp перехватит ОКС. Без клика NSPD данные не тянет.
                if discover and poly:
                    await _trigger_lupa(page, cad)
                    await page.wait_for_timeout(4000)

                buildings: list[dict[str, Any]] = []
                if discover and poly:
                    seen_pool = {id(f): f for f in feats}
                    seen_pool.update({id(f): f for f in captured})
                    cand = []
                    for f in seen_pool.values():
                        if f is parcel:
                            continue
                        coords = _geom_to_coords(f.get("geometry"))
                        if not coords:
                            continue
                        bcad = _feature_cad(f)
                        if bcad and bcad.replace(" ", "") == cad.replace(" ", ""):
                            continue                      # это сам ЗУ
                        cand.append({"cad": bcad,
                                     "geometry": {"type": "Polygon", "coords": coords}})
                    buildings = _N.features_in_polygon(cand, poly)

                out[cad] = {"polygon": poly, "buildings": buildings,
                            "captured": len(set(id(f) for f in (feats or [])) |
                                            set(id(f) for f in captured))}
        finally:
            await browser.close()
    return out


def fetch_parcels(cads: list[str], *, discover: bool = True, headless: bool = True,
                  timeout_ms: int = 45000) -> dict[str, dict[str, Any]]:
    """Синхронно: геометрия ЗУ + ОКС в границах через браузер NSPD (geoportal-search).

    Бросает RuntimeError если нет playwright/браузера/сети."""
    try:
        return asyncio.run(_run(cads, discover=discover, headless=headless,
                                timeout_ms=timeout_ms))
    except ModuleNotFoundError as e:
        raise RuntimeError(
            "Нужен playwright: `pip install playwright` + `playwright install chromium`. "
            f"({e})") from e
