"""Temporal-overlay resolver + founder-chain pledge BFS.

Реализует ядро алгоритмов из dev/SPEC_TEMPORAL_REPORTS.md:
  • §3.3 `resolve_state(structure, documents, target_date)` —
    snapshot-overlay (последняя выписка как база + overlay-документы).
  • §3.4 `apply_effect()` — обработка единичного effect dict.
  • §7.2 `founder_chain_has_pledge(enterprise_key, beneficiaries,
    exclude_pledge_holders)` — BFS до корня с защитой от циклов.
  • `collect_pledge_holders(beneficiaries, cadastre_objects)` — собрать
    ИНН залогодержателей (объект + доля) для exclude_set.
"""
from __future__ import annotations

import copy
import re
from collections import deque
from datetime import date

from .documents_schema import EXTRACT_KINDS, parse_date

_TARGET_RE = re.compile(r"^([a-z_]+)\[([a-z_]+)=([^\]]+)\]\.([a-z_]+)$")


def _resolve_target(state: dict, target: str) -> tuple[list, dict | None]:
    """`cadastre_objects[id=cad_X].restrictions` → (list, parent_record).

    Возвращает (поле, родитель) или (None, None) если не найдено.
    """
    m = _TARGET_RE.match(target)
    if not m:
        return None, None
    collection_key, match_key, match_val, field = m.groups()
    coll = state.get(collection_key)
    if not isinstance(coll, list):
        return None, None
    rec = next((r for r in coll if isinstance(r, dict) and str(r.get(match_key)) == match_val), None)
    if rec is None:
        return None, None
    if field not in rec or rec[field] is None:
        rec[field] = []
    return rec[field], rec


def apply_effect(state: dict, eff: dict, *, source_doc_id: str | None = None) -> None:
    """In-place применение единичного effect к state (§3.4)."""
    op = eff["op"]
    target = eff["target"]
    payload = eff.get("payload") or {}
    field, parent = _resolve_target(state, target)
    if field is None:
        return  # target не существует — silently skip (fail-safe)

    if op == "add":
        # add: payload — новая запись (dict с произвольными полями)
        entry = dict(payload)
        if source_doc_id:
            entry["_source_doc_id"] = source_doc_id
        field.append(entry)
    elif op == "remove":
        # remove: payload — критерий по полям; удаляем все совпадающие
        criteria = payload
        field[:] = [r for r in field
                    if not (isinstance(r, dict)
                            and all(r.get(k) == v for k, v in criteria.items()))]
    elif op == "change":
        # change: payload = {"match":{...}, "set":{...}}
        match = payload.get("match") or {}
        new_vals = payload.get("set") or {}
        for r in field:
            if isinstance(r, dict) and all(r.get(k) == v for k, v in match.items()):
                r.update(new_vals)
                if source_doc_id:
                    r["_source_doc_id"] = source_doc_id


def resolve_state(structure: dict, documents: list[dict], target_date: date) -> dict:
    """Snapshot-overlay алгоритм (§3.3).

    База: последняя выписка с doc_date ≤ target_date.
    Overlay: все non-extract документы с doc_date ∈ (extract_date, target_date].
    """
    state = copy.deepcopy(structure)
    extracts = [d for d in documents
                if d["kind"] in EXTRACT_KINDS
                and parse_date(d["doc_date"]) <= target_date]
    if not extracts:
        return state  # fallback: structure as-is
    latest_extract = max(extracts, key=lambda d: parse_date(d["doc_date"]))
    extract_date_value = parse_date(latest_extract["doc_date"])

    overlays = [d for d in documents
                if d["kind"] not in EXTRACT_KINDS
                and extract_date_value < parse_date(d["doc_date"]) <= target_date]
    overlays.sort(key=lambda d: (d["doc_date"],
                                 d.get("registered_at", ""),
                                 d["doc_id"]))

    for doc in overlays:
        for eff in doc.get("effects") or []:
            apply_effect(state, eff, source_doc_id=doc["doc_id"])
    return state


# ─── Founder-chain pledge propagation (§7.2) ────────────────────────────────


def founder_chain_has_pledge(
    enterprise_key: str,
    beneficiaries: dict,
    exclude_pledge_holders: set[str] | None = None,
) -> tuple[bool, list[str]]:
    """BFS вверх от enterprise до корня через `Бенефициар (ключ)` parent-pointer.

    Возвращает (есть_ли_залог, путь_до_первого_залогодателя).
    `exclude_pledge_holders` — keys бенефициаров-залогодержателей,
    исключаются из обхода (по требованию пользователя).
    """
    exclude = exclude_pledge_holders or set()
    visited: set[str] = set()
    queue: deque[tuple[str, list[str]]] = deque([(enterprise_key, [enterprise_key])])

    while queue:
        cur, path = queue.popleft()
        if cur in visited or cur in exclude:
            continue
        visited.add(cur)

        ben = beneficiaries.get(cur)
        if not isinstance(ben, dict):
            continue

        # Пометка has_pledge или непустые "Обременения доли" → залог
        attrs = ben.get("attrs") if isinstance(ben.get("attrs"), dict) else {}
        if (ben.get("has_pledge") or attrs.get("has_pledge")
                or ben.get("Обременения доли")
                or attrs.get("Обременения доли")):
            return True, path

        parent_key = (ben.get("Бенефициар (ключ)")
                      or attrs.get("Бенефициар (ключ)"))
        if parent_key and parent_key not in visited:
            queue.append((parent_key, path + [parent_key]))

    return False, []


def collect_pledge_holders(
    beneficiaries: dict,
    cadastre_objects: list[dict] | None = None,
) -> set[str]:
    """Собрать ключи бенефициаров-залогодержателей.

    Источники:
      • `beneficiaries[*]["Обременения доли"][*]["Сведения о залогодержателе"]["ИНН"]`
      • `cadastre_objects[*].restrictions[*].beneficiary_inn`
    Сопоставление ИНН → ben_key через `beneficiaries[*].attrs.ИНН` (или
    top-level). Если ИНН залогодержателя не находится в `beneficiaries` —
    он не попадает в exclude_set (не его ключа в графе нет).
    """
    holder_inns: set[str] = set()

    for ben in (beneficiaries or {}).values():
        if not isinstance(ben, dict):
            continue
        for pl in ben.get("Обременения доли") or []:
            if not isinstance(pl, dict):
                continue
            hldr = pl.get("Сведения о залогодержателе") or {}
            inn = hldr.get("ИНН")
            if inn:
                holder_inns.add(str(inn))

    for cad in cadastre_objects or []:
        for r in (cad or {}).get("restrictions") or []:
            inn = (r or {}).get("beneficiary_inn")
            if inn:
                holder_inns.add(str(inn))

    inn_to_key: dict[str, str] = {}
    for k, ben in (beneficiaries or {}).items():
        if not isinstance(ben, dict):
            continue
        attrs = ben.get("attrs") if isinstance(ben.get("attrs"), dict) else {}
        inn = ben.get("ИНН") or attrs.get("ИНН")
        if inn:
            inn_to_key[str(inn)] = k

    return {inn_to_key[i] for i in holder_inns if i in inn_to_key}
