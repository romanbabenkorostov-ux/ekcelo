"""tests/test_xml_basis_restricting.py — основание права, ограничиваемые права, личное участие.

Без этих сведений не составить проект договора по лоту (abn ADR-025):
- основание права решает, нужно ли согласие супруга (дарение, наследство,
  приватизация — личное имущество);
- `restricting_rights` у аренды называет арендодателей, у запрещения — чью
  долю оно держит;
- заявление о регистрации только при личном участии значит, что
  представитель сделку не зарегистрирует.
Колонки `basis`, `restricting_right_number`, `personal_participation_req` в
схеме уже были — заполнялись не из xml.
"""
from __future__ import annotations

import sqlite3
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from egrn_parser.merge.upsert import upsert_right                       # noqa: E402
from egrn_parser.parsers.xml_parser import (_parse_xml_restrict_record,  # noqa: E402
                                            _parse_xml_right_record)

RIGHT = """<right_record>
  <record_info><registration_date>2023-06-29T10:00:00+03:00</registration_date></record_info>
  <right_data>
    <right_type><code>001002000000</code><value>Общая долевая собственность</value></right_type>
    <right_number>26:29:130106:71-26/105/2023-8</right_number>
    <shares><share><numerator>1</numerator><denominator>2</denominator></share></shares>
  </right_data>
  <underlying_documents><underlying_document>
    <document_code><code>558401010101</code><value>Договор купли-продажи</value></document_code>
    <document_name>Договор дарения доли</document_name>
    <document_date>2023-06-01</document_date>
  </underlying_document></underlying_documents>
  <personal_participations><personal_participation><inability_info>
    <origin_content>заявление</origin_content></inability_info></personal_participation>
  </personal_participations>
</right_record>"""

LEASE = """<restrict_record>
  <record_info><registration_date>2023-11-15</registration_date></record_info>
  <restrictions_encumbrances_data>
    <restriction_encumbrance_number>26:29:130106:71-26/474/2023-10</restriction_encumbrance_number>
    <restriction_encumbrance_type><code>022006000000</code><value>Аренда</value></restriction_encumbrance_type>
    <restricting_rights>
      <restricting_right><number>26:29:130106:71-26/105/2023-9</number>
        <right_number>26:29:130106:71-26/105/2023-9</right_number></restricting_right>
      <restricting_right><number>26:29:130106:71-26/105/2023-8</number>
        <right_number>26:29:130106:71-26/105/2023-8</right_number></restricting_right>
    </restricting_rights>
  </restrictions_encumbrances_data>
  <right_holders><right_holder><legal_entity><entity><resident>
    <name>ООО «Арендатор»</name><inn>2618801913</inn></resident></entity></legal_entity>
  </right_holder></right_holders>
</restrict_record>"""


def test_right_record_takes_basis_and_personal_participation():
    rec = _parse_xml_right_record(ET.fromstring(RIGHT), "26:29:130106:71", "land",
                                  "КУВИ-1", "right")
    assert "Договор дарения доли" in rec["basis"]
    assert rec["personal_participation_req"] == 1


def test_restrict_record_names_restricted_rights():
    rec = _parse_xml_restrict_record(ET.fromstring(LEASE), "26:29:130106:71", "land",
                                     "КУВИ-1")
    assert rec["restricting_right_number"] == ("26:29:130106:71-26/105/2023-9; "
                                               "26:29:130106:71-26/105/2023-8")


def test_upsert_writes_restricting_right_number():
    schema = (Path(__file__).parent.parent / "egrn_parser" / "db" / "schema.sql").read_text(
        encoding="utf-8")
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.executescript(schema)
    rec = _parse_xml_restrict_record(ET.fromstring(LEASE), "26:29:130106:71", "land",
                                     "КУВИ-1")
    right_id = upsert_right(conn, rec)
    row = conn.execute("SELECT restricting_right_number FROM rights WHERE right_id = ?",
                       (right_id,)).fetchone()
    assert row["restricting_right_number"].endswith("2023-8")
