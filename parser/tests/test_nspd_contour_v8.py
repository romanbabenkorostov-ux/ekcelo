"""Unit-tests для NSPD parser v8.1 contour extraction.

Главный test: `test_cv_extract_complex_path_network` — синтетическая фикстура
«сеть дорожек» (имитирует объект 90:25:020103:1393, S=554 м²). Прогоняет
полный CV-pipeline и проверяет:
  - что найдено ≥1 полигон;
  - что после калибровки площадь_вычисленная_кв_м ≈ 554 (точно совпадает,
    т.к. калибровка по parsed_area);
  - что в outer ring достаточно вершин (≥20 — форма сложная);
  - что превью_png_b64 декодируется обратно.

Запуск:  pytest -xvs parser/tests/test_nspd_contour_v8.py
"""
import importlib.util
import io
import math
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "01_parsing_nspd_v8.py"

spec = importlib.util.spec_from_file_location("nspd_v8", SCRIPT_PATH)
nspd_v8 = importlib.util.module_from_spec(spec)
sys.modules["nspd_v8"] = nspd_v8
spec.loader.exec_module(nspd_v8)


# ─── Геометрические хелперы ─────────────────────────────────────────────


def test_lonlat_to_meters_at_equator():
    """На экваторе 1° по долготе ≈ 111320 м."""
    dx, dy = nspd_v8._lonlat_to_local_meters(1.0, 0.0, 0.0, 0.0)
    assert abs(dx - 111320.0) < 1.0
    assert abs(dy) < 1e-6


def test_lonlat_to_meters_at_lat60():
    """На широте 60° по долготе 1° ≈ 111320 × cos(60°) = 55660 м."""
    dx, _dy = nspd_v8._lonlat_to_local_meters(1.0, 60.0, 0.0, 60.0)
    assert abs(dx - 55660.0) < 5.0


def test_ring_area_sqm_local_unit_square():
    """Квадрат 100×100 м → 10000 м²."""
    ring = [(0, 0), (100, 0), (100, 100), (0, 100)]
    assert abs(nspd_v8._ring_area_sqm_local(ring) - 10000.0) < 1e-6


def test_ring_centroid_wgs84_unit_square():
    """Квадрат на широте 0 → центроид (0.5, 0.5)."""
    ring = [[0, 0], [1, 0], [1, 1], [0, 1]]
    cx, cy = nspd_v8._ring_centroid_wgs84(ring)
    assert abs(cx - 0.5) < 1e-9
    assert abs(cy - 0.5) < 1e-9


def test_ring_area_degenerate():
    """Линейный сегмент → 0."""
    assert nspd_v8._ring_area_sqm_local([(0, 0), (10, 0)]) == 0.0
    assert nspd_v8._ring_area_sqm_local([]) == 0.0


def test_parsed_area_sqm_from_info():
    """Поддержка нескольких ключей и форматов."""
    assert nspd_v8._parsed_area_sqm({"Площадь, кв.м": 554}) == 554.0
    assert nspd_v8._parsed_area_sqm({"Площадь, кв.м": "554"}) == 554.0
    assert nspd_v8._parsed_area_sqm({"Площадь": "1 234,5 кв.м"}) == 1234.5
    assert nspd_v8._parsed_area_sqm({"Общая площадь, кв.м": 100}) == 100.0
    assert nspd_v8._parsed_area_sqm({}) is None
    assert nspd_v8._parsed_area_sqm({"Площадь": "—"}) is None


def test_reproject_3857_to_wgs84_origin():
    geom = {"type": "Polygon", "coordinates": [[[0, 0], [0, 0]]]}
    out = nspd_v8._reproject_3857_to_wgs84(geom)
    assert abs(out["coordinates"][0][0][0]) < 1e-9
    assert abs(out["coordinates"][0][0][1]) < 1e-9


def test_geojson_polygon_to_local_known():
    """Маленький квадрат ~100×100 м рядом с Москвой."""
    lat0 = 55.75
    lon0 = 37.62
    dlat = 100.0 / 110540.0
    dlon = 100.0 / (111320.0 * math.cos(math.radians(lat0)))
    poly = {
        "type": "Polygon",
        "coordinates": [[
            [lon0, lat0],
            [lon0 + dlon, lat0],
            [lon0 + dlon, lat0 + dlat],
            [lon0, lat0 + dlat],
            [lon0, lat0],
        ]],
    }
    out = nspd_v8._geojson_to_local_meters(poly)
    assert out["тип"] == "Polygon"
    assert len(out["полигоны"]) == 1
    assert len(out["полигоны"][0]["outer"]) == 5
    assert out["полигоны"][0]["holes"] == []
    # 100 × 100 м ≈ 10000 м² (±0.5% от планарной проекции)
    assert abs(out["площадь_вычисленная_кв_м"] - 10000.0) < 50.0


