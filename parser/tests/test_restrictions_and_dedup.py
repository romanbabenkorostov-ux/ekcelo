"""Замки: единый классификатор ограничений (PDF=XML) и дедуп PDF/XML по отчёту."""
from pathlib import Path

from egrn_parser.parsers.restrictions_common import classify_restriction_type
from egrn_parser.cli import _dedup_pdf_xml, _report_key


def test_classify_okn():
    assert classify_restriction_type("Территория объекта культурного наследия") == "okn_territory"
    assert classify_restriction_type(None, "памятник архитектуры") == "okn_territory"


def test_classify_zouit_default():
    assert classify_restriction_type("Охранная зона ЛЭП") == "czuit_zone"
    assert classify_restriction_type(None, None) == "czuit_zone"


def test_report_key_pairs_pdf_and_xml():
    pdf = Path("report-31053789-OfSite-61-01[0] ЭП.pdf")
    xml = Path("report-31053789-OfSite-61-01[0].xml")
    assert _report_key(pdf) == _report_key(xml)


def test_dedup_prefers_xml():
    pdf = Path("report-A-61-01[0] ЭП.pdf")
    xml = Path("report-A-61-01[0].xml")
    lone = Path("Выписка 9302.pdf")
    other = Path("ОСВ.xlsx")
    kept, dropped = _dedup_pdf_xml([pdf, xml, lone, other])
    assert xml in kept and pdf in dropped
    assert lone in kept and other in kept
    assert dropped == [pdf]
