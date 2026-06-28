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
import re
import urllib.parse
from typing import Any, Optional

from egrn_parser import geo_nspd as _N

# КН РФ: 2:2:6-7:N (квартал/участок). Ловим в любом тексте ответа NSPD.
_CAD_RE = re.compile(r"\b\d{2}:\d{1,2}:\d{5,7}:\d+\b")


def collect_cads(payload: Any) -> set[str]:
    """Рекурсивно собрать ВСЕ кадастровые номера из JSON-ответа (включая
    атрибутивные таблицы вкладки «ОКС в пределах ЗУ», где геометрии нет)."""
    found: set[str] = set()

    def walk(node, depth=0):
        if depth > 8 or node is None:
            return
        if isinstance(node, str):
            found.update(_CAD_RE.findall(node))
        elif isinstance(node, dict):
            for v in node.values():
                walk(v, depth + 1)
        elif isinstance(node, list):
            for v in node:
                walk(v, depth + 1)

    walk(payload)
    return found

# Современный geoportal-API NSPD (тот, что дёргает строка поиска / лупа).
GEOPORTAL_SEARCH = "https://nspd.gov.ru/api/geoportal/v2/search/geoportal"
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


async def _geoportal_get(page, cad: str, theme_ids=()) -> list[dict]:
    """Один проход geoportal-search по вариантам запроса (без ретраев/модалей).

    theme_ids — id поисковых тем NSPD (ЗУ в дефолтной теме, ОКС — в другой;
    перебор по темам находит объект независимо от того, где он индексируется)."""
    q = urllib.parse.quote(cad, safe="")
    urls = [f"{GEOPORTAL_SEARCH}?query={q}"]
    for tid in (theme_ids or ()):
        urls.append(f"{GEOPORTAL_SEARCH}?thematicSearchId={tid}&query={q}")
    for url in urls:
        try:
            resp = await page.request.get(url, headers={
                "Referer": "https://nspd.gov.ru/map",
                "Accept": "application/json, */*",
            }, timeout=20000)
            if not resp.ok:
                continue
            feats = extract_features(json.loads(await resp.text()))
            if feats:
                return feats
        except Exception:
            continue
    return []


async def _search_geoportal(page, cad: str, theme_ids=()) -> list[dict]:
    """geoportal-search по КН с ретраями и закрытием модалей (для геометрии ЗУ)."""
    for attempt in range(3):
        if attempt > 0:
            await page.wait_for_timeout(500)
        await _close_modals(page)
        feats = await _geoportal_get(page, cad, theme_ids)
        if feats:
            return feats
    return []


SEARCH_THEMES = "https://nspd.gov.ru/api/geoportal/v1/search-theme?pageCode=geoportal"


async def _fetch_search_themes(page) -> list[tuple]:
    """Список поисковых тем NSPD → [(id, name)]. Темы ЗУ/ОКС/границ и т.д.;
    нужны, чтобы искать ОКС в их теме (в дефолтной индексируются только ЗУ)."""
    try:
        resp = await page.request.get(SEARCH_THEMES, headers={
            "Referer": "https://nspd.gov.ru/map",
            "Accept": "application/json, */*",
        }, timeout=20000)
        if not resp.ok:
            return []
        data = json.loads(await resp.text())
    except Exception:
        return []
    items = data.get("data") if isinstance(data, dict) else data
    out: list[tuple] = []

    def walk(node, depth=0):
        if depth > 5 or node is None:
            return
        if isinstance(node, list):
            for x in node:
                walk(x, depth + 1)
        elif isinstance(node, dict):
            tid = node.get("id") or node.get("thematicSearchId") or node.get("themeId")
            name = node.get("title") or node.get("name") or node.get("label")
            if tid is not None and name:
                out.append((tid, str(name)))
            for v in node.values():
                walk(v, depth + 1)

    walk(items)
    # уникальные по id, сохраняя порядок
    seen, uniq = set(), []
    for tid, name in out:
        if tid not in seen:
            seen.add(tid)
            uniq.append((tid, name))
    return uniq


