"""
tests/test_egrul_egrip_parser.py — парсер выписок ФНС ЕГРЮЛ/ЕГРИП.

Проверяет автоопределение формата (ВерсФорм/ТипИнф), версионный реестр XSD
и извлечение субъекта + корпоративных связей из windows-1251 XML.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from egrn_parser.parsers import egrul_egrip_parser as P  # noqa: E402

FIX = Path(__file__).parent / "fixtures" / "fns"


# ── Автоопределение формата ──────────────────────────────────────────────────
def test_detect_egrul():
    fmt = P.detect_format(FIX / "egrul_408_min.xml")
    assert fmt is not None
    assert (fmt.registry, fmt.version, fmt.info_type) == (
        "ЕГРЮЛ", "4.08", "ЕГРЮЛ_ОТКР_СВЕД")
    assert fmt.supported


def test_detect_egrip():
    fmt = P.detect_format(FIX / "egrip_407_min.xml")
    assert fmt is not None
    assert (fmt.registry, fmt.version) == ("ЕГРИП", "4.07")
    assert fmt.supported


def test_detect_rejects_non_fns():
    assert P.detect_format(FIX / "not_fns.xml") is None
    assert not P.is_fns_reestr_xml(FIX / "not_fns.xml")


def test_unsupported_version_raises(tmp_path):
    bad = tmp_path / "bad.xml"
    bad.write_bytes(
        '<?xml version="1.0" encoding="windows-1251"?>'
        '<Файл ИдФайл="x" ВерсФорм="9.99" ТипИнф="ЕГРЮЛ_ОТКР_СВЕД" КолДок="0"/>'
        .encode("cp1251")
    )
    fmt = P.detect_format(bad)
    assert fmt is not None and not fmt.supported
    with pytest.raises(ValueError, match="не поддержан"):
        P.parse(bad)


# ── Версионный реестр XSD ────────────────────────────────────────────────────
def test_find_xsd_per_registry():
    egrul = P.find_xsd("ЕГРЮЛ", "4.08")
    egrip = P.find_xsd("ЕГРИП", "4.07")
    assert egrul is not None and egrul.suffix == ".xsd" and "egrul" in str(egrul)
    assert egrip is not None and "egrip" in str(egrip)


# ── ЕГРЮЛ: субъект + связи ───────────────────────────────────────────────────
def test_parse_egrul_subject_and_relations():
    out = P.parse(FIX / "egrul_408_min.xml")
    assert out["format"]["registry"] == "ЕГРЮЛ"
    assert len(out["records"]) == 1
    rec = out["records"][0]

    subj = rec["subject"]
    assert subj["kind"] == "org"
    assert subj["ogrn"] == "1027700132195"
    assert subj["inn"] == "7707083893"
    assert subj["kpp"] == "770701001"
    assert "ПРИМЕР" in subj["name_full"]
    assert subj["name_short"] == "ООО ПРИМЕР"
    assert subj["status"]["name"] == "Действующее"
    assert subj["okved_main"]["code"] == "62.01"

    # руководитель (физлицо)
    assert len(rec["directors"]) == 1
    d = rec["directors"][0]
    assert d["fio"] == {"last": "Иванов", "first": "Иван", "middle": "Иванович"}
    assert d["post"] == "ГЕНЕРАЛЬНЫЙ ДИРЕКТОР"
    assert d["inn"] == "770700000000"

    # управляющая организация
    assert rec["managing_orgs"][0]["inn"] == "7705000000"

    # учредители: юрлицо + физлицо с долями
    kinds = {f["kind"] for f in rec["founders"]}
    assert kinds == {"legal_ru", "person"}
    legal = next(f for f in rec["founders"] if f["kind"] == "legal_ru")
    assert legal["ogrn"] == "1037700000000"
    assert legal["share_percent"] == 100
    assert legal["share_nominal"] == 10000
    person = next(f for f in rec["founders"] if f["kind"] == "person")
    assert person["fio"]["last"] == "Петров"
    assert person["share_percent"] == 50

    # реорганизация
    assert rec["predecessors"][0]["ogrn"] == "1020000000001"
    assert rec["successors"][0]["name"] == "ООО НОВОЕ"

    # источник
    assert rec["source"]["system"] == "ФНС-ЕГРЮЛ-XML"
    assert rec["source"]["version"] == "4.08"


# ── ЕГРИП: субъект-физлицо ───────────────────────────────────────────────────
def test_parse_egrip_subject():
    out = P.parse(FIX / "egrip_407_min.xml")
    rec = out["records"][0]
    subj = rec["subject"]
    assert subj["kind"] == "person"
    assert subj["ogrnip"] == "304770000000001"
    assert subj["inn"] == "770700000001"
    assert subj["fio"] == {"last": "Сидоров", "first": "Сидор", "middle": "Сидорович"}
    assert subj["ip_kind"] == "Индивидуальный предприниматель"
    assert subj["status"]["name"] == "Действующий"
    assert subj["okved_main"]["code"] == "47.11"
    # для ИП корпоративных связей нет
    assert rec["directors"] == [] and rec["founders"] == []


# ── XSD-валидация (lxml) ─────────────────────────────────────────────────────
def test_validate_runs_against_real_xsd():
    """validate() не падает и возвращает список (фикстура минимальна → могут
    быть ошибки полноты, но вызов по реальной XSD ФНС должен отработать)."""
    errs = P.validate(FIX / "egrul_408_min.xml")
    assert isinstance(errs, list)


def test_validate_rejects_non_fns():
    errs = P.validate(FIX / "not_fns.xml")
    assert errs and "выписк" in errs[0].lower()
