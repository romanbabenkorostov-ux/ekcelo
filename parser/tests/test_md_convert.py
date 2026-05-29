"""tests/test_md_convert.py — конвертация lot_appendix.md → PDF/DOCX."""
from __future__ import annotations

from pathlib import Path

import pytest

from parser.exporters.etp.md_convert import (
    _md_to_html,
    available_targets,
    convert_appendix,
    soffice_bin,
)


def _conversion_actually_works(tmp_path_factory) -> bool:
    """Runtime-probe: реально ли конвертится в этой среде.

    soffice-бинарь может присутствовать, но не работать (sandbox без $HOME,
    profile lock и т.п.). Пробуем крошечную конвертацию и кешируем результат.
    """
    if _conversion_actually_works._cache is not None:  # type: ignore[attr-defined]
        return _conversion_actually_works._cache  # type: ignore[attr-defined]
    ok = False
    try:
        d = tmp_path_factory.mktemp("probe")
        md = d / "probe.md"
        md.write_text("# probe\n\ntext", encoding="utf-8")
        ok = convert_appendix(md, target="pdf") is not None
    except Exception:
        ok = False
    _conversion_actually_works._cache = ok  # type: ignore[attr-defined]
    return ok


_conversion_actually_works._cache = None  # type: ignore[attr-defined]


@pytest.fixture(scope="session")
def conversion_works(tmp_path_factory) -> bool:
    return _conversion_actually_works(tmp_path_factory)


SAMPLE_MD = """# Приложение к лоту lot:pirushin:001

**Имущественный комплекс «Пирушин-Центр»**

## Параметры процедуры

| Параметр | Значение |
|---|---|
| Тип сделки | sale |
| Целевые ЭТП | torgi.gov.ru, sberbank-ast.ru |

## Состав лота

- 61:44:0050706:31 (room)
- 61:44:0050706:7 (land)

Текст с `кодом` и *курсивом*.
"""


# ─────────────────────────────────────────────────────────────────────────────
#  _md_to_html (без внешних инструментов)
# ─────────────────────────────────────────────────────────────────────────────

def test_md_to_html_headings():
    html = _md_to_html("# H1\n## H2")
    assert "<h1>H1</h1>" in html
    assert "<h2>H2</h2>" in html


def test_md_to_html_table():
    html = _md_to_html("| A | B |\n|---|---|\n| 1 | 2 |")
    assert "<table" in html
    assert "<th>A</th>" in html
    assert "<td>1</td>" in html


def test_md_to_html_list():
    html = _md_to_html("- item1\n- item2")
    assert "<ul>" in html
    assert "<li>item1</li>" in html


def test_md_to_html_inline():
    html = _md_to_html("**bold** and *italic* and `code`")
    assert "<b>bold</b>" in html
    assert "<i>italic</i>" in html
    assert "<code>code</code>" in html


def test_md_to_html_escapes():
    html = _md_to_html("text with <script> & ampersand")
    assert "<script>" not in html  # экранировано
    assert "&lt;script&gt;" in html or "&amp;" in html


def test_md_to_html_full_sample_valid():
    html = _md_to_html(SAMPLE_MD)
    assert "<!doctype html>" in html
    assert "Пирушин-Центр" in html
    assert "<table" in html
    assert "61:44:0050706:31" in html


# ─────────────────────────────────────────────────────────────────────────────
#  available_targets / soffice_bin
# ─────────────────────────────────────────────────────────────────────────────

def test_available_targets_returns_set():
    targets = available_targets()
    assert isinstance(targets, set)
    # На CI/dev с LibreOffice — должно содержать pdf+docx; без — пусто.
    assert targets <= {"pdf", "docx"}


# ─────────────────────────────────────────────────────────────────────────────
#  convert_appendix
# ─────────────────────────────────────────────────────────────────────────────

def test_convert_rejects_bad_target(tmp_path):
    md = tmp_path / "a.md"
    md.write_text(SAMPLE_MD, encoding="utf-8")
    with pytest.raises(ValueError, match="pdf.*docx"):
        convert_appendix(md, target="rtf")


def test_convert_missing_file_raises(tmp_path):
    with pytest.raises(FileNotFoundError):
        convert_appendix(tmp_path / "nope.md", target="pdf")


def test_convert_to_pdf_via_soffice(tmp_path, conversion_works):
    if not conversion_works:
        pytest.skip("конвертер (pandoc/LibreOffice) недоступен или не работает в среде")
    md = tmp_path / "lot_appendix.md"
    md.write_text(SAMPLE_MD, encoding="utf-8")
    result = convert_appendix(md, target="pdf")
    assert result is not None
    assert result.suffix == ".pdf"
    assert result.exists()
    # PDF начинается с %PDF.
    assert result.read_bytes()[:4] == b"%PDF"


def test_convert_to_docx_via_soffice(tmp_path, conversion_works):
    if not conversion_works:
        pytest.skip("конвертер (pandoc/LibreOffice) недоступен или не работает в среде")
    md = tmp_path / "lot_appendix.md"
    md.write_text(SAMPLE_MD, encoding="utf-8")
    result = convert_appendix(md, target="docx")
    assert result is not None
    assert result.suffix == ".docx"
    assert result.exists()
    # DOCX = ZIP, начинается с PK.
    assert result.read_bytes()[:2] == b"PK"


def test_convert_returns_none_when_no_converter(tmp_path, monkeypatch):
    """Если ни pandoc, ни LibreOffice недоступны — None, .md остаётся."""
    import parser.exporters.etp.md_convert as mc
    monkeypatch.setattr(mc, "_has", lambda tool: False)
    monkeypatch.setattr(mc, "soffice_bin", lambda: None)
    md = tmp_path / "lot_appendix.md"
    md.write_text(SAMPLE_MD, encoding="utf-8")
    result = convert_appendix(md, target="pdf")
    assert result is None
    assert md.exists()  # .md сохранён
