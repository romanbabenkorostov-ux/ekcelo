"""Тесты контракта KMZ 2.12.0: emit `<Data extract_date>` + sidecar `_data/documents.json`.

Покрывает инварианты §5/§6 контракта 2.12.0:
1. `<Document>/<ExtendedData>` содержит `<Data name="extract_date">YYYY-MM-DD</Data>`
   когда параметр `extract_date` передан в `build_kmz()`.
2. Поле опционально: если параметр не передан и `_data/documents.json` отсутствует —
   `<Data extract_date>` не эмитится (graceful, контракт 2.11.0 совместимость).
3. Если `_data/documents.json` есть — `extract_date` авто-резолвится через
   `_load_extract_date()` (max(doc_date) среди kind ∈ {egrn/egrul/egrip}_extract).
4. Sidecar `_data/documents.json` копируется в KMZ-архив как `_data/documents.json`
   (опционально, parser-internal soглашение; path зарезервирован в wire §5).
5. Валидация формата: `extract_date` НЕ ISO `YYYY-MM-DD` → `ValueError`.
"""
from __future__ import annotations
import importlib.util
import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


# 08_v2_2 импорт через importlib (имя файла содержит точку версии _v2_2).
_spec = importlib.util.spec_from_file_location(
    "_kmz_v2_2", SCRIPTS / "pirushin_sosn_rocha_08_build_kmz_v2_2.py")
_kmz = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_kmz)


KML_NS = {"kml": "http://www.opengis.net/kml/2.2",
          "atom": "http://www.w3.org/2005/Atom"}


def _read_kml_and_names(kmz_path: Path) -> tuple[str, set[str], dict[str, bytes]]:
    with zipfile.ZipFile(kmz_path, "r") as zf:
        names = set(zf.namelist())
        contents = {n: zf.read(n) for n in names if not n.endswith("/")}
        return contents["doc.kml"].decode("utf-8"), names, contents


def _document_extended_data(kml_text: str) -> dict[str, str]:
    """Собирает `{name: value}` из `<Document>/<ExtendedData>` (плоский dict)."""
    root = ET.fromstring(kml_text)
    doc = root.find("kml:Document", KML_NS)
    assert doc is not None
    ext = doc.find("kml:ExtendedData", KML_NS)
    if ext is None:
        return {}
    return {
        d.attrib.get("name", ""): d.findtext("kml:value", "", KML_NS)
        for d in ext.findall("kml:Data", KML_NS)
    }


# ─── 1. Явный параметр extract_date ─────────────────────────────────────────

def test_v2_2_emits_extract_date_when_param_passed(synthetic_root: Path):
    kmz = _kmz.build_kmz(synthetic_root, extract_date="2026-04-15")
    kml, _, _ = _read_kml_and_names(kmz)
    ed = _document_extended_data(kml)
    assert ed.get("extract_date") == "2026-04-15"


# ─── 2. Поле опционально (backward-compat 2.11.0) ───────────────────────────

def test_v2_2_skips_extract_date_when_no_source(synthetic_root: Path):
    kmz = _kmz.build_kmz(synthetic_root)
    kml, _, _ = _read_kml_and_names(kmz)
    ed = _document_extended_data(kml)
    assert "extract_date" not in ed
    # При этом kml_schema_version по-прежнему присутствует (2.11.0 invariant сохраняется).
    assert ed.get("kml_schema_version") == "2.1"


# ─── 3. Авто-резолв через documents.json ────────────────────────────────────

def test_v2_2_resolves_extract_date_from_documents_json(synthetic_root: Path):
    data_dir = synthetic_root / "_data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "documents.json").write_text(json.dumps({
        "schema_version": "1.0",
        "project_slug": "test",
        "documents": [
            {"doc_id": "ee_old", "kind": "egrn_extract", "doc_date": "2025-12-01"},
            {"doc_id": "ee_new", "kind": "egrn_extract", "doc_date": "2026-04-15"},
            {"doc_id": "ee_mid", "kind": "egrul_extract", "doc_date": "2026-03-01"},
            {"doc_id": "pc_1",   "kind": "purchase",     "doc_date": "2026-09-01"},  # не-выписка → игнор
        ],
    }, ensure_ascii=False), encoding="utf-8")

    kmz = _kmz.build_kmz(synthetic_root)
    kml, _, _ = _read_kml_and_names(kmz)
    ed = _document_extended_data(kml)
    # max(doc_date среди kind ∈ {egrn,egrul,egrip}_extract) = 2026-04-15
    assert ed.get("extract_date") == "2026-04-15"


def test_v2_2_param_overrides_documents_json(synthetic_root: Path):
    """Явный параметр build_kmz(extract_date=...) приоритетнее documents.json."""
    data_dir = synthetic_root / "_data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "documents.json").write_text(json.dumps({
        "documents": [
            {"doc_id": "ee_old", "kind": "egrn_extract", "doc_date": "2025-12-01"},
        ],
    }, ensure_ascii=False), encoding="utf-8")
    kmz = _kmz.build_kmz(synthetic_root, extract_date="2026-04-15")
    kml, _, _ = _read_kml_and_names(kmz)
    ed = _document_extended_data(kml)
    assert ed.get("extract_date") == "2026-04-15"  # параметр, не 2025-12-01


# ─── 4. Sidecar `_data/documents.json` в KMZ-архиве ─────────────────────────

def test_v2_2_copies_documents_json_into_kmz(synthetic_root: Path):
    data_dir = synthetic_root / "_data"
    data_dir.mkdir(parents=True, exist_ok=True)
    docs_payload = {"schema_version": "1.0", "documents": [
        {"doc_id": "ee_1", "kind": "egrn_extract", "doc_date": "2026-04-15"},
    ]}
    (data_dir / "documents.json").write_text(
        json.dumps(docs_payload, ensure_ascii=False), encoding="utf-8")
    kmz = _kmz.build_kmz(synthetic_root)
    _, names, contents = _read_kml_and_names(kmz)
    assert "_data/documents.json" in names
    # Содержимое идентично исходному (parser-internal соглашение §5).
    parsed = json.loads(contents["_data/documents.json"].decode("utf-8"))
    assert parsed == docs_payload


def test_v2_2_skips_documents_json_when_absent(synthetic_root: Path):
    kmz = _kmz.build_kmz(synthetic_root)
    _, names, _ = _read_kml_and_names(kmz)
    assert "_data/documents.json" not in names


# ─── 5. Валидация формата ───────────────────────────────────────────────────

def test_v2_2_rejects_invalid_extract_date_format(synthetic_root: Path):
    with pytest.raises(ValueError, match="ISO YYYY-MM-DD"):
        _kmz.build_kmz(synthetic_root, extract_date="15.04.2026")
    with pytest.raises(ValueError, match="ISO YYYY-MM-DD"):
        _kmz.build_kmz(synthetic_root, extract_date="2026-4-15")  # без leading zero