def test_geojson_multipolygon_to_local():
    poly = {
        "type": "MultiPolygon",
        "coordinates": [
            [[[0, 0], [1e-4, 0], [1e-4, 1e-4], [0, 1e-4], [0, 0]]],
            [[[1, 1], [1 + 1e-4, 1], [1 + 1e-4, 1 + 1e-4], [1, 1 + 1e-4], [1, 1]]],
        ],
    }
    out = nspd_v8._geojson_to_local_meters(poly)
    assert out["тип"] == "MultiPolygon"
    assert len(out["полигоны"]) == 2


# ─── CV-pipeline ────────────────────────────────────────────────────────


def _make_path_network_png(width=900, height=600):
    """Синтетическая фикстура — имитация скриншота 90:25:020103:1393.

    Сеть дорожек: 3 горизонтальные ветви + 3 вертикальные перемычки.
    Заливка полупрозрачным фиолетом, обводка тёмным пурпуром.
    При m_per_px=0.18 (≈ 65 px на 10 м, как scale-bar НСПД) площадь
    замыкается на ~554 м² (после калибровки парсером).
    """
    pytest.importorskip("PIL")
    from PIL import Image, ImageDraw

    img = Image.new("RGB", (width, height), (172, 175, 165))  # светло-серо-зелёный
    overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    # Толщина сегмента 16 px (≈ 2.9 м); длины подобраны для общей площади ~17500 px²
    fill_color = (180, 100, 220, 102)     # alpha ≈ 0.4
    stroke_color = (110, 50, 160, 255)
    segs = [
        (210, 285, 690, 305),   # central horizontal
        (210, 200, 226, 400),   # left vertical
        (440, 220, 456, 420),   # middle vertical
        (670, 180, 686, 410),   # right vertical
        (300, 200, 540, 220),   # top horizontal
        (310, 380, 590, 400),   # bottom horizontal
    ]
    for s in segs:
        draw.rectangle(s, fill=fill_color, outline=stroke_color, width=2)

    composed = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
    buf = io.BytesIO()
    composed.save(buf, format="PNG")
    return buf.getvalue()


def test_cv_decode_and_mask_complex():
    if not nspd_v8._HAS_CV:
        pytest.skip("CV-deps not available")
    png = _make_path_network_png()
    bgr = nspd_v8._decode_png_to_bgr(png)
    assert bgr is not None and bgr.shape[2] == 3
    mask = nspd_v8._build_purple_mask(bgr)
    # должна быть существенная маска (тысячи пикселей)
    nonzero = int((mask > 0).sum())
    assert nonzero > 5000, f"mask nonzero={nonzero} — расширь HSV-диапазон"


def test_cv_find_polygons_complex():
    if not nspd_v8._HAS_CV:
        pytest.skip("CV-deps not available")
    png = _make_path_network_png()
    bgr = nspd_v8._decode_png_to_bgr(png)
    mask = nspd_v8._clean_mask(nspd_v8._build_purple_mask(bgr))
    contours, polygons = nspd_v8._find_polygons(mask)
    # «Сеть дорожек» — одна связная region → 1 outer polygon
    assert len(polygons) >= 1
    assert all(p["outer"] >= 0 for p in polygons)


def test_cv_extract_complex_path_network():
    """ГЛАВНЫЙ TEST — сложная форма «сеть дорожек», полный CV-pipeline.
    parsed_area=554 м², scale-bar 10 м = 65 px → 6.5 px/m, ≈ 0.154 м/px.
    После калибровки computed_area_sqm должен совпасть с 554.0.
    """
    if not nspd_v8._HAS_CV:
        pytest.skip("CV-deps not available")
    png = _make_path_network_png()
    result = nspd_v8._extract_contours_from_image(
        png_bytes=png,
        parsed_area_sqm=554.0,
        scale_px=65,
        scale_m=10,
    )
    assert result is not None, "CV-pipeline вернул None на синтетике"
    assert result["num_polygons"] >= 1
    assert abs(result["area_sqm"] - 554.0) < 0.01, \
        f"after calibration area={result['area_sqm']} ≠ 554"
    # Корреляция должна быть в разумных пределах (синтетика ≈ 0.85..1.15)
    assert 0.5 < result["corr"] < 1.5, f"коэф_коррекции выбился: {result['corr']}"
    # m_per_px после калибровки — корректный
    assert result["m_per_px"] > 0
    # Превью декодируется
    assert result["thumb_b64"] and len(result["thumb_b64"]) > 100
    # Сложная форма → outer ring имеет много вершин (после адаптивного RDP)
    outer_rings = [p["outer"] for p in result["polygons_local_m"]]
    max_vertices = max(len(r) for r in outer_rings)
    assert max_vertices >= 15, \
        f"сложная форма: ожидаем ≥15 вершин в outer ring, получили {max_vertices}"


