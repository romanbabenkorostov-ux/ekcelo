#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""09_make_reports_v1 — console-CLI отчёты по проекту (PR-δ..ζ).

Реализует dev/SPEC_TEMPORAL_REPORTS.md §8 (CLI с подменю):
  [1] ОСВ-сверка   (PR-ε)
  [2] Залоговая таблица — 4 секции (PR-δ, реализовано)
  [3] Фотоотчёт   (PR-ζ)
  [4] Формат output (md / docx / both) — toggle на сессию
  [Q] Выход

Пример:
    python3 parser/scripts/pirushin_sosn_rocha_09_make_reports_v1.py /path/to/project
    python3 parser/scripts/pirushin_sosn_rocha_09_make_reports_v1.py /path/to/project --as-of 2026-04-15

Архитектура: один project_dir → один CLI-session = одна точка T → один
timestamp для всех файлов сессии (§8.7).
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Literal


SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS.parent))  # parser/
sys.path.insert(0, str(SCRIPTS.parent.parent))  # ekcelo/

from egrn_parser.documents_schema import (  # noqa: E402
    EXTRACT_KINDS, load_documents, parse_date,
)
from egrn_parser.temporal import (  # noqa: E402
    collect_pledge_holders, founder_chain_has_pledge, resolve_state,
)
from utils.report_builder import (  # noqa: E402
    DocxNativeBuilder, MarkdownBuilder, SourceTracker,
)


# ─── Console UI helpers (заимствовано из 06_photo_report_to_docx_v3, §17.10) ─


class C:
    G = "\033[92m"; R = "\033[91m"; Y = "\033[93m"; CY = "\033[96m"
    B = "\033[1m"; X = "\033[0m"


def cp(t: str = "", c: str = "") -> None:
    print(f"{c}{t}{C.X}" if c else t)


def ask(prompt: str, default: str = "") -> str:
    suffix = f" [{default}]" if default else ""
    ans = input(f"{prompt}{suffix}: ").strip()
    return ans or default


def ask_yn(question: str, default: bool = True) -> bool:
    suffix = " (Y/n): " if default else " (y/N): "
    while True:
        ans = input(question + suffix).strip().lower()
        if not ans:
            return default
        if ans in ("y", "yes", "д", "да"):
            return True
        if ans in ("n", "no", "н", "нет"):
            return False
        cp("Введите 'y' или 'n'", C.Y)


# ─── Project loading ────────────────────────────────────────────────────────


def load_structure(root: Path) -> dict:
    """Читает <project>/_data/structure[_<slug>].json."""
    candidates = [root / "_data" / "structure.json"]
    candidates += sorted((root / "_data").glob("structure_*.json"))
    for p in candidates:
        if p.exists():
            return json.loads(p.read_text(encoding="utf-8"))
    raise FileNotFoundError(
        f"structure.json не найден в {root}/_data/. Запустите 052 сначала."
    )


def load_enriched(root: Path) -> dict:
    """Читает <project>/_data/enriched.json (canonical-приоритет)."""
    data_dir = root / "_data"
    canonical = data_dir / "enriched.json"
    if canonical.exists():
        try:
            return json.loads(canonical.read_text(encoding="utf-8"))
        except Exception:
            pass
    for p in sorted(data_dir.glob("enriched_*.json")):
        try:
            return json.loads(p.read_text(encoding="utf-8"))
        except Exception:
            continue
    return {}


# ─── Report 2: Залоговая таблица (PR-δ) ─────────────────────────────────────


def _format_units(cad: dict) -> tuple[str, str, str, str]:
    """(адрес, вид, КН, площадь) для строки отчёта."""
    cn = cad.get("cadastral_number") or "—"
    obj = cad.get("object_type") or "—"
    vid = "ЗУ" if "земельн" in str(obj).lower() else "ОКС"
    area = cad.get("area")
    area_s = f"{area:,.1f}".replace(",", " ") if area else "—"
    return (cad.get("address") or "—", vid, cn, area_s)


def _pledge_holder_label(bens: dict, holder_key: str) -> str:
    ben = (bens or {}).get(holder_key) or {}
    attrs = ben.get("attrs") if isinstance(ben.get("attrs"), dict) else ben
    name = (attrs.get("Полное наименование") or attrs.get("Краткое наименование")
            or ben.get("Полное наименование") or holder_key)
    inn = attrs.get("ИНН") or ben.get("ИНН") or "—"
    return f"{name} (ИНН {inn})"


