# -*- coding: utf-8 -*-
"""Tests для assembler'а (13_assemble_contract_v1)."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCRIPT = ROOT / "parser" / "scripts" / "pirushin_sosn_rocha_13_assemble_contract_v1.py"


def _load():
    spec = importlib.util.spec_from_file_location("assembler", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


A = _load()


def _make_project(tmp_path: Path) -> Path:
    """Создаёт Surveycontract/ с пред-заготовленными MD-файлами."""
    sc = tmp_path / "Surveycontract"
    for sub in ("tz1-content", "body", "tz2-calculation", "sborki", "gotovo", "upd"):
        (sc / sub).mkdir(parents=True, exist_ok=True)

    (sc / "tz1-content" / "TZ1_20260527_140000.md").write_text(
        "# ТЗ-1 (тип: ГК-39)\nОбъекты: 23\n",
        encoding="utf-8",
    )
    (sc / "body" / "Contract_20260527-1_20260527_141000.md").write_text(
        "# Договор № 20260527-1\n*(тип: ГК-39)*\nТекст договора...\n",
        encoding="utf-8",
    )
    (sc / "tz2-calculation" / "Appendix2_20260527-1_20260527_142000.md").write_text(
        "# Приложение №2 (тип: ГК-39)\nКалендарный план...\n",
        encoding="utf-8",
    )
    return tmp_path


def test_scan_group_finds_tz1(tmp_path):
    project = _make_project(tmp_path)
    items = A.scan_group(project / "Surveycontract", "tz1")
    assert len(items) == 1
    assert items[0]["name"] == "TZ1_20260527_140000.md"
    assert items[0]["ts"] == "20260527_140000"
    # predmet_kind распознан из тела MD.
    assert items[0]["predmet_kind"] == "gk39"


def test_scan_group_parses_contract_number(tmp_path):
    project = _make_project(tmp_path)
    items = A.scan_group(project / "Surveycontract", "body")
    assert items[0]["number"] == "20260527-1"


def test_assemble_creates_sborka_and_gotovo(tmp_path):
    project = _make_project(tmp_path)
    sc = project / "Surveycontract"

    result = A.assemble(
        project,
        tz1=sc / "tz1-content" / "TZ1_20260527_140000.md",
        body=sc / "body" / "Contract_20260527-1_20260527_141000.md",
        calc=sc / "tz2-calculation" / "Appendix2_20260527-1_20260527_142000.md",
        upd=None,
        contract_number="20260527-1",
        version=1,
        predmet_kind="gk39",
        formats=("md", "json"),
    )

    assert Path(result["sborka_path"]).exists()
    cfg = json.loads(Path(result["sborka_path"]).read_text(encoding="utf-8"))
    assert cfg["contract_number"] == "20260527-1"
    assert cfg["predmet_kind"] == "gk39"
    assert cfg["components"]["tz1"].startswith("tz1-content/")
    assert cfg["components"]["upd"] is None
    assert "md" in result["gotovo_paths"]
    assert "json" in result["gotovo_paths"]

    combined = Path(result["gotovo_paths"]["md"]).read_text(encoding="utf-8")
    assert "Техническое задание №1" in combined
    assert "Тело договора" in combined
    assert "Календарный план" in combined


def test_assemble_versioning_via_parent_sborka(tmp_path):
    """Допсоглашение (v2) — со ссылкой на parent (v1)."""
    project = _make_project(tmp_path)
    sc = project / "Surveycontract"
    args = dict(
        tz1=sc / "tz1-content" / "TZ1_20260527_140000.md",
        body=sc / "body" / "Contract_20260527-1_20260527_141000.md",
        calc=sc / "tz2-calculation" / "Appendix2_20260527-1_20260527_142000.md",
        upd=None,
        contract_number="20260527-1",
        predmet_kind="gk39",
        formats=("json",),
    )

    r_v1 = A.assemble(project, version=1, **args)
    r_v2 = A.assemble(project, version=2, parent_sborka=Path(r_v1["sborka_path"]).name, **args)

    cfg_v2 = json.loads(Path(r_v2["sborka_path"]).read_text(encoding="utf-8"))
    assert cfg_v2["version"] == 2
    assert cfg_v2["_parent_sborka"] == Path(r_v1["sborka_path"]).name


def test_assemble_subcontract_chain(tmp_path):
    """Субподряд: `_parent_contract` ссылается на parent-номер."""
    project = _make_project(tmp_path)
    sc = project / "Surveycontract"
    result = A.assemble(
        project,
        tz1=sc / "tz1-content" / "TZ1_20260527_140000.md",
        body=sc / "body" / "Contract_20260527-1_20260527_141000.md",
        calc=sc / "tz2-calculation" / "Appendix2_20260527-1_20260527_142000.md",
        upd=None,
        contract_number="SUB-001",
        parent_contract="20260527-1",
        formats=("json",),
    )
    cfg = json.loads(Path(result["sborka_path"]).read_text(encoding="utf-8"))
    assert cfg["_parent_contract"] == "20260527-1"
    assert cfg["contract_number"] == "SUB-001"
