"""
tests/test_basic.py — базовые тесты egrn_parser v1.10.

Покрывает чек-лист ТЗ раздел 17.
"""

import hashlib
import json
import sys
import tempfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))


# ─────────────────────────────────────────────────────────────────────────────
#  Тесты _common.py
# ─────────────────────────────────────────────────────────────────────────────

def test_parse_date_ru():
    from egrn_parser.parsers._common import parse_date_ru
    assert parse_date_ru("24.05.2021") == "2021-05-24"
    assert parse_date_ru("01.01.2026г.") == "2026-01-01"
    assert parse_date_ru("нет даты") is None


def test_parse_datetime_ru():
    from egrn_parser.parsers._common import parse_datetime_ru
    result = parse_datetime_ru("24.05.2021 12:26:19")
    assert result == "2021-05-24 12:26:19"  # Fix 40d: пробел вместо T


def test_normalize_cad_number():
    from egrn_parser.parsers._common import normalize_cad_number
    assert normalize_cad_number("61:44:0040713:370") == "61:44:0040713:370"
    assert normalize_cad_number("кадастровый номер: 61:44:0040713:370 ") == "61:44:0040713:370"
    assert normalize_cad_number("нет номера") is None


def test_parse_share():
    from egrn_parser.parsers._common import parse_share
    num, den = parse_share("47/100")
    assert num == 47 and den == 100
    num2, den2 = parse_share("нет доли")
    assert num2 is None and den2 is None


def test_parse_number():
    from egrn_parser.parsers._common import parse_number
    assert parse_number("1 234 567,89") == pytest.approx(1234567.89)
    assert parse_number("332.7") == pytest.approx(332.7)
    assert parse_number("") is None


def test_cad_quarter():
    from egrn_parser.parsers._common import cad_quarter
    assert cad_quarter("61:44:0040713:370") == "61:44:0040713"


def test_classify_holder_type():
    from egrn_parser.parsers._common import classify_holder_type
    assert classify_holder_type("ООО «Антарес»", "2312122992") == "legal_entity"
    assert classify_holder_type("Российская Федерация", None) == "public"
    assert classify_holder_type("", "123456789012") == "individual"  # 12 цифр


def test_parse_term_formats():
    from egrn_parser.parsers._common import parse_term
    # Формат 1: с ... по ...
    t = parse_term("с 01.01.2020 по 31.12.2025")
    assert t["valid_from"] == "2020-01-01"
    assert t["valid_until"] == "2025-12-31"

    # Формат 2: сроком на N лет
    t2 = parse_term("с 01.01.2020 сроком на 5 лет")
    assert t2["valid_from"] == "2020-01-01"
    assert t2["valid_duration_years"] == 5

    # Бессрочно
    t3 = parse_term("бессрочно")
    assert t3["lease_term_description"] == "бессрочно"


def test_is_absent():
    from egrn_parser.parsers._common import is_absent
    assert is_absent("данные отсутствуют")
    assert is_absent("")
    assert is_absent(None)
    assert not is_absent("61:44:0040713:370")


# ─────────────────────────────────────────────────────────────────────────────
#  Тесты personal_data_filter.py
# ─────────────────────────────────────────────────────────────────────────────

def test_filter_personal_data_removes_field():
    from egrn_parser.utils.personal_data_filter import filter_personal_data
    data = {
        "name": "ООО «Тест»",
        "Сведения о возможности предоставления третьим лицам персональных данных": "Да",
    }
    filtered = filter_personal_data(data)
    assert "name" in filtered
    assert "Сведения о возможности предоставления третьим лицам персональных данных" not in filtered


def test_filter_personal_data_nested():
    from egrn_parser.utils.personal_data_filter import filter_personal_data
    data = {
        "holders": [
            {
                "name": "Иванов",
                "Сведения о возможности предоставления третьим лицам персональных данных": "Нет",
            }
        ]
    }
    # list не обрабатывается рекурсивно в текущей реализации — это известное ограничение
    # для dict внутри dict:
    data2 = {
        "holder": {
            "name": "Иванов",
            "Сведения о возможности предоставления третьим лицам персональных данных": "Нет",
        }
    }
    filtered = filter_personal_data(data2)
    assert "Сведения о возможности предоставления третьим лицам персональных данных" not in filtered["holder"]


def test_assert_no_personal_data_raises():
    from egrn_parser.utils.personal_data_filter import assert_no_personal_data
    with pytest.raises(AssertionError):
        assert_no_personal_data(
            "Сведения о возможности предоставления третьим лицам персональных данных: Да"
        )


