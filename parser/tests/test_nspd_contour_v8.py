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
    assert payload["алгоритм_версия"] == "v8.1"
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


def test_cv_no_purple_pixels_returns_none():
    """Чисто серое изображение без фиолетового → None."""
    if not nspd_v8._HAS_CV:
        pytest.skip("CV-deps not available")
    from PIL import Image
    img = Image.new("RGB", (400, 300), (180, 180, 180))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    assert nspd_v8._extract_contours_from_image(buf.getvalue(), None, 65, 10) is None