# Эндпоинт списка ОКС в пределах ЗУ (выявлен по диагностике сетевых запросов NSPD).
OBJECTS_LIST = ("https://nspd.gov.ru/api/geoportal/v1/tab-group-data"
                "?tabClass=objectsList&categoryId={cat}&geomId={gid}")


def _parcel_ids(feature: Optional[dict]) -> tuple:
    """Достать (geomId, categoryId) из geoportal-feature ЗУ для запроса списка ОКС."""
    if not feature:
        return (None, None)
    props = feature.get("properties") or {}
    gid = (feature.get("id") or props.get("geomId") or props.get("geom_id")
           or props.get("interactionId"))
    cat = (props.get("category") or props.get("categoryId")
           or props.get("category_id"))
    return (gid, cat)


async def _fetch_objects_list(page, geom_id, cat_id) -> set[str]:
    """GET список ОКС в пределах ЗУ (tab-group-data objectsList) → множество КН."""
    if not geom_id or not cat_id:
        return set()
    url = OBJECTS_LIST.format(cat=cat_id, gid=geom_id)
    try:
        resp = await page.request.get(url, headers={
            "Referer": "https://nspd.gov.ru/map",
            "Accept": "application/json, */*",
        }, timeout=20000)
        if not resp.ok:
            return set()
        return collect_cads(json.loads(await resp.text()))
    except Exception:
        return set()


async def _resolve_geom(page, cad: str, theme_ids=()) -> Optional[dict]:
    """КН ОКС → геометрия {type, coords} через geoportal-search.

    Возвращает контур (Polygon) если есть; иначе реальную точку (Point) из NSPD;
    None — если объект вообще не нашёлся (тогда вызывающий ставит точку по спирали).
    Точку NSPD предпочитаем спирали — она настоящая, а не синтетическая."""
    feats = await _geoportal_get(page, cad, theme_ids)
    if not feats:
        return None
    want = cad.replace(" ", "").upper()
    chosen = None
    for f in feats:
        if (_feature_cad(f) or "").replace(" ", "").upper() == want:
            chosen = f
            break
    chosen = chosen or feats[0]
    g = _reproject(chosen.get("geometry"))
    if not g or not g.get("coordinates"):
        return None
    t = g.get("type")
    if t == "Polygon":
        return {"type": "Polygon", "coords": g["coordinates"]}
    if t == "MultiPolygon":
        return {"type": "Polygon", "coords": g["coordinates"][0]}
    if t == "Point":
        return {"type": "Point", "coords": [g["coordinates"]]}
    return None