def build_pledge_report(
    structure: dict,
    documents: list[dict],
    target_date: date,
    builder,
) -> None:
    """4 секции залоговой таблицы (§8.4 spec'а).

    Без залога / залог объекта (групп. по залогодержателю объекта) /
    залог УК (групп. по залогодержателю доли, founder-chain до корня) /
    и объект и доли.
    """
    state = resolve_state(structure, documents, target_date)
    cads = state.get("cadastre_objects") or []
    bens = state.get("beneficiaries") or {}
    holder_keys = collect_pledge_holders(bens, cads)

    builder.heading(
        f"Таблица объектов по типам залога на {target_date.isoformat()}",
        level=1,
    )

    # Классификация: для каждого КН смотрим (a) есть ли restrictions с
    # ипотекой/залогом, (b) есть ли pledge в founder-chain enterprise'а,
    # связанного с этим КН через business_units → beneficiary_key.
    bu_by_cad: dict[str, list[dict]] = {}
    for bu in state.get("business_units") or []:
        anchor = bu.get("anchor_cadastral")
        if anchor:
            bu_by_cad.setdefault(anchor, []).append(bu)

    def _enterprise_key_for(cad: dict) -> str | None:
        cn = cad.get("cadastral_number")
        for bu in bu_by_cad.get(cn or "", []):
            k = bu.get("beneficiary_key")
            if k:
                return k
        return None

    rows_clean: list[list[str]] = []
    rows_obj_pledge: dict[str, list[list[str]]] = {}  # holder_label → rows
    rows_uk_pledge: dict[str, list[list[str]]] = {}
    rows_both: dict[str, list[list[str]]] = {}

    tracker: SourceTracker = builder.tracker

    src_main = tracker.ref(
        "structure",
        f"structure.json (snapshot на {target_date.isoformat()})",
    )

    for cad in cads:
        if not cad.get("cadastral_number"):
            continue
        addr, vid, cn, area = _format_units(cad)

        obj_restrictions = [
            r for r in (cad.get("restrictions") or [])
            if isinstance(r, dict)
            and r.get("type", "").lower() in {"ипотека", "залог"}
        ]
        has_obj_pledge = bool(obj_restrictions)

        ek = _enterprise_key_for(cad)
        uk_found = False
        uk_holder_label = None
        if ek:
            uk_found, _path = founder_chain_has_pledge(
                ek, bens, exclude_pledge_holders=holder_keys)
            if uk_found:
                # holder из founder-chain (не из restrictions)
                # — берём первого holder_key из exclude_set; для отчёта
                # подходит любой known holder, иначе fallback "неопределён".
                uk_holder_label = (
                    _pledge_holder_label(bens, next(iter(holder_keys)))
                    if holder_keys else "неопределённый залогодержатель"
                )

        if has_obj_pledge and uk_found:
            for r in obj_restrictions:
                hl = (r.get("beneficiary_name") or "—") + (
                    f" (ИНН {r['beneficiary_inn']})" if r.get("beneficiary_inn") else "")
                rows_both.setdefault(hl, []).append(
                    [addr, vid, cn, area,
                     f"{r.get('contract', '—')} → УК: {uk_holder_label or '—'}",
                     src_main])
        elif has_obj_pledge:
            for r in obj_restrictions:
                hl = (r.get("beneficiary_name") or "—") + (
                    f" (ИНН {r['beneficiary_inn']})" if r.get("beneficiary_inn") else "")
                rows_obj_pledge.setdefault(hl, []).append(
                    [addr, vid, cn, area, r.get("contract", "—"), src_main])
        elif uk_found:
            rows_uk_pledge.setdefault(uk_holder_label or "—", []).append(
                [addr, vid, cn, area, src_main])
        else:
            rows_clean.append([addr, vid, cn, area, src_main])

    # ── Эмиссия секций ──
    builder.heading("§1. Без залога", level=2)
    if rows_clean:
        builder.table(["Адрес", "Вид", "КН", "Площадь", "Источник"], rows_clean)
    else:
        builder.paragraph("Объектов без залога не найдено.")

    builder.heading("§2. С залогом объекта (группировка по залогодержателям)",
                    level=2)
    if rows_obj_pledge:
        for hl, rows in sorted(rows_obj_pledge.items()):
            builder.heading(hl, level=3)
            builder.table(["Адрес", "Вид", "КН", "Площадь", "Договор", "Источник"],
                          rows)
    else:
        builder.paragraph("Объектов с залогом самого объекта не найдено.")

    builder.heading("§3. С залогом доли в УК (через founder-chain)", level=2)
    if rows_uk_pledge:
        for hl, rows in sorted(rows_uk_pledge.items()):
            builder.heading(hl, level=3)
            builder.table(["Адрес", "Вид", "КН", "Площадь", "Источник"], rows)
    else:
        builder.paragraph("Объектов с залогом доли в УК не найдено.")

    builder.heading("§4. С залогом и объекта, и долей бенефициаров", level=2)
    if rows_both:
        for hl, rows in sorted(rows_both.items()):
            builder.heading(hl, level=3)
            builder.table(["Адрес", "Вид", "КН", "Площадь", "Договор",
                           "Источник"], rows)
    else:
        builder.paragraph("Объектов с обоими видами залога не найдено.")

    builder.sources_block()


