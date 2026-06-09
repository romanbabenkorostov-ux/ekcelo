"""
tests/test_egrul_egrip_sources.py — PDF-адаптер, checko/dadata JSON-адаптеры
и merge нормализованных записей (мультиисточник ЕГРЮЛ/ЕГРИП).

Все источники должны давать запись ОДНОЙ формы
`{subject, directors, managing_orgs, founders, predecessors, successors, source}`.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from egrn_parser.parsers import egrul_egrip_pdf as PDF          # noqa: E402
from egrn_parser.parsers import egrul_egrip_sources as SRC      # noqa: E402
from egrn_parser.parsers import egrul_egrip_normalized as NORM  # noqa: E402

FIX = Path(__file__).parent / "fixtures" / "fns"


# ── PDF-адаптер (parse_text на текстовых фикстурах) ──────────────────────────
def test_pdf_egrul_subject_and_relations():
    text = (FIX / "egrul_pdf_min.txt").read_text(encoding="utf-8")
    assert PDF.detect_registry(text) == "ЕГРЮЛ"
    rec = PDF.parse_text(text, file="egrul_pdf_min.txt")["records"][0]
    s = rec["subject"]
    assert s["ogrn"] == "1027700132195"
    assert s["inn"] == "7707083893"          # из шапки, не директора
    assert s["kpp"] == "770701001"
    assert "ПРИМЕР" in s["name_full"] and "ОТВЕТСТВЕННОСТЬЮ" in s["name_full"]
    assert s["name_short"] == 'ООО "ПРИМЕР"'
    assert s["okved_main"]["code"] == "62.01"
    assert "программного обеспечения" in s["okved_main"]["name"]
    # руководитель-физлицо
    assert rec["directors"][0]["fio"] == {"last": "ПЕТРОВ", "first": "ПЕТР", "middle": "ПЕТРОВИЧ"}
    assert rec["directors"][0]["post"] == "ГЕНЕРАЛЬНЫЙ ДИРЕКТОР"
    # учредитель-юрлицо с долей
    f = rec["founders"][0]
    assert f["ogrn"] == "1037700000000" and f["share_percent"] == 100.0
    assert rec["source"]["system"] == "ФНС-ЕГРЮЛ-PDF"


def test_pdf_egrip_subject():
    text = (FIX / "egrip_pdf_min.txt").read_text(encoding="utf-8")
    rec = PDF.parse_text(text)["records"][0]
    s = rec["subject"]
    assert s["kind"] == "person"
    assert s["ogrnip"] == "304770000000001"
    assert s["inn"] == "770700000001"
    assert s["fio"] == {"last": "СИДОРОВ", "first": "СИДОР", "middle": "СИДОРОВИЧ"}
    assert s["okved_main"]["code"] == "47.11"


def test_pdf_ao_foreign_shareholder():
    text = (FIX / "egrul_pdf_ao_shareholder.txt").read_text(encoding="utf-8")
    rec = PDF.parse_text(text)["records"][0]
    assert rec["subject"]["inn"] == "7710000001"   # из шапки, не акционера
    f = rec["founders"][0]
    assert f["kind"] == "legal_foreign"
    assert f["inn"] == "9909000251"
    assert f["name"] == "ЮНИКРЕДИТ С.П.А."
    assert f["country"] == "Итальянская Республика"
    assert f["foreign_reg"] == "00348170101"


def test_pdf_plumber_inline_layout():
    """pdfplumber кладёт «NN Метка Значение» в одну строку — парсер должен
    извлекать поля и связи так же, как из PyMuPDF-раскладки."""
    text = (FIX / "egrul_pdf_plumber_layout.txt").read_text(encoding="utf-8")
    rec = PDF.parse_text(text)["records"][0]
    s = rec["subject"]
    assert s["inn"] == "7710000001"      # из «ИНН юридического лица», не акционера
    assert s["kpp"] == "770101001"
    assert s["name_short"] == "АО ПРИМЕР-БАНК"
    assert s["okved_main"]["code"] == "64.19"
    d = rec["directors"][0]
    assert d["fio"] == {"last": "ИВАНОВ", "first": "ИВАН", "middle": "ИВАНОВИЧ"}
    assert d["inn"] == "771100000000" and d["post"] == "ПРЕДСЕДАТЕЛЬ ПРАВЛЕНИЯ"
    f = rec["founders"][0]
    assert f["kind"] == "legal_foreign" and f["inn"] == "9909000251"
    assert f["name"] == "ЗАРУБЕЖ ХОЛДИНГ С.П.А."
    assert f["country"] == "Итальянская Республика"


def test_pdf_rejects_foreign_text():
    with pytest.raises(ValueError, match="не опознан"):
        PDF.parse_text("просто какой-то текст без выписки")


# ── checko JSON-адаптер ──────────────────────────────────────────────────────
def test_from_checko_json():
    raw = json.loads((FIX / "checko_min.json").read_text(encoding="utf-8"))
    rec = SRC.from_checko_json(raw)["records"][0]
    assert rec["registry"] == "ЕГРЮЛ"
    assert rec["subject"]["inn"] == "7707083893"
    assert rec["subject"]["name_short"] == 'ООО "ПРИМЕР"'
    assert rec["directors"][0]["fio"]["last"] == "ПЕТРОВ"
    assert rec["directors"][0]["post"] == "ГЕНЕРАЛЬНЫЙ ДИРЕКТОР"
    legal = next(f for f in rec["founders"] if f["kind"] == "legal")
    assert legal["ogrn"] == "1037700000000" and legal["share_percent"] == 100
    assert rec["source"]["system"] == "checko"


# ── dadata JSON-адаптер ──────────────────────────────────────────────────────
def test_from_dadata_json():
    raw = json.loads((FIX / "dadata_min.json").read_text(encoding="utf-8"))
    rec = SRC.from_dadata_json(raw)["records"][0]
    assert rec["subject"]["inn"] == "7707083893"
    assert rec["subject"]["name_full"].startswith("ОБЩЕСТВО")
    assert rec["directors"][0]["post"] == "ГЕНЕРАЛЬНЫЙ ДИРЕКТОР"
    assert rec["founders"][0]["ogrn"] == "1037700000000"
    assert rec["source"]["system"] == "dadata"


# ── Единая форма + merge по приоритету источника ─────────────────────────────
def test_all_sources_same_shape_and_inn():
    pdf = PDF.parse_text((FIX / "egrul_pdf_min.txt").read_text(encoding="utf-8"))["records"][0]
    chk = SRC.from_checko_json(json.loads((FIX / "checko_min.json").read_text(encoding="utf-8")))["records"][0]
    dad = SRC.from_dadata_json(json.loads((FIX / "dadata_min.json").read_text(encoding="utf-8")))["records"][0]
    keys = {"registry", "subject", "directors", "managing_orgs", "founders",
            "predecessors", "successors", "source"}
    for rec in (pdf, chk, dad):
        assert set(rec) == keys
        assert rec["subject"]["inn"] == "7707083893"


def test_merge_prefers_official_source():
    pdf = PDF.parse_text((FIX / "egrul_pdf_min.txt").read_text(encoding="utf-8"))["records"][0]
    chk = SRC.from_checko_json(json.loads((FIX / "checko_min.json").read_text(encoding="utf-8")))["records"][0]
    merged = NORM.merge_records([chk, pdf])  # PDF приоритетнее checko
    assert merged["subject"]["inn"] == "7707083893"
    assert merged["source"]["merged_from"][0] == "ФНС-ЕГРЮЛ-PDF"


# ── Клиент без ключа: в сеть не ходим ────────────────────────────────────────
def test_fetch_by_inn_without_key_raises(monkeypatch):
    monkeypatch.delenv("CHECKO_API_KEY", raising=False)
    monkeypatch.setattr(SRC, "load_env", lambda *a, **k: {})
    with pytest.raises(RuntimeError, match="CHECKO_API_KEY"):
        SRC.fetch_by_inn("7707083893", vendor="checko")
