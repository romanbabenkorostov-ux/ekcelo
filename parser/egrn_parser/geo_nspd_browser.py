"""
egrn_parser/geo_nspd_browser.py — получение геометрии из NSPD через БРАУЗЕР (Playwright).

Зачем: NSPD/ПКК блокируют голый HTTP анти-ботом, поэтому надёжный путь — через
браузерную сессию с куками (как в `scripts/01_parsing_nspd_v8.py`). Здесь
переиспользуются ПРОВЕРЕННЫЕ функции v8 (`_fetch_geom_via_wfs`/`_fetch_geom_via_pkk`)
для геометрии ЗУ по КН, плюс WFS BBOX-запрос через `page.request` для обнаружения
ОКС в границах участка.

Требует: установленный `playwright` + браузер (`playwright install chromium`) и сеть.
В закрытом контуре/без playwright — `fetch_parcels` бросит понятную ошибку; вызывающий
(CLI `kmz --nspd`) ловит и сообщает, предлагая `--nspd-http` (лёгкий путь) или
загрузку контуров заранее.

Выход: {cad: {"polygon": coords|None, "buildings": [{name, geometry}]}}.
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from typing import Any, Optional

from egrn_parser import geo_nspd as _N


def _load_v8():
    """Импортировать scripts/01_parsing_nspd_v8.py (требует playwright)."""
    path = Path(__file__).resolve().parents[1] / "scripts" / "01_parsing_nspd_v8.py"
    if not path.exists():
        raise RuntimeError(f"не найден NSPD-парсер: {path}")
    spec = importlib.util.spec_from_file_location("nspd_v8_browser", path)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["nspd_v8_browser"] = mod
    spec.loader.exec_module(mod)                      # упадёт, если нет playwright
    return mod


def _norm_geom(g: Optional[dict]) -> Optional[list]:
    """GeoJSON (от v8) → coords полигона (внешние кольца) для geo_kmz/land_contours."""
    if not g:
        return None
    t = g.get("type"); c = g.get("coordinates")
    if t == "Polygon":
        return c
    if t == "MultiPolygon" and c:
        return c[0]
    return None


async def _run(cads: list[str], *, discover: bool, headless: bool,
               timeout_ms: int) -> dict[str, dict[str, Any]]:
    from playwright.async_api import async_playwright
    v8 = _load_v8()
    wfs_headers = {"Referer": "https://nspd.gov.ru/map", "Origin": "https://nspd.gov.ru",
                   "Accept": "application/json, */*"}
    out: dict[str, dict[str, Any]] = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        ctx = await browser.new_context(ignore_https_errors=True)
        page = await ctx.new_page()
        try:
            for cad in cads:
                # сессия: открыть карту с запросом по КН (как в v8) — даёт куки/анти-бот
                try:
                    await page.goto(f"https://nspd.gov.ru/map?query={cad.replace(':', '%3A')}",
                                    wait_until="domcontentloaded", timeout=timeout_ms)
                except Exception:
                    pass
                # геометрия ЗУ: проверенный путь v8 (WFS → PKK fallback)
                res = await v8._fetch_geom_via_wfs(page, cad)
                if not res:
                    res = await v8._fetch_geom_via_pkk(page, cad)
                poly = _norm_geom(res.get("geom")) if res else None
                buildings: list[dict[str, Any]] = []
                if discover and poly:
                    from egrn_parser.geo_kmz import _ring, bbox as _bbox
                    bb = _bbox(_ring(poly))
                    feats = []
                    for lid in _N.NSPD_OKS_LAYERS:
                        try:
                            r = await page.request.get(_N.wfs_bbox_url(lid, bb),
                                                       headers=wfs_headers, timeout=timeout_ms)
                            if r.status == 200:
                                feats += _N.parse_wfs_features(await r.json())
                        except Exception:
                            continue
                    buildings = _N.features_in_polygon(feats, poly)
                out[cad] = {"polygon": poly, "buildings": buildings}
        finally:
            await browser.close()
    return out


def fetch_parcels(cads: list[str], *, discover: bool = True, headless: bool = True,
                  timeout_ms: int = 45000) -> dict[str, dict[str, Any]]:
    """Синхронно: геометрия ЗУ + ОКС в границах через браузер NSPD.

    Бросает RuntimeError/ImportError если нет playwright/браузера/сети."""
    try:
        return asyncio.run(_run(cads, discover=discover, headless=headless, timeout_ms=timeout_ms))
    except ModuleNotFoundError as e:
        raise RuntimeError(
            "Нужен playwright: `pip install playwright` + `playwright install chromium`. "
            f"({e})") from e
