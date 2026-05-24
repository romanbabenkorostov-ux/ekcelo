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


def test_build_osv_recon_report():
    """PR-ε: 3 строки ОСВ против 2-объектной структуры → 2 missing-in-cad
    (одна КН-привязанная не из кадастра, одна без КН) + 1 missing-in-osv."""
    structure = {
        "cadastre_objects": [
            {"id": "c1", "cadastral_number": "61:44:0050706:1",
             "object_type": "Земельный участок",
             "accounting_account": "01.01"},
            {"id": "c2", "cadastral_number": "61:44:0050706:99",
             "object_type": "Здание",
             "accounting_account": "01.01"},  # в structure есть, в ОСВ нет
        ],
    }
    osv = {
        "exported_at": "2026-04-10T10:00:00Z",
        "rows": [
            {"row_n": 1, "account": "01.01", "inv_number": "ОС-001",
             "name": "Земельный участок",
             "cn_hints": ["61:44:0050706:1"],  # совпадает с c1
             "close_dt": 1_500_000.00},
            {"row_n": 2, "account": "01.01", "inv_number": "ОС-002",
             "name": "Хозблок", "cn_hints": [],  # нет в кадастре
             "close_dt": 250_000.00},
            {"row_n": 3, "account": "08", "inv_number": "ОНС-007",
             "name": "Затраты на мансарду", "cn_hints": [],  # счёт 08
             "close_dt": 1_350_000.00},
        ],
    }
    builder = MarkdownBuilder(tracker=SourceTracker(), title="ОСВ test")
    _09.build_osv_recon_report(structure, osv, date(2026, 4, 15), builder)
    md = "\n".join(builder._lines)
    # Счета сгруппированы
    assert "§01.01" in md
    assert "§08" in md
    # Missing-in-cad: ОС-002 (Хозблок) + ОНС-007
    assert "ОС-002" in md
    assert "ОНС-007" in md
    # Missing-in-osv: c2 (61:44:0050706:99)
    assert "61:44:0050706:99" in md
    # Рекомендация присутствует
    assert "рекомендовать" in md.lower()


def test_load_osv_returns_none_when_missing(tmp_path: Path):
    assert _09.load_osv(tmp_path) is None


def test_build_photo_report_returns_none_when_no_photos(tmp_path: Path):
    """PR-ζ: фотоотчёт graceful-skip когда фото нет."""
    (tmp_path / "_data").mkdir()
    out = _09.build_photo_report(tmp_path, {}, [],
                                  tmp_path / "report.docx")
    assert out is None


def test_integration_mini_fixture_e2e(tmp_path: Path):
    """E2E: make_mini_fixture с тремя флагами → ручной вызов обоих
    отчётов через build_pledge_report / build_osv_recon_report → проверка
    что MD-файлы валидны (§11 spec'а Integration acceptance)."""
    import subprocess

    fixture_dir = tmp_path / "proj"
    res = subprocess.run(
        [sys.executable,
         str(SCRIPTS / "dev" / "make_mini_fixture.py"),
         str(fixture_dir),
         "--with-pledge-chain", "--with-osv", "--with-overlay"],
        capture_output=True, text=True, timeout=30,
        env={"PYTHONPATH": str(SCRIPTS.parent), "PATH": "/usr/bin:/bin"},
    )
    assert res.returncode == 0, f"fixture failed: {res.stderr}"
    assert (fixture_dir / "_data" / "structure.json").exists()
    assert (fixture_dir / "_data" / "documents.json").exists()
    assert (fixture_dir / "_data" / "osv_cache.json").exists()

    # Загрузить и прогнать оба отчёта программно
    structure = _09.load_structure(fixture_dir)
    documents = _09.load_documents(fixture_dir)
    osv = _09.load_osv(fixture_dir)
    target = date(2026, 4, 15)

    # 1. Залоговая таблица
    pb = MarkdownBuilder(tracker=SourceTracker(),
                         title=f"Залоги — {target.isoformat()}")
    _09.build_pledge_report(structure, documents, target, pb)
    pledges_path = pb.save(fixture_dir / "reports" / "pledges.md")
    assert pledges_path.exists()
    md = pledges_path.read_text(encoding="utf-8")
    assert "§1. Без залога" in md
    assert "§2. С залогом объекта" in md
    assert "§3. С залогом доли в УК" in md
    assert "§4. С залогом и объекта" in md

    # 2. ОСВ-сверка
    ob = MarkdownBuilder(tracker=SourceTracker(),
                         title=f"ОСВ — {target.isoformat()}")
    _09.build_osv_recon_report(structure, osv, target, ob)
    osv_path = ob.save(fixture_dir / "reports" / "osv.md")
    assert osv_path.exists()
    md_osv = osv_path.read_text(encoding="utf-8")
    assert "§01.01" in md_osv
    # ОНС-007 (счёт 08) присутствует в стубе
    assert "ОНС-007" in md_osv


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
