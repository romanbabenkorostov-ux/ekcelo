"""Тесты v17 chain (третья parser-команда, append-интеграция).

Покрытие:
  • 08_build_kmz_v2_2: `cn_to_id_part`/`style_id_for` корректно обрабатывают
    КН вида ``XX:XX:XXXXXXXX:NN/N`` (часть КН) — `/` → `__`.
  • 07_init_project_v2: `_cn_to_mask` ↔ `_mask_to_cn` round-trip для КН с
    частью; `cad_to_token` alias == `_cn_to_mask`.
  • 052_v2_1 `link_with_enriched`: фильтрация `_kind ∈ {ip, person}`;
    подъём `ИНН/ОГРН/КПП` из `ben["attrs"]` (bug-fix к v2).
  • 052_v2_1 `load_enriched_extras`: при наличии canonical `enriched.json`
    legacy `enriched_*.json` игнорируются (детерминизм).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path


SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS))


def _load(name: str, filename: str):
    spec = importlib.util.spec_from_file_location(name, SCRIPTS / filename)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


_kmz = _load("_kmz_v2_2", "pirushin_sosn_rocha_08_build_kmz_v2_2.py")
_init = _load("_init_v2", "pirushin_sosn_rocha_07_init_project_v2.py")
_struct = _load("_struct_v2_1", "pirushin_sosn_rocha_052_make_structure_v2_1.py")


# ── 08_build_kmz_v2_2 ───────────────────────────────────────────────────────

def test_08_cn_to_id_part_handles_part_cn():
    assert _kmz.cn_to_id_part("90:25:020102:119/1") == "90_25_020102_119__1"
    assert _kmz.cn_to_id_part("61:44:0050706:31") == "61_44_0050706_31"


def test_08_style_id_unique_for_cn_with_part():
    a = _kmz.style_id_for("zu", "90:25:020102:119")
    b = _kmz.style_id_for("zu", "90:25:020102:119/1")
    assert a != b
    assert "__1" in b and "__1" not in a


# ── 07_init_project_v2 ──────────────────────────────────────────────────────

def test_07_cn_round_trip_with_part():
    cn = "47:14:0000001:1/2"
    assert _init._mask_to_cn(_init._cn_to_mask(cn)) == cn


def test_07_cad_to_token_alias_is_cn_to_mask():
    assert _init.cad_to_token is _init._cn_to_mask
    assert _init.cad_to_token("61:44:0050706:31") == "61_44_0050706_31"


# ── 052_v2_1 link_with_enriched ─────────────────────────────────────────────

def _make_extras_for_link(*, nested_attrs: bool):
    """Синтетический extras: ЮЛ-головной + ИП + ФЛ.

    Если ``nested_attrs`` — ИНН/ОГРН/КПП лежат только в ``ben["attrs"]``
    (как в реальном v17), иначе на верхнем уровне.
    """
    yul_fields = {"ИНН": "7700000001", "ОГРН": "1027700000001", "КПП": "770001001"}
    if nested_attrs:
        yul = {
            "attrs": {
                "Полное наименование": "ООО АКМЕ-ПРОМ",
                "Краткое наименование": "АКМЕ-ПРОМ",
                **yul_fields,
            },
        }
    else:
        yul = {
            "Полное наименование": "ООО АКМЕ-ПРОМ",
            "Краткое наименование": "АКМЕ-ПРОМ",
            **yul_fields,
        }
    ip = {
        "_kind": "ip",
        "attrs": {"Полное наименование": "АКМЕ-ПРОМ ИВАНОВ И.И.",
                  "ИНН": "770000000099"},
    }
    person = {
        "_kind": "person",
        "attrs": {"Полное наименование": "АКМЕ-ПРОМ ПЕТРОВ П.П."},
    }
    return {
        "business_units": [],
        "beneficiaries": {"yul::1": yul, "ip::1": ip, "person::1": person},
    }


def test_052_link_picks_yul_skipping_ip_and_person():
    enterprise = {"name_short": "АКМЕ-ПРОМ"}
    extras = _make_extras_for_link(nested_attrs=False)
    _struct.link_with_enriched(enterprise, [], [], extras)
    assert enterprise["inn"] == "7700000001"
    assert enterprise["ogrn"] == "1027700000001"
    assert enterprise["kpp"] == "770001001"


def test_052_link_reads_inn_from_nested_attrs():
    """Bug-fix к v2: поля бенефициара лежат в ``ben["attrs"]``."""
    enterprise = {"name_short": "АКМЕ-ПРОМ"}
    extras = _make_extras_for_link(nested_attrs=True)
    _struct.link_with_enriched(enterprise, [], [], extras)
    assert enterprise["inn"] == "7700000001"
    assert enterprise["ogrn"] == "1027700000001"
    assert enterprise["kpp"] == "770001001"


# ── 052_v2_1 load_enriched_extras hotfix ────────────────────────────────────

def test_052_load_enriched_priority_canonical(tmp_path: Path):
    """При наличии canonical ``enriched.json`` legacy файлы не читаются."""
    canonical = {
        "data": {
            "business_units": [{"Ключ": "bu::new", "Объект (КН)": "61:44:0050706:31"}],
            "beneficiaries": {"yul::new": {"Полное наименование": "NEW"}},
        }
    }
    legacy = {
        "data": {
            "business_units": [
                {"Ключ": "bu::old1", "Объект (КН)": "61:44:0050706:32"},
                {"Ключ": "bu::old2", "Объект (КН)": "61:44:0050706:33"},
            ],
            "beneficiaries": {"yul::old": {"Полное наименование": "OLD"}},
        }
    }
    (tmp_path / "enriched.json").write_text(
        json.dumps(canonical, ensure_ascii=False), encoding="utf-8")
    (tmp_path / "enriched_20250101.json").write_text(
        json.dumps(legacy, ensure_ascii=False), encoding="utf-8")

    out = _struct.load_enriched_extras(tmp_path)
    bu_keys = [b.get("Ключ") for b in out["business_units"]]
    assert bu_keys == ["bu::new"]
    assert "yul::new" in out["beneficiaries"]
    assert "yul::old" not in out["beneficiaries"]


def test_052_load_enriched_fallback_to_legacy(tmp_path: Path):
    """Без canonical берём legacy ``enriched_*.json``."""
    legacy = {
        "data": {
            "business_units": [{"Ключ": "bu::old1", "Объект (КН)": "61:44:0050706:32"}],
            "beneficiaries": {"yul::old": {"Полное наименование": "OLD"}},
        }
    }
    (tmp_path / "enriched_20250101.json").write_text(
        json.dumps(legacy, ensure_ascii=False), encoding="utf-8")

    out = _struct.load_enriched_extras(tmp_path)
    bu_keys = [b.get("Ключ") for b in out["business_units"]]
    assert bu_keys == ["bu::old1"]
    assert "yul::old" in out["beneficiaries"]
