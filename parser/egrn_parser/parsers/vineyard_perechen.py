"""
egrn_parser/parsers/vineyard_perechen.py — парсер перечня виноградных насаждений
из залоговых/оценочных документов (ADR-006, текстовый источник).

Вход: текст с блоками «Многолетние насаждения (виноградные насаждения),
расположенные на Предмете залога N…» с характеристиками насаждения (фед. реестр,
площадь, сорт привоя/подвоя, код сорта, год высадки, число кустов).

Выход → агро-слой: каждый блок = `agro_parcel` (насаждение, площадь, land-привязка
опц., расширенные поля в attrs) + `agro_crop_cycle` (виноград, perennial, сорт-привой,
год высадки → sow_date). §6, source='perechen'.

Ценообразующая семантика (ADR-006 §K): сорт+подвой+год высадки+число кустов —
характеристики НАСАЖДЕНИЯ на поверхности контура ЗУ (геопривязка, почва, климат,
накопленные погодные условия), дающего урожай определённого качества при уходе.
"""
from __future__ import annotations

import json
import re
import sqlite3
from typing import Any, Optional

_BLOCK_SPLIT = re.compile(r"Многолетние насаждения", re.IGNORECASE)

_FIELDS = {
    "pledge_item":   re.compile(r"Предмете?\s+залога\s*№?\s*(\d+)", re.I),
    "federal_reg_no": re.compile(r"федеральном\s+реестре[^:]*:\s*([\d\-]+)", re.I),
    "area_ha":       re.compile(r"Площадь\s+виноградного\s+насаждения:\s*([\d  ,.]+)\s*га", re.I),
    "variety":       re.compile(r"сорта\s+привоя\)\s*:\s*([^\n;]+)", re.I),
    "variety_code":  re.compile(r"государственном\s+реестре\s+селекционных[^:]*:\s*(\d+)", re.I),
    "area_variety_ha": re.compile(r"Площадь\s+сорта\s+винограда:\s*([\d  ,.]+)\s*га", re.I),
    "planting_year": re.compile(r"Год\s+высадки:\s*(\d{4})", re.I),
    "rootstock":     re.compile(r"сорта\s+подвоя\)\s*:\s*([^\n;]+)", re.I),
    "vines_count":   re.compile(r"Количество\s+виноградных\s+кустов[^:]*:\s*([\d  ]+)", re.I),
}


def _num(s: Optional[str]) -> Optional[float]:
    if not s:
        return None
    t = s.replace("\xa0", "").replace(" ", "").replace(",", ".").strip()
    try:
        return float(t)
    except ValueError:
        return None


def _int(s: Optional[str]) -> Optional[int]:
    n = _num(s)
    return int(n) if n is not None else None


def parse_planting_descriptions(text: str) -> list[dict[str, Any]]:
    """Текст → список насаждений с полями (по блокам «Многолетние насаждения»)."""
    out = []
    for chunk in _BLOCK_SPLIT.split(text or ""):
        if "Предмет" not in chunk and "привоя" not in chunk:
            continue
        rec: dict[str, Any] = {}
        for key, rx in _FIELDS.items():
            m = rx.search(chunk)
            rec[key] = m.group(1).strip() if m else None
        if not (rec.get("federal_reg_no") or rec.get("variety")):
            continue
        rec["pledge_item"] = _int(rec.get("pledge_item"))
        rec["area_ha"] = _num(rec.get("area_ha"))
        rec["area_variety_ha"] = _num(rec.get("area_variety_ha"))
        rec["planting_year"] = _int(rec.get("planting_year"))
        rec["vines_count"] = _int(rec.get("vines_count"))
        out.append(rec)
    return out


def plantings_to_agro_records(plantings: list[dict[str, Any]], *,
                              land_cad_by_pledge: Optional[dict[int, str]] = None,
                              confidence: float = 0.7) -> list[dict[str, Any]]:
    """Насаждения → [{parcel, cycle}] для записи в агро-слой (ADR-006).

    `land_cad_by_pledge` — опц. карта «предмет залога → КН ЗУ» (привязка к земле)."""
    land_map = land_cad_by_pledge or {}
    src = {"source": "perechen", "confidence": confidence}
    recs = []
    for p in plantings:
        pledge = p.get("pledge_item")
        parcel_code = f"ПЗ-{pledge}" if pledge is not None else (p.get("federal_reg_no") or "насаждение")
        attrs = {k: p[k] for k in ("federal_reg_no", "variety_code", "rootstock",
                                   "vines_count", "area_variety_ha", "pledge_item")
                 if p.get(k) is not None}
        parcel = {"parcel_code": parcel_code, "season_year": p.get("planting_year"),
                  "area_ha": p.get("area_ha"), "land_cad": land_map.get(pledge),
                  "attrs": attrs, **src}
        cycle = {"crop": "виноград", "cycle_kind": "perennial",
                 "variety": p.get("variety"),
                 "sow_date": (str(p["planting_year"]) if p.get("planting_year") else None),
                 "season_year": p.get("planting_year"), "crop_status": "fact", **src}
        recs.append({"parcel": parcel, "cycle": cycle})
    return recs


def ingest_plantings(conn: sqlite3.Connection, text: str, *,
                     land_cad_by_pledge: Optional[dict[int, str]] = None) -> dict[str, Any]:
    """Разобрать перечень и записать в agro_parcel/agro_crop_cycle (миграция 0005)."""
    plantings = parse_planting_descriptions(text)
    recs = plantings_to_agro_records(plantings, land_cad_by_pledge=land_cad_by_pledge)
    for r in recs:
        p, c = r["parcel"], r["cycle"]
        parcel_id = conn.execute(
            "INSERT INTO agro_parcel(parcel_code, season_year, area_ha, land_cad, "
            "attrs, source, confidence) VALUES(?,?,?,?,?,?,?)",
            (p["parcel_code"], p["season_year"], p["area_ha"], p["land_cad"],
             json.dumps(p["attrs"], ensure_ascii=False), p["source"], p["confidence"])
        ).lastrowid
        conn.execute(
            "INSERT INTO agro_crop_cycle(parcel_id, cycle_kind, crop, variety, "
            "sow_date, season_year, crop_status, source, confidence) "
            "VALUES(?,?,?,?,?,?,?,?,?)",
            (parcel_id, c["cycle_kind"], c["crop"], c["variety"], c["sow_date"],
             c["season_year"], c["crop_status"], c["source"], c["confidence"]))
    conn.commit()
    return {"plantings": len(plantings), "written": len(recs)}
