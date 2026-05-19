"""Тесты контракта KMZ 2.11.0: `graph_node_id` + protocol pre-selection.

Покрывает инварианты §5/§6 контракта 2.11.0:
1. `kml_schema_version` 2.0 → 2.1 в `<Document>`.
2. Каждый Placemark из 5 классов (КН, БУ, EQ, BEN, photoPin) несёт `graph_node_id`,
   если sidecar `graph_node_index.json` присутствует.
3. Cross-match: каждое `graph_node_id` ↔ значение из sidecar (или fallback formula).
4. photoPin наследует `graph_node_id` родительского КН.
5. `graph.html` от `04_nspd_graph_v14` несёт `<meta name="ekcelo-graph-protocol" content="1">`.
6. `graph.html` содержит IIFE-listener `ekcelo.graph.select` + hash-routing.
7. `build_graph_node_index()` строит структуру по схеме `schema=1`.
8. Graceful fallback: KMZ без sidecar не падает; `graph_node_id` либо берётся из
   формулы (`cn`/`eq::<id>`/`legal::inn::<inn>`), либо отсутствует.
"""
from __future__ import annotations
import json
import re
import sys
import xml.etree.ElementTree as ET
import zipfile
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from pirushin_sosn_rocha_08_build_kmz_v2 import build_kmz, KML_SCHEMA_VERSION

# 04_nspd_graph_v14 импортируем напрямую (имя модуля начинается с цифры —
# используем importlib).
import importlib.util
_spec = importlib.util.spec_from_file_location(
    "_nspd_graph",
    Path(__file__).resolve().parents[1] / "scripts" / "04_nspd_graph_v14.py")
_nspd_graph = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_nspd_graph)


KML_NS = {"kml": "http://www.opengis.net/kml/2.2",
          "atom": "http://www.w3.org/2005/Atom"}


def _read_kml(kmz_path: Path) -> str:
    with zipfile.ZipFile(kmz_path, "r") as zf:
        return zf.read("doc.kml").decode("utf-8")


def _get_ext(pm: ET.Element, key: str) -> str | None:
    ext = pm.find("kml:ExtendedData", KML_NS)
    if ext is None:
        return None
    for d in ext.findall("kml:Data", KML_NS):
        if d.attrib.get("name") == key:
            return d.findtext("kml:value", "", KML_NS)
    return None


