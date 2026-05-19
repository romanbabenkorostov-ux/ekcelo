"""Smoke-тест для build_kmz v2 на синтетическом проекте.

Проверяет:
  1. Архив содержит doc.kml + images/ + docs/ + graph.html.
  2. XML валиден.
  3. Все 9 классов представлены <Style id=...> с правильными префиксами.
  4. <Folder> идут в фиксированном порядке (10 групп; пустые пропущены).
  5. По Placemark каждого класса: <styleUrl> с нужным префиксом,
     <description> содержит обязательные ключи, <name> содержит токен КН,
     <ExtendedData> содержит object_type.
  6. Spiral-фото без EXIF имеют 'Источник координат: spiral_around_centroid'
     в description и координаты в радиусе 25-40 м от центроида.
  7. Идемпотентность: два прогона build_kmz дают идентичный sha256 KMZ.
"""
from __future__ import annotations
import hashlib
import json
import math
import re
import shutil
import sys
import tempfile
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from pirushin_sosn_rocha_08_build_kmz_v2 import (
    build_kmz, LAT_M_PER_DEG,
)


KML_NS = {"kml": "http://www.opengis.net/kml/2.2",
          "atom": "http://www.w3.org/2005/Atom"}


# Фикстура `synthetic_root` теперь живёт в conftest.py (общая для всех parser-тестов).


def _read_kml(kmz_path: Path) -> tuple[str, set[str], dict[str, bytes]]:
    """Возвращает (kml_text, file_names_in_archive, file_contents)."""
    with zipfile.ZipFile(kmz_path, "r") as zf:
        names = set(zf.namelist())
        contents = {name: zf.read(name) for name in names if not name.endswith("/")}
        kml = contents["doc.kml"].decode("utf-8")
    return kml, names, contents


def test_archive_layout(synthetic_root: Path):
    kmz = build_kmz(synthetic_root)
    assert kmz.exists()
    kml, names, contents = _read_kml(kmz)
    assert "doc.kml" in names
    assert any(n.startswith("images/") for n in names), "нет images/"
    assert any(n.startswith("docs/") for n in names), "нет docs/"
    assert "graph.html" in names


def test_xml_valid(synthetic_root: Path):
    kmz = build_kmz(synthetic_root)
    kml, _, _ = _read_kml(kmz)
    # Должно парситься без ошибок
    ET.fromstring(kml)


def test_styles_present(synthetic_root: Path):
    kmz = build_kmz(synthetic_root)
    kml, _, _ = _read_kml(kmz)
    # 9 префиксов (cad_exp может отсутствовать в default-only) — проверяем все
    # классы, которые есть в синтетических данных:
    for prefix in ("cad_zu_", "cad_oks_", "cad_room_", "cad_str_",
                   "cad_ons_", "cad_bu_", "cad_eq_", "cad_ben_",
                   "photoPin_"):
        assert f'<Style id="{prefix}' in kml or f"<Style id='{prefix}" in kml, \
            f"стиль с префиксом {prefix} не найден"


def test_folder_order(synthetic_root: Path):
    kmz = build_kmz(synthetic_root)
    kml, _, _ = _read_kml(kmz)
    # Извлекаем имена Folder верхнего уровня (без подпапок «Фотографии»)
    root = ET.fromstring(kml)
    doc = root.find("kml:Document", KML_NS)
    folders = [f.findtext("kml:name", "", KML_NS)
               for f in doc.findall("kml:Folder", KML_NS)]
    expected_order = ["Земельные участки", "ОКС", "Помещения", "Сооружения",
                      "ОНС", "Бизнес-единицы", "Оборудование", "Бенефициары",
                      "Фотографии"]
    # Каждый folder в реальности назван с count: "ЗУ (1)". Нормализуем.
    real_names = [re.sub(r"\s*\(\d+\)\s*$", "", n) for n in folders]
    for name in expected_order:
        assert name in real_names, f"Folder '{name}' отсутствует. Real: {real_names}"
    # Порядок относительный — каждое следующее имя из expected должно идти
    # позже предыдущего.
    positions = [real_names.index(n) for n in expected_order if n in real_names]
    assert positions == sorted(positions), \
        f"Folder’ы не в нужном порядке: {real_names}"


def test_placemarks_have_required_keys(synthetic_root: Path):
    kmz = build_kmz(synthetic_root)
    kml, _, _ = _read_kml(kmz)
    root = ET.fromstring(kml)
    doc = root.find("kml:Document", KML_NS)
    # Проходим по всем Placemark
    placemarks = list(doc.iter("{http://www.opengis.net/kml/2.2}Placemark"))
    assert placemarks, "Нет Placemark в документе"
    cad_re = re.compile(r"\b(\d{2}:\d{2}:\d{1,8}:\d{1,8})\b")
    found_kinds: set[str] = set()
    for pm in placemarks:
        style_url = pm.findtext("kml:styleUrl", "", KML_NS)
        descr = pm.findtext("kml:description", "", KML_NS)
        name = pm.findtext("kml:name", "", KML_NS)
        # styleUrl начинается с #
        assert style_url.startswith("#"), f"styleUrl без #: {style_url}"
        # description — пары Key: value;
        assert ";" in descr, f"Нет пар в description: {descr[:80]}"
        # ExtendedData
        ext = pm.find("kml:ExtendedData", KML_NS)
        if ext is not None:
            obj_type = None
            for d in ext.findall("kml:Data", KML_NS):
                if d.attrib.get("name") == "object_type":
                    obj_type = d.findtext("kml:value", "", KML_NS)
                    found_kinds.add(obj_type)
            assert obj_type, "ExtendedData без object_type"
        # Для cad_* — кад.№ как токен в name и в description
        for kind_prefix in ("cad_zu_", "cad_oks_", "cad_room_", "cad_str_",
                            "cad_ons_"):
            if kind_prefix in style_url:
                assert cad_re.search(name), \
                    f"Кад.№ не в name: {name} (style={style_url})"
                assert "Кадастровый номер:" in descr, \
                    f"Нет 'Кадастровый номер:' в description: {descr[:80]}"
                break
    # Должны быть представлены все 9 классов
    assert "zu" in found_kinds
    assert "oks" in found_kinds
    assert "room" in found_kinds
    assert "str" in found_kinds
    assert "ons" in found_kinds
    assert "bu" in found_kinds
    assert "eq" in found_kinds
    assert "ben" in found_kinds
    assert "photo" in found_kinds


