"""
tests/test_osv_assets.py — парсер ОСВ → fixed_asset (ADR-006 §G).
Мини-ОСВ строится в памяти openpyxl (без бинаря в репо), включая счёт 01.08 (ОКС).
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

openpyxl = pytest.importorskip("openpyxl")
from egrn_parser.parsers import osv_assets as OSV  # noqa: E402


def _make_osv(path: Path) -> None:
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.append(["Общество с ограниченной ответственностью «Пример»"])
    ws.append(["Оборотно-сальдовая ведомость по счету 01"])
    ws.append(["Период: 2025 г."])
    ws.append([None, "Субконто", "Сальдо на начало"])
    ws.append([None, "01.01", 1000000])
    ws.append([None, "Насос FANCY FZ 32-200", 119166.66, 119166.66, 1])
    ws.append([None, "Насос FANCY FZ 32-200", 119166.67, 119166.67, 1])  # дубль → агрегат
    ws.append([None, "Линия розлива Minerva", 10999394.61, 10999394.61, 1])
    ws.append([None, "01.08", 5000000])                                   # ОКС без прав
    ws.append([None, "Цех первичной переработки (не оформлен)", 5000000, 5000000, 1])
    wb.save(str(path))


def test_parse_osv_aggregates_and_flags_okc(tmp_path):
    f = tmp_path / "osv.xlsx"
    _make_osv(f)
    assets = OSV.parse_osv(f)
    by_name = {a["name"]: a for a in assets}

    pump = by_name["Насос FANCY FZ 32-200"]
    assert pump["account"] == "01.01" and pump["units"] == 2          # 2 строки → агрегат
    assert round(pump["cost"], 2) == 238333.33 and pump["qty"] == 2
    assert pump["on_cadastre"] == 1
    assert by_name["Линия розлива Minerva"]["units"] == 1

    okc = by_name["Цех первичной переработки (не оформлен)"]
    assert okc["account"] == "01.08" and okc["on_cadastre"] == 0       # ОКС без кадастра
    assert assets and assets[0]["osv_period"] == "2025"


def test_upsert_assets_idempotent(tmp_path):
    f = tmp_path / "osv.xlsx"
    _make_osv(f)
    assets = OSV.parse_osv(f)
    c = sqlite3.connect(":memory:")
    r1 = OSV.upsert_assets(c, assets, source_file="osv.xlsx")
    assert r1["inserted"] == len(assets) and r1["updated"] == 0
    r2 = OSV.upsert_assets(c, assets)
    assert r2["inserted"] == 0 and r2["updated"] == len(assets)
    n = c.execute("SELECT COUNT(*) FROM fixed_asset").fetchone()[0]
    assert n == len(assets)
    # ОКС 01.08 помечен on_cadastre=0
    okc = c.execute("SELECT on_cadastre FROM fixed_asset WHERE account='01.08'").fetchone()
    assert okc[0] == 0