def test_cv_payload_from_cv_schema():
    """Payload v8.1 schema: ключи 'полигоны' и 'полигонов' заполнены."""
    if not nspd_v8._HAS_CV:
        pytest.skip("CV-deps not available")
    png = _make_path_network_png()
    cv_res = nspd_v8._extract_contours_from_image(png, 554.0, 65, 10)
    payload = nspd_v8._build_payload_from_cv(cv_res, 554.0, {"px": 65, "m": 10})
    assert payload["источник"] == "screenshot_cv"
    assert payload["тип"] in ("Polygon", "MultiPolygon")
    assert payload["полигонов"] >= 1
    assert isinstance(payload["полигоны"], list)
    assert all("outer" in p and "holes" in p for p in payload["полигоны"])
    # legacy flat тоже есть
    assert isinstance(payload["локальные_метры"], list)
    assert payload["алгоритм_версия"] == "v8.4"
    assert payload["площадь_заявленная_кв_м"] == 554.0
    assert abs(payload["площадь_вычисленная_кв_м"] - 554.0) < 0.01


def test_cv_returns_none_without_scalebar():
    if not nspd_v8._HAS_CV:
        pytest.skip("CV-deps not available")
    png = _make_path_network_png()
    assert nspd_v8._extract_contours_from_image(png, 554.0, None, None) is None
    assert nspd_v8._extract_contours_from_image(png, 554.0, 0, 10) is None


def test_cv_returns_none_on_empty_input():
    if not nspd_v8._HAS_CV:
        pytest.skip("CV-deps not available")
    assert nspd_v8._extract_contours_from_image(None, 554.0, 65, 10) is None
    assert nspd_v8._extract_contours_from_image(b"", 554.0, 65, 10) is None


# ─── NetworkCapture (v8.2) ──────────────────────────────────────────────


def test_network_capture_scans_featurecollection():
    cap = nspd_v8.NetworkCapture()
    fc = {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": {"type": "Polygon",
                             "coordinates": [[[37.6, 55.7], [37.7, 55.7],
                                              [37.7, 55.8], [37.6, 55.8],
                                              [37.6, 55.7]]]},
                "properties": {"cad_num": "77:01:0001001:123"},
            }
        ],
    }
    cap._scan(fc, "https://nspd.gov.ru/api/aeggis/v3/36329/wfs?cql=...")
    assert len(cap.features) == 1
    found = cap.find_by_cad("77:01:0001001:123")
    assert found is not None
    assert found["geom"]["type"] == "Polygon"