def test_assert_no_personal_data_passes():
    from egrn_parser.utils.personal_data_filter import assert_no_personal_data
    assert_no_personal_data({"cad_number": "61:44:0040713:370", "area": 100.5})


# ─────────────────────────────────────────────────────────────────────────────
#  Тесты filename_filter.py
# ─────────────────────────────────────────────────────────────────────────────

def test_is_photo_report_by_name():
    from egrn_parser.utils.filename_filter import is_photo_report_by_name
    assert is_photo_report_by_name("Суворова-фотоотчёт.docx")
    assert is_photo_report_by_name("ОБЪЕКТ-фотоотчет.docx")
    assert not is_photo_report_by_name("Суворова-выписка.pdf")
    assert not is_photo_report_by_name("ОСВ_2025.xlsx")


# ─────────────────────────────────────────────────────────────────────────────
#  Тесты osv_parser.py
# ─────────────────────────────────────────────────────────────────────────────

def test_parse_osv_period():
    from egrn_parser.parsers.osv_parser import parse_osv_period
    assert parse_osv_period("за 1 квартал 2026 г") == ("2026-01-01", "2026-03-31")
    assert parse_osv_period("за 2026 г") == ("2026-01-01", "2026-12-31")
    assert parse_osv_period("за 9 месяцев 2025 г") == ("2025-01-01", "2025-09-30")
    assert parse_osv_period("за 1 полугодие 2024 г") == ("2024-01-01", "2024-06-30")


def test_extract_cad_from_name():
    from egrn_parser.parsers.osv_parser import extract_cad_from_name
    cad, frag = extract_cad_from_name("Бар «Романов» 90:25:020102:698")
    assert cad == "90:25:020102:698"
    assert frag is None

    cad2, frag2 = extract_cad_from_name("Земельный участок :119 дог от 13.01.2016 г")
    assert cad2 is None
    assert frag2 == ":119"


def test_extract_inventory_number():
    from egrn_parser.parsers.osv_parser import extract_inventory_number
    assert extract_inventory_number("Волейбольная площадка Инв. №12345") == "12345"
    assert extract_inventory_number("Арка (00543)") == "00543"
    assert extract_inventory_number("Забор") is None


# ─────────────────────────────────────────────────────────────────────────────
#  Тесты БД
# ─────────────────────────────────────────────────────────────────────────────

def test_init_db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        from egrn_parser.db.connection import init_db, check_db
        init_db(db_path)
        assert db_path.exists()
        assert check_db(db_path)


def test_init_db_tables():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        from egrn_parser.db.connection import init_db, get_connection
        init_db(db_path)
        with get_connection(db_path, readonly=True) as conn:
            tables = [r[0] for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()]
        expected = [
            "land_objects", "building_objects", "accessories", "business_units",
            "rights", "right_holders", "entity_registry", "company_groups",
            "extracts", "valuations", "object_events", "right_events",
            "system_meta", "code_dictionary",
        ]
        for t in expected:
            assert t in tables, f"Таблица '{t}' не найдена"


def test_load_dictionaries():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        from egrn_parser.db.connection import init_db, get_connection
        from egrn_parser.db.seeds import load_dictionaries
        init_db(db_path)
        n = load_dictionaries(db_path)
        assert n > 0
        with get_connection(db_path, readonly=True) as conn:
            cnt = conn.execute("SELECT COUNT(*) FROM code_dictionary").fetchone()[0]
        assert cnt > 0


def test_upsert_land_object():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        from egrn_parser.db.connection import init_db, get_connection
        from egrn_parser.merge.upsert import upsert_land_object
        init_db(db_path)

        obj = {
            "cad_number":       "61:44:0040713:370",
            "quarter_cad_number": "61:44:0040713",
            "area":             1000.5,
            "address":          "г. Ростов-на-Дону",
            "lifecycle_status": "active",
            "content_hash":     "abc123",
        }
        with get_connection(db_path) as conn:
            conn.execute("BEGIN")
            action = upsert_land_object(conn, obj)
            conn.execute("COMMIT")
        assert action == "inserted"

        with get_connection(db_path, readonly=True) as conn:
            row = conn.execute(
                "SELECT * FROM land_objects WHERE cad_number = ?", ("61:44:0040713:370",)
            ).fetchone()
        assert row is not None
        assert row["area"] == pytest.approx(1000.5)