# ─── CLI session ────────────────────────────────────────────────────────────


def _resolve_target_date(args, documents: list[dict]) -> date:
    if args.as_of:
        return parse_date(args.as_of)
    extract_dates = [
        parse_date(d["doc_date"])
        for d in documents
        if d["kind"] in EXTRACT_KINDS
    ]
    return max(extract_dates) if extract_dates else date.today()


def _make_builders(
    fmt: Literal["md", "docx", "both"],
    title: str,
) -> list:
    """Создаёт список builders соответствующих выбранному format."""
    tracker = SourceTracker()
    out: list = []
    if fmt in ("md", "both"):
        out.append(("md", MarkdownBuilder(tracker=tracker, title=title)))
    if fmt in ("docx", "both"):
        try:
            out.append(("docx", DocxNativeBuilder(tracker=tracker, title=title)))
        except RuntimeError as e:
            cp(f"  ⚠ DOCX-рендерер недоступен: {e}", C.Y)
    return out


def _save_all(builders, out_dir: Path, base: str) -> list[Path]:
    saved = []
    for ext, b in builders:
        out = b.save(out_dir / f"{base}.{ext}")
        cp(f"  ✓ {out}", C.G)
        saved.append(out)
    return saved


def run_session(root: Path, target_date: date) -> int:
    cp(f"\n{'═' * 70}", C.B)
    cp(f"  ekcelo: Отчёты по проекту  ({root.name})", C.B)
    cp(f"{'═' * 70}\n", C.B)

    try:
        structure = load_structure(root)
    except FileNotFoundError as e:
        cp(f"✗ {e}", C.R)
        return 1
    enriched = load_enriched(root)
    if enriched and "beneficiaries" in enriched and "beneficiaries" not in structure:
        structure["beneficiaries"] = enriched["beneficiaries"]

    documents = load_documents(root)

    cp(f"Точка актуальности T: {target_date.isoformat()}", C.CY)
    cp(f"Документов: {len(documents)} "
       f"(выписок: {sum(1 for d in documents if d['kind'] in EXTRACT_KINDS)})",
       C.CY)

    out_dir = root / "reports"
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    fmt: Literal["md", "docx", "both"] = "both"

    while True:
        cp(f"\nФормат output: {fmt}", C.CY)
        cp("[1] ОСВ-сверка                        (не реализовано в v1)")
        cp("[2] Таблица залогов (4 секции)")
        cp("[3] Фотоотчёт по проекту              (не реализовано в v1)")
        cp("[4] Формат output (md / docx / both)")
        cp("[Q] Выход")
        choice = ask("Выбор").lower()

        if choice == "1":
            cp("  ОСВ-сверка пока не реализована (см. PR-ε).", C.Y)
        elif choice == "2":
            title = f"Залоговая таблица — {target_date.isoformat()}"
            builders = _make_builders(fmt, title)
            for _, b in builders:
                build_pledge_report(structure, documents, target_date, b)
            _save_all(builders, out_dir, f"report_pledges_{ts}")
        elif choice == "3":
            cp("  Фотоотчёт пока не реализован (см. PR-ζ).", C.Y)
        elif choice == "4":
            new_fmt = ask("Выберите md / docx / both", default=fmt).lower()
            if new_fmt in ("md", "docx", "both"):
                fmt = new_fmt  # type: ignore[assignment]
            else:
                cp("  Допустимы только: md, docx, both.", C.Y)
        elif choice in ("q", "quit", "exit", ""):
            break
        else:
            cp(f"  Неизвестная команда: {choice!r}", C.Y)

    cp("\nГотово.", C.G)
    return 0


def main() -> int:
    p = argparse.ArgumentParser(
        description="Отчёты по проекту ekcelo (залоги, ОСВ-сверка, фотоотчёт)")
    p.add_argument("project_dir", type=Path,
                   help="корень проекта с _data/structure.json")
    p.add_argument("--as-of", type=str,
                   help="ISO YYYY-MM-DD; default = max(extract_date)")
    args = p.parse_args()

    root = args.project_dir.expanduser().resolve()
    if not root.exists():
        cp(f"✗ Проект не найден: {root}", C.R)
        return 1

    documents = load_documents(root) if (root / "_data" / "documents.json").exists() else []
    try:
        target = _resolve_target_date(args, documents)
    except ValueError as e:
        cp(f"✗ {e}", C.R)
        return 1

    return run_session(root, target)


if __name__ == "__main__":
    sys.exit(main())