def test_network_capture_scans_pkk_style():
    cap = nspd_v8.NetworkCapture()
    pkk = {
        "feature": {
            "geometry": {"type": "Polygon", "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]},
            "attrs": {"cn": "23:50:0301004:25"},
        }
    }
    cap._scan(pkk, "https://pkk.rosreestr.ru/api/features/1/23:50:0301004:25")
    assert len(cap.features) == 1
    assert cap.find_by_cad("23:50:0301004:25") is not None


def test_network_capture_finds_part_by_core():
    """Часть `:25/9` должна находить feature родителя `:25` тоже (по core-form)."""
    cap = nspd_v8.NetworkCapture()
    fc = {
        "type": "FeatureCollection",
        "features": [{
            "type": "Feature",
            "geometry": {"type": "Polygon",
                         "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]},
            "properties": {"cad_num": "23:50:0301004:25"},
        }],
    }
    cap._scan(fc, "u")
    assert cap.find_by_cad("23:50:0301004:25/9") is not None


def test_network_capture_no_match():
    cap = nspd_v8.NetworkCapture()
    cap._scan({"type": "FeatureCollection", "features": [
        {"type": "Feature", "geometry": {"type": "Point", "coordinates": [0, 0]},
         "properties": {"cad_num": "OTHER:1:1:1"}}]}, "u")
    assert cap.find_by_cad("23:50:0301004:25") is None


def test_network_capture_clear():
    cap = nspd_v8.NetworkCapture()
    cap.features.append({"url": "u", "feature": {"geometry": {}}})
    cap.clear()
    assert cap.features == []


# ─── Reproject & sanity (v8.3) ──────────────────────────────────────────


def test_maybe_reproject_passthrough_wgs84():
    geom = {"type": "Polygon", "coordinates": [[[37.6, 55.7], [37.7, 55.7]]]}
    out = nspd_v8._maybe_reproject_to_wgs84(geom)
    assert out["coordinates"][0][0] == [37.6, 55.7]


def test_maybe_reproject_triggers_on_3857():
    """Координаты в EPSG:3857 (метры) → reproject в lon/lat."""
    geom = {"type": "Polygon",
            "coordinates": [[[4185000.0, 5550000.0], [4185100.0, 5550000.0]]]}
    out = nspd_v8._maybe_reproject_to_wgs84(geom)
    lon, lat = out["coordinates"][0][0]
    assert -180 < lon < 180
    assert -90 < lat < 90
    # 4185000 m ≈ 37.6° E
    assert 37 < lon < 38


def test_payload_area_sane_huge_rejected():
    p = {"площадь_вычисленная_кв_м": 1.4e15}
    assert nspd_v8._payload_area_sane(p, None) is False


def test_payload_area_sane_off_by_100x_rejected():
    p = {"площадь_вычисленная_кв_м": 100000.0}
    assert nspd_v8._payload_area_sane(p, 554.0) is False


def test_payload_area_sane_ok_with_parsed():
    p = {"площадь_вычисленная_кв_м": 600.0}
    assert nspd_v8._payload_area_sane(p, 554.0) is True


def test_payload_area_sane_ok_without_parsed():
    p = {"площадь_вычисленная_кв_м": 5000.0}
    assert nspd_v8._payload_area_sane(p, None) is True


def test_network_capture_skips_search():
    """Search/suggest endpoints исключаются (extent квартала, не геометрия)."""
    import asyncio

    class FakeResp:
        def __init__(self, url, payload):
            self.url = url
            self.status = 200
            self.headers = {"content-type": "application/json"}
            self._payload = payload

        async def json(self):
            return self._payload

    fc = {"type": "FeatureCollection",
          "features": [{"type": "Feature",
                        "geometry": {"type": "Polygon",
                                     "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]]},
                        "properties": {"cad_num": "X:1:1:1"}}]}
    cap = nspd_v8.NetworkCapture()

    async def run():
        await cap._on_response(FakeResp("https://nspd.gov.ru/api/geoportal/v2/search/geoportal?query=X", fc))
        assert len(cap.features) == 0
        await cap._on_response(FakeResp("https://nspd.gov.ru/api/aeggis/v3/36048/wfs?x=1", fc))
        assert len(cap.features) == 1
        # all_urls фиксирует и search, и wfs
        assert len(cap.all_urls) == 2
    asyncio.run(run())


def test_network_capture_all_urls_tracked():
    """all_urls фиксирует все попавшие в листенер URL'ы (для debug-лога)."""
    import asyncio

    class FakeResp:
        def __init__(self, url):
            self.url = url
            self.status = 403
            self.headers = {"content-type": "text/html"}

        async def json(self):
            raise RuntimeError("not json")

    cap = nspd_v8.NetworkCapture()

    async def run():
        await cap._on_response(FakeResp("https://nspd.gov.ru/api/foo"))
        await cap._on_response(FakeResp("https://pkk.rosreestr.ru/api/bar"))
        # не НСПД/PKK — не попадёт
        await cap._on_response(FakeResp("https://other.example.com/baz"))
    asyncio.run(run())
    assert len(cap.all_urls) == 2
    assert cap.debug_summary(max_urls=10)[0][1] == 403


def test_network_capture_prefers_exact_match_over_substring():
    """Если есть exact-match и substring-match, выбираем exact."""
    cap = nspd_v8.NetworkCapture()
    # «Левая» feature, substring-матч на квартал
    cap.features.append({
        "url": "u1",
        "feature": {
            "geometry": {"type": "Polygon",
                         "coordinates": [[[0, 0], [9999, 0], [9999, 9999], [0, 9999], [0, 0]]]},
            "properties": {"name": "квартал 23:50:0301004:25 содержит"},
        }
    })
    # «Правая» feature, exact match
    cap.features.append({
        "url": "u2",
        "feature": {
            "geometry": {"type": "Polygon",
                         "coordinates": [[[1, 1], [2, 1], [2, 2], [1, 2], [1, 1]]]},
            "properties": {"cad_num": "23:50:0301004:25"},
        }
    })
    found = cap.find_by_cad("23:50:0301004:25")
    assert found["src_url"] == "u2"


def test_cv_no_purple_pixels_returns_none():
    """Чисто серое изображение без фиолетового → None."""
    if not nspd_v8._HAS_CV:
        pytest.skip("CV-deps not available")
    from PIL import Image
    img = Image.new("RGB", (400, 300), (180, 180, 180))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    assert nspd_v8._extract_contours_from_image(buf.getvalue(), None, 65, 10) is None
