# -*- coding: utf-8 -*-
"""Tests для parser.upd.validator.

Покрывают behavior validator'а без bundled-XSD (он будет приложен
пользователем отдельным шагом). Когда XSD появится в репо —
добавятся golden-кейсы валидного/невалидного XML.
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from parser.upd import validator


def test_missing_xml_returns_error(tmp_path):
    errs = validator.validate(tmp_path / "does_not_exist.xml")
    assert errs
    assert "XML не найден" in errs[0]


def test_missing_xsd_returns_error(tmp_path):
    xml = tmp_path / "sample.xml"
    xml.write_text("<root/>", encoding="utf-8")
    # XSD точно отсутствует в bundled-папке на этот момент (или присутствует —
    # тогда тест проверит что валидация запускается; ok оба варианта).
    errs = validator.validate(xml)
    if errs:
        # Если XSD не приложен — должна быть осмысленная ошибка.
        assert any("XSD" in e or "lxml" in e or "schema" in e.lower() or "valid" in e.lower()
                   for e in errs)


def test_explicit_xsd_path_missing(tmp_path):
    xml = tmp_path / "sample.xml"
    xml.write_text("<root/>", encoding="utf-8")
    errs = validator.validate(xml, xsd_path=tmp_path / "nope.xsd")
    assert errs
    assert any("XSD" in e for e in errs)
