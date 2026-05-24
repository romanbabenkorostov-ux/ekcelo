"""Тесты PR-δ: 09_make_reports_v1.py (залоговая таблица end-to-end)."""
from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from datetime import date
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS.parent))

_spec = importlib.util.spec_from_file_location(
    "_09_v1", SCRIPTS / "pirushin_sosn_rocha_09_make_reports_v1.py")
_09 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_09)

from utils.report_builder import MarkdownBuilder, SourceTracker  # noqa: E402


def _fixture_structure_with_pledge() -> dict:
    """Структура с 3 объектами: 1 без залога, 1 с залогом объекта, 1 с
    залогом доли через founder-chain."""
    return {
        "enterprise": {"name_short": "ДЕМО-ПРОМ"},
        "cadastre_objects": [
            {"id": "c1", "cadastral_number": "61:44:0050706:1",
             "object_type": "Земельный участок", "address": "addr1",
             "area": 1500.0},
            {"id": "c2", "cadastral_number": "61:44:0050706:31",
             "object_type": "Здание", "address": "addr2",
             "area": 850.0,
             "restrictions": [{
                 "type": "ипотека", "beneficiary_name": "АО БАНК-1",
                 "beneficiary_inn": "7700000099", "contract": "ИП-1"}]},
            {"id": "c3", "cadastral_number": "61:44:0050706:33",
             "object_type": "Земельный участок", "address": "addr3",
             "area": 2000.0},
        ],
        "business_units": [
            {"id": "bu1", "anchor_cadastral": "61:44:0050706:33",
             "beneficiary_key": "ben_main"},
        ],
        "beneficiaries": {
            "ben_main": {"_kind": "legal",
                         "attrs": {"ИНН": "6164098765",
                                   "Полное наименование": "ООО ДЕМО-ПРОМ"},
                         "Бенефициар (ключ)": "ben_holding"},
            "ben_holding": {"_kind": "legal", "has_pledge": True,
                            "attrs": {"ИНН": "7700000001"},
                            "Обременения доли": [{
                                "Сведения о залогодержателе": {
                                    "ИНН": "7700000088",
                                },
                            }]},
            "ben_bank": {"_kind": "legal",
                         "attrs": {"ИНН": "7700000088",
                                   "Полное наименование": "АО БАНК-2"}},
        },
    }


def test_build_pledge_report_classifies_all_4_sections():
    builder = MarkdownBuilder(tracker=SourceTracker(),
                              title="Тест залоговый отчёт")
    _09.build_pledge_report(
        _fixture_structure_with_pledge(), [], date(2026, 4, 15), builder,
    )
    md = "\n".join(builder._lines)
    # Все 4 секции присутствуют
    assert "§1. Без залога" in md
    assert "§2. С залогом объекта" in md
    assert "§3. С залогом доли в УК" in md
    assert "§4. С залогом и объекта" in md
    # c1 — без залога
    assert "61:44:0050706:1" in md
    # c2 — залог объекта (АО БАНК-1)
    assert "АО БАНК-1" in md
    # c3 — залог УК (через founder-chain через ben_holding)
    assert "61:44:0050706:33" in md
    # Источники
    assert "<details>" in md


def test_cli_smoke_help(tmp_path: Path):
    """CLI запускается без ошибок и выводит usage."""
    res = subprocess.run(
        [sys.executable, str(SCRIPTS / "pirushin_sosn_rocha_09_make_reports_v1.py"),
         "--help"],
        capture_output=True, text=True, timeout=10,
    )
    assert res.returncode == 0
    assert "project_dir" in res.stdout
    assert "--as-of" in res.stdout


def test_cli_smoke_nonexistent_project(tmp_path: Path):
    """CLI на несуществующем пути возвращает 1."""
    res = subprocess.run(
        [sys.executable,
         str(SCRIPTS / "pirushin_sosn_rocha_09_make_reports_v1.py"),
         str(tmp_path / "missing")],
        capture_output=True, text=True, timeout=10,
    )
    assert res.returncode == 1
    assert "не найден" in res.stdout or "не найден" in res.stderr