async def _run(cads: list[str], *, discover: bool, headless: bool,
               timeout_ms: int, manual: bool = False) -> dict[str, dict[str, Any]]:
    from playwright.async_api import async_playwright

    out: dict[str, dict[str, Any]] = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless and not manual)
        ctx = await browser.new_context(ignore_https_errors=True,
                                        user_agent="Mozilla/5.0")
        page = await ctx.new_page()

        # Разрешающий слушатель: копим geoportal-feature (в т.ч. из /search/),
        # которые v8.NetworkCapture отбрасывает. Источник ОКС + пассивный fallback.
        captured: list[dict] = []
        seen_cads: set[str] = set()          # все КН из ответов (ручной режим)
        diag: list[tuple] = []               # (url, keys, n_feats, n_cads) — диагностика

        async def _on_resp(resp):
            try:
                url = resp.url
                # в ручном режиме данные вкладок (ОКС в пределах) идут не только с
                # /geoportal/ — ловим любой JSON c nspd, extract_features отсеет лишнее.
                if "nspd.gov.ru" not in url:
                    return
                if not manual and "geoportal" not in url:
                    return
                ct = (resp.headers or {}).get("content-type", "")
                if "json" not in ct.lower() and "json" not in url.lower():
                    return
                data = json.loads(await resp.text())
                feats = extract_features(data)
                captured.extend(feats)
                if manual:
                    cads = collect_cads(data)
                    seen_cads.update(cads)
                    keys = list(data.keys())[:6] if isinstance(data, dict) else type(data).__name__
                    diag.append((url.split("nspd.gov.ru")[-1][:90], keys, len(feats), len(cads)))
            except Exception:
                return

        page.on("response", lambda r: asyncio.create_task(_on_resp(r)))

        theme_ids: list = []
        try:
            for cad in cads:
                captured.clear()
                seen_cads.clear()
                diag.clear()
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
                if not theme_ids:                         # один раз: темы поиска NSPD
                    themes = await _fetch_search_themes(page)
                    theme_ids = [t[0] for t in themes]
                    if themes:
                        print("  [темы поиска NSPD] " +
                              "; ".join(f"{i}={n}" for i, n in themes), flush=True)
                feats = await _search_geoportal(page, cad, theme_ids)
                if not feats and captured:               # пассивный fallback
                    feats = list(captured)

                parcel = pick_parcel_feature(feats, cad)
                poly = _geom_to_coords(parcel.get("geometry")) if parcel else None

                idx = cads.index(cad) + 1
                print(f"  [{idx}/{len(cads)}] ЗУ {cad}: "
                      f"{'контур ✓' if poly else 'контур ✗'}", flush=True)

                if manual:
                    # Ручной режим: пользователь сам жмёт лупу и листает вкладки;
                    # ждём Enter БЕЗ блокировки event-loop (иначе перехват встанет).
                    print(f"      ▶ нажмите лупу + откройте вкладку «Объекты в "
                          f"пределах», затем ENTER здесь…", flush=True)
                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, input)
                    if captured and not poly:
                        parcel = pick_parcel_feature(list(captured), cad)
                        poly = _geom_to_coords(parcel.get("geometry")) if parcel else None
                    print(f"      [диаг] JSON-ответов: {len(diag)}; КН в ответах: "
                          f"{len(seen_cads)}; feature: {len(captured)}", flush=True)

                buildings: list[dict[str, Any]] = []
                if (discover or manual) and poly:
                    # 1) список ОКС в пределах ЗУ — прямой запрос objectsList по
                    #    geomId/categoryId самого ЗУ (надёжнее ручного листания).
                    geom_id, cat_id = _parcel_ids(parcel)
                    oks = await _fetch_objects_list(page, geom_id, cat_id)
                    # 2) добор из перехваченного (ручные клики по вкладкам) — на случай,
                    #    если прямой запрос пуст.
                    oks |= {c for c in seen_cads}
                    oks = {c for c in oks if c.replace(" ", "") != cad.replace(" ", "")}
                    if oks:
                        print(f"      ОКС в пределах: {len(oks)} — резолвлю геометрию…",
                              flush=True)
                    # 3) геометрия каждого ОКС: контур (Polygon) > реальная точка
                    #    (Point) > спираль (None). Точка NSPD точнее синтетической спирали.
                    n_cont = n_pt = n_spi = 0
                    for j, oc in enumerate(sorted(oks), 1):
                        g = await _resolve_geom(page, oc, theme_ids)
                        buildings.append({"name": oc, "geometry": g})
                        if g and g["type"] == "Polygon":
                            mark = "контур"; n_cont += 1
                        elif g and g["type"] == "Point":
                            mark = "точка"; n_pt += 1
                        else:
                            mark = "спираль"; n_spi += 1
                        print(f"        {j}/{len(oks)} {oc}: {mark}", flush=True)
                    if oks:
                        print(f"      → контур: {n_cont}, точка: {n_pt}, спираль: {n_spi}",
                              flush=True)

                out[cad] = {"polygon": poly, "buildings": buildings,
                            "captured": len(captured)}
        finally:
            await browser.close()
    return out


def fetch_parcels(cads: list[str], *, discover: bool = True, headless: bool = True,
                  timeout_ms: int = 45000, manual: bool = False) -> dict[str, dict[str, Any]]:
    """Синхронно: геометрия ЗУ + ОКС в границах через браузер NSPD (geoportal-search).

    manual=True — пользователь сам жмёт лупу и листает вкладки, скрипт ждёт Enter
    по каждому КН и парсит перехваченное (видимый браузер принудительно).
    Бросает RuntimeError если нет playwright/браузера/сети."""
    try:
        return asyncio.run(_run(cads, discover=discover, headless=headless,
                                timeout_ms=timeout_ms, manual=manual))
    except ModuleNotFoundError as e:
        raise RuntimeError(
            "Нужен playwright: `pip install playwright` + `playwright install chromium`. "
            f"({e})") from e
