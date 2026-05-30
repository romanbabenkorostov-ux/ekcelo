"""response_handler + router: market_template extraction + MARP split."""
from __future__ import annotations

from lot_orchestrator.response_handler import extract_and_write_market_template
from lot_orchestrator.router import route_outputs


def test_extracts_and_writes_market_template(tmp_path):
    canonical = tmp_path / "market_template.md"
    response = (
        "Финальный отчёт.\n\n"
        "<SYSTEM_MARKET_TEMPLATE>\n"
        "## Карточка локации\n- район: центр\n"
        "</SYSTEM_MARKET_TEMPLATE>\n\n"
        "Продолжение."
    )
    result = extract_and_write_market_template(response, canonical)
    assert result.template_written
    assert canonical.read_text(encoding="utf-8").startswith("## Карточка локации")
    assert "SYSTEM_MARKET_TEMPLATE" not in result.cleaned_response


def test_market_template_idempotency(tmp_path):
    canonical = tmp_path / "market_template.md"
    response = "x<SYSTEM_MARKET_TEMPLATE>same</SYSTEM_MARKET_TEMPLATE>y"
    extract_and_write_market_template(response, canonical)
    sha1 = canonical.read_bytes()
    extract_and_write_market_template(response, canonical)
    assert canonical.read_bytes() == sha1


def test_missing_template_tags_returns_warning(tmp_path):
    canonical = tmp_path / "market_template.md"
    result = extract_and_write_market_template("no tags here", canonical)
    assert not result.template_written
    assert result.warning
    assert not canonical.exists()


def test_route_split_by_marp_marker(tmp_path):
    cleaned = "Final report body.\n\n<!-- MARP_START -->\n# Slide 1\n"
    routing = route_outputs(cleaned, tmp_path)
    assert routing.final_report_path.read_text(encoding="utf-8") == "Final report body.\n"
    assert routing.investment_slides_path.read_text(encoding="utf-8").startswith("# Slide 1")
    assert routing.warning is None


def test_route_missing_marker_warns_and_empty_slides(tmp_path):
    routing = route_outputs("Only report.", tmp_path)
    assert routing.final_report_path.read_text(encoding="utf-8") == "Only report.\n"
    assert routing.investment_slides_path.read_text(encoding="utf-8") == ""
    assert routing.warning
    assert "MARP_START" in routing.warning
