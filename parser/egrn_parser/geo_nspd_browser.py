"""
egrn_parser/geo_nspd_browser.py — получение геометрии из NSPD через БРАУЗЕР (Playwright).

Зачем: NSPD/ПКК блокируют голый HTTP анти-ботом (WFS-эндпоинт отдаёт 403). Надёжный
путь — открыть карту NSPD в браузере и **пассивно перехватить** geometry из её
сетевых ответов (`NetworkCapture` из `scripts/01_parsing_nspd_v8.py`): карта сама
грузит контур своим текущим API. Геометрия выбирается `find_by_cad` (точное>substring)
и репроецируется 3857→WGS84 (`_maybe_reproject_to_wgs84`). ОКС в границах ЗУ — из тех
же перехваченных feature, отфильтрованных по centroid-in-polygon.

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


def _norm_geom_any(g: Optional[dict], v8) -> Optional[list]:
    """Репроекция 3857→WGS84 (если надо) + → coords полигона."""
    if not g:
        return None
    return _norm_geom(v8._maybe_reproject_to_wgs84(g))


async def _run(cads: list[str], *, discover: bool, headless: bool,
               timeout_ms: int) -> dict[str, dict[str, Any]]:
    from playwright.async_api import async_playwright
    v8 = _load_v8()
    out: dict[str, dict[str, Any]] = {}
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=headless)
        ctx = await browser.new_context(ignore_https_errors=True)
        page = await ctx.new_page()
        capture = v8.NetworkCapture()
        capture.attach(page)
        try:
            for cad in cads:
                capture.clear()
                # карта сама грузит геометрию своим текущим API → ловим пассивно
                # (WFS-эндпоинт теперь отдаёт 403). active_layers=ЗУ+ОКС, чтобы
                # подгрузились и строения для обнаружения в границах.
                layers = ",".join(str(x) for x in (v8.NSPD_ZU_IDS + v8.NSPD_OKS_IDS))
                url = (f"https://nspd.gov.ru/map?query={cad.replace(':', '%3A')}"
                       f"&active_layers={layers}")
                try:
                    await page.goto(url, wait_until="domcontentloaded", timeout=timeout_ms)
                except Exception:
                    try:
                        await page.goto(url, wait_until="load", timeout=timeout_ms)
                    except Exception:
                        pass
                # ждём появления feature нужного КН (poll до timeout)
                hit = None
                for _ in range(max(1, timeout_ms // 700)):
                    await page.wait_for_timeout(700)
                    hit = capture.find_by_cad(cad)
                    if hit:
                        break
                poly = _norm_geom_any(hit["geom"], v8) if hit else None

                buildings: list[dict[str, Any]] = []
                if discover and poly:
                    feats = []
                    for entry in capture.features:    # все захваченные объекты карты
                        ng = _norm_geom_any(entry["feature"].get("geometry"), v8)
                        if not ng:
                            continue
                        props = entry["feature"].get("properties") or entry["feature"].get("attrs") or {}
                        bcad = _N._feat_cad(props)
                        if bcad and bcad.replace(" ", "") == cad.replace(" ", ""):
                            continue                  # это сам ЗУ
                        feats.append({"cad": bcad, "geometry": {"type": "Polygon", "coords": ng}})
                    buildings = _N.features_in_polygon(feats, poly)
                out[cad] = {"polygon": poly, "buildings": buildings,
                            "captured": len(capture.features)}
        finally:
            capture.detach()
            await browser.close()
    return out


def fetch_parcels(cads: list[str], *, discover: bool = True, headless: bool = True,
                  timeout_ms: int = 45000) -> dict[str, dict[str, Any]]:
    """Синхронно: геометрия ЗУ + ОКС в границах через браузер NSPD (NetworkCapture).

    Бросает RuntimeError если нет playwright/браузера/сети."""
    try:
        return asyncio.run(_run(cads, discover=discover, headless=headless, timeout_ms=timeout_ms))
    except ModuleNotFoundError as e:
        raise RuntimeError(
            "Нужен playwright: `pip install playwright` + `playwright install chromium`. "
            f"({e})") from e
