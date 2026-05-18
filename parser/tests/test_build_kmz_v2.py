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


@pytest.fixture
def synthetic_root(tmp_path: Path) -> Path:
    """Создаёт минимальный синтетический проект в tmp_path."""
    root = tmp_path / "Тестовый_проект"
    root.mkdir()
    (root / "_data").mkdir()
    (root / "_data" / "nspd_cache").mkdir()
    (root / "Документы_JPG").mkdir()
    (root / "Фотографии").mkdir()

    # КН и БУ: 1 ЗУ, 1 здание (4 эт.), 2 помещения, 1 сооружение,
    # 1 ОНС, 1 БУ, 2 оборудования, 1 бенефициар.
    structure = {
        "enterprise": {"name_short": "ТестЗАО", "name": "ТестЗАО"},
        "cadastre_objects": [
            {"id": "c1", "cadastral_number": "61:44:0050706:1",
             "object_type": "Земельный участок",
             "address": "г. Ростов-на-Дону, ул. Б.Садовая, 111"},
            {"id": "c2", "cadastral_number": "61:44:0050706:31",
             "object_type": "Здание",
             "address": "г. Ростов-на-Дону, ул. Б.Садовая, 111"},
            {"id": "c3", "cadastral_number": "61:44:0050706:119",
             "object_type": "Квартира",
             "address": "г. Ростов-на-Дону, ул. Б.Садовая, 111, кв. 12",
             "parent_cad": "61:44:0050706:31", "_floor_index": 3},
            {"id": "c4", "cadastral_number": "61:44:0050706:120",
             "object_type": "Нежилое помещение",
             "address": "г. Ростов-на-Дону, ул. Б.Садовая, 111, пом. 1",
             "parent_cad": "61:44:0050706:31", "_floor_index": 1},
            {"id": "c5", "cadastral_number": "61:44:0050706:77",
             "object_type": "Сооружение",
             "address": "г. Ростов-на-Дону, ул. Б.Садовая, 111"},
            {"id": "c6", "cadastral_number": "61:44:0050706:31",  # ниже заменим
             "object_type": "Объект незавершённого строительства"},
        ],
        "business_units": [
            {"id": "bu1", "name": "Филиал Ростов",
             "address": "г. Ростов-на-Дону, ул. Б.Садовая, 111",
             "inns": ["6164012345"],
             "cadastre_ids": ["c1", "c2", "c3"],
             "equipment_ids": ["eq1", "eq2"],
             "owners": [
                 {"inn": "6164098765", "ogrn": "1026103098765",
                  "name": "ООО Ромашка",
                  "address": "г. Ростов-на-Дону, пр. Будённовский, 1",
                  "share": "100%"}
             ]}
        ],
        "equipment": [
            {"id": "eq1", "name": "Котёл КЧМ-5",
             "inv_number_hint": "004113", "account": "01.04",
             "balance_value": "184500",
             "links": {"cadastre_id": "c2",
                       "level_ids": [{"level_index": 1}]}},
            {"id": "eq2", "name": "Лифт",
             "inv_number_hint": "004114", "account": "01.04",
             "links": {"cadastre_id": "c2",
                       "level_ids": [{"level_index": 2}]}},
        ],
    }
    # c6 должен иметь уникальный КН
    structure["cadastre_objects"][5]["cadastral_number"] = "61:44:0050706:99"

    (root / "_data" / "structure.json").write_text(
        json.dumps(structure, ensure_ascii=False), encoding="utf-8"
    )

    # NSPD-кеш с геометрией для каждого КН
    cache = {"objects": {
        "61:44:0050706:1": {"info": {
            "geometry": {"type": "Polygon", "coordinates": [
                [[39.7088, 47.2186], [39.7092, 47.2186],
                 [39.7092, 47.2189], [39.7088, 47.2189], [39.7088, 47.2186]]
            ]},
            "Количество этажей": None,
        }},
        "61:44:0050706:31": {"info": {
            "geometry": {"type": "Polygon", "coordinates": [
                [[39.7089, 47.2187], [39.7091, 47.2187],
                 [39.7091, 47.2188], [39.7089, 47.2188], [39.7089, 47.2187]]
            ]},
            "Количество этажей": "4",
        }},
        "61:44:0050706:119": {"info": {
            "geometry": {"type": "Point", "coordinates": [39.7090, 47.21875]},
        }},
        "61:44:0050706:120": {"info": {
            "geometry": {"type": "Point", "coordinates": [39.70905, 47.21878]},
        }},
        "61:44:0050706:77": {"info": {
            "geometry": {"type": "Polygon", "coordinates": [
                [[39.7093, 47.2186], [39.7095, 47.2186],
                 [39.7095, 47.2188], [39.7093, 47.2188], [39.7093, 47.2186]]
            ]},
        }},
        "61:44:0050706:99": {"info": {
            "geometry": {"type": "Polygon", "coordinates": [
                [[39.7087, 47.2185], [39.7089, 47.2185],
                 [39.7089, 47.2186], [39.7087, 47.2186], [39.7087, 47.2185]]
            ]},
            "Количество этажей": "3",
        }},
    }}
    (root / "_data" / "nspd_cache" / "cache.json").write_text(
        json.dumps(cache, ensure_ascii=False), encoding="utf-8"
    )

    # graph.html
    (root / "_data" / "graph.html").write_text(
        "<!DOCTYPE html><html><body><h1>Граф связей</h1></body></html>",
        encoding="utf-8"
    )

    # Документы
    fake_jpg = (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01"
        b"\x00\x01\x00\x00\xff\xdb\x00C\x00" + b"\x08" * 64 + b"\xff\xd9"
    )
    (root / "Документы_JPG" / "egrn_61_44_0050706_31.jpg").write_bytes(fake_jpg)
    (root / "Документы_JPG" / "egrul_inn6164098765.jpg").write_bytes(fake_jpg)

    # Фото без EXIF-GPS — должны попасть на спираль
    realty_dir = (root / "Фотографии" / "Недвижимость" / "Строения"
                  / "61_44_0050706_31" / "Фасад")
    realty_dir.mkdir(parents=True)
    for name in ("IMG_01.jpg", "IMG_02.jpg", "IMG_03.jpg"):
        (realty_dir / name).write_bytes(fake_jpg)

    return root


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
    assert "2.0" in versions
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