def test_upsert_right():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        from egrn_parser.db.connection import init_db, get_connection
        from egrn_parser.merge.upsert import upsert_right
        init_db(db_path)

        right = {
            "object_class":     "land",
            "object_key_type":  "cad_number",
            "object_key_value": "61:44:0040713:370",
            "right_category":   "right",
            "right_type":       "Общая долевая собственность",
            "right_type_code":  "shared",
            "right_number":     "61:44:0040713:370-61/183/2021-2",
            "right_date":       "2021-05-24T12:26:19",
            "share_numerator":  47,
            "share_denominator":100,
        }
        with get_connection(db_path) as conn:
            conn.execute("BEGIN")
            right_id = upsert_right(conn, right)
            conn.execute("COMMIT")
        assert right_id is not None

        # Повторная вставка — INSERT OR IGNORE
        with get_connection(db_path) as conn:
            conn.execute("BEGIN")
            right_id2 = upsert_right(conn, right)
            conn.execute("COMMIT")
        assert right_id2 == right_id  # тот же ID


# ─────────────────────────────────────────────────────────────────────────────
#  Тест content_hash
# ─────────────────────────────────────────────────────────────────────────────

def test_compute_content_hash_deterministic():
    from egrn_parser.merge.content_hash import compute_content_hash
    extract = {
        "cad_number":          "61:44:0040713:370",
        "area":                1000.5,
        "cadastral_value":     15234567,
        "address":             "г. Ростов-на-Дону",
        "permitted_uses":      None,
        "object_restrictions": [],
        "rights_summary":      [("RN1", "Собственность", None, None)],
    }
    h1 = compute_content_hash(extract)
    h2 = compute_content_hash(extract)
    assert h1 == h2
    assert len(h1) == 64  # SHA-256


# ─────────────────────────────────────────────────────────────────────────────
#  Тест differ
# ─────────────────────────────────────────────────────────────────────────────

def test_diff_objects_detects_changes():
    from egrn_parser.merge.differ import diff_objects
    old = {"area": 1000.5, "cadastral_value": 15000000.0, "address": "Старый адрес"}
    new = {"area": 1002.0, "cadastral_value": 15000000.0, "address": "Новый адрес"}
    changed = diff_objects(old, new, "land")
    assert "area" in changed
    assert "address" in changed
    assert "cadastral_value" not in changed


def test_diff_objects_no_changes():
    from egrn_parser.merge.differ import diff_objects
    obj = {"area": 1000.5, "cadastral_value": 15000000.0}
    changed = diff_objects(obj, obj, "land")
    assert not changed


# ─────────────────────────────────────────────────────────────────────────────
#  Тест dictionaries
# ─────────────────────────────────────────────────────────────────────────────

def test_all_dictionaries_present():
    from egrn_parser import dictionaries as d
    for attr in [
        "RIGHT_TYPES", "RIGHT_CATEGORIES", "ENCUMBRANCE_TYPES", "OBJECT_TYPES",
        "LAND_CATEGORIES", "HOLDER_TYPES", "OBJECT_EVENT_TYPES", "RIGHT_EVENT_TYPES",
        "TRANSFORMATION_TYPES", "VALUATION_TYPES", "OSV_ACCOUNT_RIGHTS",
        "UNIT_TYPES", "UNIT_STATUSES", "HIERARCHY_LEVELS", "OBJECT_RESTRICTION_TYPES",
    ]:
        assert hasattr(d, attr), f"Словарь {attr} не найден в dictionaries.py"
        val = getattr(d, attr)
        assert len(val) > 0, f"Словарь {attr} пуст"


def test_right_type_ru_to_code():
    from egrn_parser.dictionaries import RIGHT_TYPE_RU_TO_CODE
    assert RIGHT_TYPE_RU_TO_CODE["собственность"] == "ownership"
    assert RIGHT_TYPE_RU_TO_CODE["общая долевая собственность"] == "shared"
    assert RIGHT_TYPE_RU_TO_CODE["аренда"] == "lease"


# ─────────────────────────────────────────────────────────────────────────────
#  Тест resolve_room_parent
# ─────────────────────────────────────────────────────────────────────────────