def _write_sidecar_into(root: Path) -> dict:
    """Пишет реалистичный `graph_node_index.json` под synthetic_root и возвращает его."""
    idx = {
        "schema": 1,
        "by_cad_number": {
            "61:44:0050706:1":   "61:44:0050706:1",
            "61:44:0050706:31":  "61:44:0050706:31",
            "61:44:0050706:119": "61:44:0050706:119",
            "61:44:0050706:120": "61:44:0050706:120",
            "61:44:0050706:77":  "61:44:0050706:77",
            "61:44:0050706:99":  "61:44:0050706:99",
        },
        "by_bu_name":   {"Филиал Ростов": "bu::abc123deadbeef"},
        "by_eq_id":     {"eq1": "eq::eq1", "eq2": "eq::eq2"},
        "by_ben_inn":   {"6164098765": "legal::inn::6164098765"},
        "by_ben_ogrn":  {"1026103098765": "legal::inn::6164098765"},
        "by_ben_name":  {"ООО Ромашка": "legal::inn::6164098765"},
    }
    (root / "_data" / "graph_node_index.json").write_text(
        json.dumps(idx, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return idx


# ─── 1. kml_schema_version ────────────────────────────────────────────────────

def test_kml_schema_version_is_2_1(synthetic_root: Path):
    """Контракт 2.11.0 §5: kml_schema_version 2.0 → 2.1 (MINOR wire-bump)."""
    assert KML_SCHEMA_VERSION == "2.1"
    kmz = build_kmz(synthetic_root)
    kml = _read_kml(kmz)
    root = ET.fromstring(kml)
    doc = root.find("kml:Document", KML_NS)
    ext = doc.find("kml:ExtendedData", KML_NS)
    versions = [d.findtext("kml:value", "", KML_NS)
                for d in ext.findall("kml:Data", KML_NS)
                if d.attrib.get("name") == "kml_schema_version"]
    assert versions == ["2.1"], versions


# ─── 2/3. graph_node_id присутствует и cross-match'ится с sidecar ────────────

def test_graph_node_id_emitted_when_sidecar_present(synthetic_root: Path):
    idx = _write_sidecar_into(synthetic_root)
    kmz = build_kmz(synthetic_root)
    kml = _read_kml(kmz)
    root = ET.fromstring(kml)

    # Соберём (styleUrl, graph_node_id) для каждого Placemark с релевантным префиксом.
    relevant_prefixes = ("cad_zu_", "cad_oks_", "cad_room_", "cad_str_",
                         "cad_ons_", "cad_bu_", "cad_eq_", "cad_ben_",
                         "photoPin_")
    hits: list[tuple[str, str | None]] = []
    for pm in root.iter("{http://www.opengis.net/kml/2.2}Placemark"):
        style = pm.findtext("kml:styleUrl", "", KML_NS).lstrip("#")
        if not any(style.startswith(p) for p in relevant_prefixes):
            continue
        gid = _get_ext(pm, "graph_node_id")
        hits.append((style, gid))

    assert hits, "не найдено ни одного Placemark с релевантным styleUrl"

    # Все классы кроме cad_ben_ (без <Point>, может остаться None для бенефициара
    # без идентификатора) должны нести непустой graph_node_id.
    missing = [(s, g) for s, g in hits if not s.startswith("cad_ben_") and not g]
    assert not missing, f"Placemark'и без graph_node_id (контракт 2.11.0 §6): {missing}"


def test_cross_match_kmz_to_sidecar(synthetic_root: Path):
    """Каждое значение `graph_node_id` присутствует в sidecar (cross-match §6)."""
    idx = _write_sidecar_into(synthetic_root)
    kmz = build_kmz(synthetic_root)
    kml = _read_kml(kmz)
    root = ET.fromstring(kml)

    # Множество всех значений из sidecar (все возможные node_id, на которые ссылается KMZ).
    sidecar_values: set[str] = set()
    for sub in ("by_cad_number", "by_bu_name", "by_eq_id",
                "by_ben_inn", "by_ben_ogrn", "by_ben_name"):
        sidecar_values.update(idx.get(sub, {}).values())

    for pm in root.iter("{http://www.opengis.net/kml/2.2}Placemark"):
        gid = _get_ext(pm, "graph_node_id")
        if not gid:
            continue
        assert gid in sidecar_values, (
            f"graph_node_id={gid!r} не найден в sidecar. "
            f"Возможные значения: {sorted(sidecar_values)}")


# ─── 4. photoPin наследует graph_node_id родительского КН ────────────────────

def test_photopin_carries_parent_cad(synthetic_root: Path):
    _write_sidecar_into(synthetic_root)
    kmz = build_kmz(synthetic_root)
    kml = _read_kml(kmz)
    root = ET.fromstring(kml)

    photopins = [pm for pm in root.iter("{http://www.opengis.net/kml/2.2}Placemark")
                 if pm.findtext("kml:styleUrl", "", KML_NS)
                       .lstrip("#").startswith("photoPin_")]
    assert photopins, "нет ни одного photoPin_"

    for pm in photopins:
        gid = _get_ext(pm, "graph_node_id")
        cad = _get_ext(pm, "cad_number")
        if cad:
            assert gid == cad, (
                f"photoPin: graph_node_id={gid!r} ≠ cad_number={cad!r} "
                f"(контракт 2.11.0 §5: photoPin несёт graph_node_id = кад.№ родителя)")


# ─── 5/6. graph.html: meta-тег + IIFE-listener ───────────────────────────────

def _render_graph_html_minimal() -> str:
    """Запускает render_html на минимальном наборе nodes/edges (для smoke-теста)."""
    nodes = [{"id": "cn::test", "label": "TEST", "kind": "object",
              "type": "Земельный участок",
              "color": {"background": "#000", "border": "#000"},
              "size": 16, "shape": "dot", "tooltip": "TEST",
              "attrs": {}, "deregistered": False}]
    edges: list[dict] = []
    return _nspd_graph.render_html(nodes, edges, "test_src", "test_out.html")


def test_meta_protocol_tag_present():
    """Контракт 2.11.0 §5/§6: `<meta name="ekcelo-graph-protocol" content="1">`."""
    html = _render_graph_html_minimal()
    pat = re.compile(
        r'<meta\s+name="ekcelo-graph-protocol"\s+content="1"\s*/?>',
        re.IGNORECASE)
    assert pat.search(html), "ekcelo-graph-protocol meta-тег отсутствует"


def test_hash_routing_js_present():
    """Контракт 2.11.0 §5: listener postMessage + hash."""
    html = _render_graph_html_minimal()
    assert "ekcelo.graph.select" in html, \
        "обработчик postMessage 'ekcelo.graph.select' отсутствует"
    assert "stabilizationIterationsDone" in html, \
        "отложенный apply на stabilizationIterationsDone отсутствует"
    # hash-routing: location.hash + node=
    assert re.search(r"location\.hash", html), "hash-routing отсутствует"


# ─── 7. build_graph_node_index() — структура schema=1 ────────────────────────

def test_build_graph_node_index_structure():
    """`04_nspd_graph_v14.build_graph_node_index` строит правильный sidecar."""
    nodes = [
        {"id": "61:44:0050706:1", "kind": "object",
         "attrs": {"cad_number": "61:44:0050706:1"}},
        {"id": "bu::abc", "kind": "business_unit",
         "attrs": {"Наименование": "Филиал Тест"}},
        {"id": "eq::eq1", "kind": "equipment",
         "attrs": {"id": "eq1", "name": "Котёл"}},
        {"id": "legal::inn::7707083893", "kind": "beneficiary",
         "attrs": {"attrs": {"ИНН": "7707083893"},
                   "Наименование (отображаемое)": "ООО Тест"}},
        {"id": "cat::Категория", "kind": "category", "attrs": {}},
    ]
    idx = _nspd_graph.build_graph_node_index(nodes)
    assert idx["schema"] == 1
    assert idx["by_cad_number"] == {"61:44:0050706:1": "61:44:0050706:1"}
    assert idx["by_bu_name"]    == {"Филиал Тест":   "bu::abc"}
    assert idx["by_eq_id"]      == {"eq1":           "eq::eq1"}
    assert idx["by_ben_inn"]    == {"7707083893":    "legal::inn::7707083893"}
    assert idx["by_ben_name"]   == {"ООО Тест":      "legal::inn::7707083893"}


# ─── 8. Graceful fallback: KMZ без sidecar ───────────────────────────────────

def test_graceful_fallback_without_sidecar(synthetic_root: Path):
    """Без `graph_node_index.json` build_kmz не падает; для КН используется формула
    `graph_node_id = cn`, для eq — `eq::<id>`."""
    # sidecar НЕ создаётся
    assert not (synthetic_root / "_data" / "graph_node_index.json").exists()
    kmz = build_kmz(synthetic_root)
    kml = _read_kml(kmz)
    root = ET.fromstring(kml)

    # Для КН-Placemark'а graph_node_id = cad_number (формула fallback).
    cad_placemarks = [pm for pm in root.iter("{http://www.opengis.net/kml/2.2}Placemark")
                      if pm.findtext("kml:styleUrl", "", KML_NS)
                            .lstrip("#").startswith(("cad_zu_", "cad_oks_",
                                                      "cad_room_", "cad_str_",
                                                      "cad_ons_"))]
    assert cad_placemarks
    for pm in cad_placemarks:
        gid = _get_ext(pm, "graph_node_id")
        cn = _get_ext(pm, "cad_number")
        assert gid == cn, f"fallback: graph_node_id={gid!r} ≠ cad_number={cn!r}"


# ─── 9. Idempotency с sidecar ────────────────────────────────────────────────

def test_idempotent_with_sidecar(synthetic_root: Path):
    """С sidecar тоже идемпотентно (sha256 KMZ совпадает между прогонами)."""
    import hashlib
    _write_sidecar_into(synthetic_root)
    h1 = hashlib.sha256(build_kmz(synthetic_root).read_bytes()).hexdigest()
    h2 = hashlib.sha256(build_kmz(synthetic_root).read_bytes()).hexdigest()
    assert h1 == h2, f"идемпотентность нарушена: {h1} ≠ {h2}"