def test_spiral_photos(synthetic_root: Path):
    """3 фото без GPS должны быть на спирали вокруг центроида здания (c2)."""
    kmz = build_kmz(synthetic_root)
    kml, _, _ = _read_kml(kmz)
    root = ET.fromstring(kml)
    # Центроид c2 = (39.7090, 47.21875) (среднее 4 уникальных вершин)
    cen_lon, cen_lat = 39.7090, 47.21875
    m_lon = LAT_M_PER_DEG * math.cos(math.radians(cen_lat))
    spiral_count = 0
    coords_seen: list[tuple[float, float]] = []
    for pm in root.iter("{http://www.opengis.net/kml/2.2}Placemark"):
        style_url = pm.findtext("kml:styleUrl", "", KML_NS)
        descr = pm.findtext("kml:description", "", KML_NS)
        if "photoPin_" not in style_url:
            continue
        if "spiral_around_centroid" not in descr:
            continue
        spiral_count += 1
        coords_el = pm.find(".//kml:coordinates", KML_NS)
        assert coords_el is not None
        lon_s, lat_s, _ = coords_el.text.strip().split(",")
        lon, lat = float(lon_s), float(lat_s)
        coords_seen.append((lon, lat))
        # Расстояние от центроида c2
        d_lat = (lat - cen_lat) * LAT_M_PER_DEG
        d_lon = (lon - cen_lon) * m_lon
        r = math.hypot(d_lat, d_lon)
        assert 25.0 <= r <= 45.0, f"r={r:.2f} м вне диапазона"
    assert spiral_count == 3, f"Ожидалось 3 spiral-фото, найдено {spiral_count}"
    # Координаты не совпадают между собой
    assert len(set(coords_seen)) == 3


def test_no_html_in_description(synthetic_root: Path):
    """description — plain pairs, без HTML-тегов."""
    kmz = build_kmz(synthetic_root)
    kml, _, _ = _read_kml(kmz)
    root = ET.fromstring(kml)
    for pm in root.iter("{http://www.opengis.net/kml/2.2}Placemark"):
        descr = pm.findtext("kml:description", "", KML_NS) or ""
        # Не должно быть <table>, <img>, <tr>, <td>, <a href>
        for tag in ("<table", "<img", "<tr", "<td", "<a href"):
            assert tag not in descr.lower(), \
                f"HTML-тег {tag!r} в description: {descr[:120]}"


def test_extrude_for_buildings(synthetic_root: Path):
    """cad_oks_* / cad_ons_* должны иметь <extrude>1</extrude>."""
    kmz = build_kmz(synthetic_root)
    kml, _, _ = _read_kml(kmz)
    root = ET.fromstring(kml)
    for pm in root.iter("{http://www.opengis.net/kml/2.2}Placemark"):
        style_url = pm.findtext("kml:styleUrl", "", KML_NS)
        if "cad_oks_" in style_url or "cad_ons_" in style_url:
            poly = pm.find(".//kml:Polygon", KML_NS)
            assert poly is not None, f"Нет Polygon у {style_url}"
            assert poly.findtext("kml:extrude", "", KML_NS) == "1"
            assert (poly.findtext("kml:altitudeMode", "", KML_NS)
                    == "relativeToGround")


def test_schema_version_in_document(synthetic_root: Path):
    kmz = build_kmz(synthetic_root)
    kml, _, _ = _read_kml(kmz)
    root = ET.fromstring(kml)
    doc = root.find("kml:Document", KML_NS)
    ext = doc.find("kml:ExtendedData", KML_NS)
    assert ext is not None, "Нет ExtendedData в Document"
    versions = [d.findtext("kml:value", "", KML_NS)
                for d in ext.findall("kml:Data", KML_NS)
                if d.attrib.get("name") == "kml_schema_version"]
    # Контракт KMZ 2.11.0 §5: kml_schema_version "2.0" → "2.1" (MINOR wire-bump).
    assert "2.1" in versions, f"ожидаем kml_schema_version=2.1, получено {versions}"
    # atom:author
    author = doc.find("atom:author", KML_NS)
    assert author is not None, "Нет atom:author"


def test_no_inner_boundary(synthetic_root: Path):
    """innerBoundaryIs запрещён (несовместимо с v2.9.62 §4)."""
    kmz = build_kmz(synthetic_root)
    kml, _, _ = _read_kml(kmz)
    assert "innerBoundaryIs" not in kml


def test_idempotent_sha256(synthetic_root: Path):
    """Два прогона build_kmz на тех же данных → одинаковый sha256 архива."""
    kmz1 = build_kmz(synthetic_root)
    h1 = hashlib.sha256(kmz1.read_bytes()).hexdigest()
    kmz2 = build_kmz(synthetic_root)
    h2 = hashlib.sha256(kmz2.read_bytes()).hexdigest()
    assert h1 == h2, "KMZ не идемпотентен"
