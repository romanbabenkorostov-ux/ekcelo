"""Общие pytest fixtures для parser-тестов."""
from __future__ import annotations
import json
import sys
from pathlib import Path

import pytest

# Пути для обеих конвенций импорта репозитория, независимо от cwd/способа запуска
# (`pytest` или `python -m pytest`):
#   • parser/        → `egrn_parser.*`, `exporters.*`, `scripts`
#   • корень репо    → `parser.*` (parser/__init__.py делает его пакетом; ETL-тесты)
_PARSER_DIR = Path(__file__).resolve().parents[1]
_REPO_ROOT = Path(__file__).resolve().parents[2]
for _p in (str(_PARSER_DIR / "scripts"), str(_PARSER_DIR), str(_REPO_ROOT)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


@pytest.fixture
def synthetic_root(tmp_path: Path) -> Path:
    """Минимальный синтетический проект — 6 КН, 1 БУ, 2 ОС, 1 бенефициар, 3 фото."""
    root = tmp_path / "Тестовый_проект"
    root.mkdir()
    (root / "_data").mkdir()
    (root / "_data" / "nspd_cache").mkdir()
    (root / "Документы_JPG").mkdir()
    (root / "Фотографии").mkdir()

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
            {"id": "c6", "cadastral_number": "61:44:0050706:99",
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

    (root / "_data" / "structure.json").write_text(
        json.dumps(structure, ensure_ascii=False), encoding="utf-8"
    )

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

    (root / "_data" / "graph.html").write_text(
        "<!DOCTYPE html><html><body><h1>Граф связей</h1></body></html>",
        encoding="utf-8"
    )

    fake_jpg = (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01"
        b"\x00\x01\x00\x00\xff\xdb\x00C\x00" + b"\x08" * 64 + b"\xff\xd9"
    )
    (root / "Документы_JPG" / "egrn_61_44_0050706_31.jpg").write_bytes(fake_jpg)
    (root / "Документы_JPG" / "egrul_inn6164098765.jpg").write_bytes(fake_jpg)

    realty_dir = (root / "Фотографии" / "Недвижимость" / "Строения"
                  / "61_44_0050706_31" / "Фасад")
    realty_dir.mkdir(parents=True)
    for name in ("IMG_01.jpg", "IMG_02.jpg", "IMG_03.jpg"):
        (realty_dir / name).write_bytes(fake_jpg)

    return root