def test_resolve_room_parent():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        from egrn_parser.db.connection import init_db, get_connection
        from egrn_parser.merge.upsert import upsert_building_object
        from egrn_parser.enrichers.room_parent_resolver import resolve_room_parent
        init_db(db_path)

        # Создать здание
        bldg = {
            "cad_number":       "61:44:0040713:200",
            "object_type":      "building",
            "floors_total":     5,
            "floors_above_ground": 4,
            "underground_floors": 1,
            "lifecycle_status": "active",
            "content_hash":     "bldg_hash",
        }
        with get_connection(db_path) as conn:
            conn.execute("BEGIN")
            upsert_building_object(conn, bldg)
            conn.execute("COMMIT")

        # Создать помещение
        room = {
            "cad_number":       "61:44:0040713:201",
            "object_type":      "room",
            "parent_cad_number":"61:44:0040713:200",
            "lifecycle_status": "active",
            "content_hash":     "room_hash",
        }
        with get_connection(db_path) as conn:
            conn.execute("BEGIN")
            upsert_building_object(conn, room)
            conn.execute("COMMIT")

        # Запустить resolve_room_parent
        n = resolve_room_parent(db_path)
        assert n >= 1

        with get_connection(db_path, readonly=True) as conn:
            row = conn.execute(
                "SELECT parent_floors_above_ground, parent_underground_floors "
                "FROM building_objects WHERE cad_number = ?",
                ("61:44:0040713:201",),
            ).fetchone()
        assert row["parent_floors_above_ground"] == 4
        assert row["parent_underground_floors"] == 1


# ─────────────────────────────────────────────────────────────────────────────
#  Тесты ОНС (ТЗ 4.4)
# ─────────────────────────────────────────────────────────────────────────────

def test_ons_pdf_parsing():
    """Реальный PDF 510: ОНС должен парситься как object_type='ons'."""
    from egrn_parser.parsers.pdf_parser import parse_egrn_pdf
    p = Path("/mnt/user-data/uploads/Выписка_ЕГРН_510.pdf")
    if not p.exists():
        pytest.skip("PDF 510 не загружен")
    r = parse_egrn_pdf(p)
    assert r is not None
    assert r["object_type"] == "ons"
    obj = r["object"]
    assert obj["area"] == pytest.approx(105.8)
    assert obj.get("construction_stage") == pytest.approx(80.0)
    assert obj.get("purpose") is not None
    land = obj.get("land_cad_numbers")
    assert land is not None
    assert "90:25:020103:8653" in land  # plain text format (Fix 21)


# ─────────────────────────────────────────────────────────────────────────────
#  Тесты spravka_parser
# ─────────────────────────────────────────────────────────────────────────────

def test_spravka_parser():
    """Реальная Справка: должны быть распарсены аренды ЗУ и статусы ОКС."""
    from egrn_parser.parsers.spravka_parser import parse_spravka_docx, is_spravka_docx
    p = Path("/mnt/user-data/uploads/Справка_ООО_ССР_21_04_2026_.docx")
    if not p.exists():
        pytest.skip("Справка не загружена")
    assert is_spravka_docx(p)
    r = parse_spravka_docx(p, entity_inn="9103015220")
    assert len(r["lease_intentions"]) >= 7
    assert len(r["building_statuses"]) >= 8
    # Проверить конкретные кадастровые номера
    lease_cads = {item["cad_number"] for item in r["lease_intentions"]}
    assert "90:25:020103:9466" in lease_cads
    bldg_cads = {item["cad_number"] for item in r["building_statuses"]}
    assert "90:25:020103:754" in bldg_cads


# ─────────────────────────────────────────────────────────────────────────────
#  Тесты cad_resolver
# ─────────────────────────────────────────────────────────────────────────────

def test_find_cad_candidates():
    """Поиск по хвосту кадастрового номера в БД."""
    import tempfile
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        from egrn_parser.db.connection import init_db, get_connection
        from egrn_parser.merge.upsert import upsert_land_object
        from egrn_parser.merge.cad_resolver import find_cad_candidates
        init_db(db_path)

        obj = {
            "cad_number":       "90:25:020102:119",
            "lifecycle_status": "active",
            "content_hash":     "h1",
            "address":          "Крым, Ялта, Гаспра",
        }
        with get_connection(db_path) as conn:
            conn.execute("BEGIN")
            upsert_land_object(conn, obj)
            conn.execute("COMMIT")

        candidates = find_cad_candidates(db_path, ":119")
        assert len(candidates) == 1
        assert candidates[0]["cad_number"] == "90:25:020102:119"

        # Несуществующий фрагмент
        assert find_cad_candidates(db_path, ":9999") == []
