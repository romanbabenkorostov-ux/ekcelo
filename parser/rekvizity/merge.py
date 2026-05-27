# -*- coding: utf-8 -*-
"""Идемпотентный merge canonical-словарей реквизитов.

Принципы:
  • История источников (`_sources`) никогда не теряется и не схлопывается.
  • При конфликте по конкретному полю побеждает источник с более высоким
    приоритетом (см. canonical.SOURCE_PRIORITY); при равном приоритете —
    более свежий `_sources[].ts`.
  • Пустые значения (None / "" / [] / {}) НЕ затирают уже известное.

Используется store.py: каждый ingest сливает новый fragment в существующий
canonical (или создаёт новый, если ИНН встречается впервые).
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from . import canonical


def _is_empty(v: Any) -> bool:
    if v is None:
        return True
    if isinstance(v, str) and v.strip() == "":
        return True
    if isinstance(v, (list, dict)) and not v:
        return True
    return False


def _source_winner(
    a_sources: list[dict], b_sources: list[dict], field_owner_a: str, field_owner_b: str
) -> str:
    """Возвращает 'a' или 'b' — чей источник имеет приоритет.
    `field_owner_a/b` — type строки источника, давшего значение.
    """
    pa = canonical.source_score(field_owner_a)
    pb = canonical.source_score(field_owner_b)
    if pa != pb:
        return "a" if pa > pb else "b"
    # Равный приоритет — берём более свежий ts.
    ts_a = _last_ts_for_source(a_sources, field_owner_a)
    ts_b = _last_ts_for_source(b_sources, field_owner_b)
    return "a" if ts_a >= ts_b else "b"


def _last_ts_for_source(sources: list[dict], src_type: str) -> str:
    candidates = [s["ts"] for s in sources if s.get("type") == src_type and s.get("ts")]
    return max(candidates) if candidates else ""


def _track_field_owner(rek: dict[str, Any]) -> dict[str, str]:
    """Заглушка: связь «поле → источник» извлекается из `_sources[*].fields`
    если присутствует, иначе считаем что все поля = последний source.
    Для упрощения MVP — owner = последний source.type.
    """
    sources = rek.get("_sources") or []
    if not sources:
        return {}
    last = sources[-1].get("type", "")
    return {k: last for k in rek.keys() if not k.startswith("_")}


def merge(existing: dict[str, Any], fragment: dict[str, Any]) -> dict[str, Any]:
    """Сливает `fragment` в `existing` (не мутирует входы — возвращает новый dict).

    Если `existing` пуст / отсутствует — возвращает canonical-форму из
    fragment'а.
    """
    if not existing:
        merged = canonical.empty_canonical()
    else:
        merged = dict(existing)
        # Глубокая копия вложенных dict-ов.
        merged["bank"] = dict(existing.get("bank") or {})
        merged["signatory"] = dict(existing.get("signatory") or {})
        merged["_sources"] = list(existing.get("_sources") or [])
        merged["phones"] = list(existing.get("phones") or [])
        merged["emails"] = list(existing.get("emails") or [])

    # Schema version.
    merged["_schema_version"] = canonical.SCHEMA_VERSION

    # 1. Сначала добавляем источник во фрагменте к существующим (фактическая
    #    история ingest'а).
    frag_sources = fragment.get("_sources") or []
    fragment_owner = frag_sources[-1].get("type") if frag_sources else "unknown"

    # 2. Для скаляров: top-level + nested.
    for key in ("inn", "kpp", "ogrn", "ogrnip", "type", "name_full",
                "name_short", "address_legal", "address_actual", "site"):
        if key not in fragment:
            continue
        new_val = fragment.get(key)
        if _is_empty(new_val):
            continue
        cur_val = merged.get(key)
        if _is_empty(cur_val):
            merged[key] = new_val
            continue
        if cur_val == new_val:
            continue
        # Конфликт: решаем по приоритету.
        existing_owner = _last_owner_for_field(existing, key)
        if _source_winner(
            merged["_sources"], frag_sources, existing_owner, fragment_owner
        ) == "b":
            merged[key] = new_val

    # 3. Bank — поле за полем (источник на каждое поле может быть свой).
    frag_bank = fragment.get("bank") or {}
    for k in ("name", "bic", "ks", "rs"):
        new_val = frag_bank.get(k)
        if _is_empty(new_val):
            continue
        cur_val = merged["bank"].get(k)
        if _is_empty(cur_val):
            merged["bank"][k] = new_val
            continue
        if cur_val == new_val:
            continue
        existing_owner = _last_owner_for_field(existing, f"bank.{k}")
        if _source_winner(
            merged["_sources"], frag_sources, existing_owner, fragment_owner
        ) == "b":
            merged["bank"][k] = new_val

    # 4. Signatory — atomic (берём целиком от победителя).
    frag_sig = fragment.get("signatory") or {}
    if any(not _is_empty(v) for v in frag_sig.values()):
        cur_sig = merged.get("signatory") or {}
        if all(_is_empty(v) for v in cur_sig.values()):
            merged["signatory"] = dict(frag_sig)
        elif cur_sig != frag_sig:
            existing_owner = _last_owner_for_field(existing, "signatory")
            if _source_winner(
                merged["_sources"], frag_sources, existing_owner, fragment_owner
            ) == "b":
                merged["signatory"] = dict(frag_sig)

    # 5. Phones / emails — union (без дубликатов, сохраняя порядок).
    for key in ("phones", "emails"):
        new_list = fragment.get(key) or []
        for item in new_list:
            if item not in merged[key]:
                merged[key].append(item)

    # 6. Sources — append (история).
    for src in frag_sources:
        merged["_sources"].append(src)

    merged["_updated_at"] = datetime.now().isoformat(timespec="seconds")
    return merged


def _last_owner_for_field(rek: dict[str, Any] | None, field: str) -> str:
    """Заглушка: возвращаем тип последнего источника. Для precise tracking
    нужно вести `_field_owners`, но для MVP этого достаточно.
    """
    if not rek:
        return "unknown"
    sources = rek.get("_sources") or []
    return sources[-1].get("type", "unknown") if sources else "unknown"


def is_noop(existing: dict[str, Any], fragment: dict[str, Any]) -> bool:
    """True, если merge не изменит ни одного содержательного поля
    (источник уже был учтён ранее или не приносит новых значений).
    """
    if not existing:
        return False
    sources = existing.get("_sources") or []
    frag_sources = fragment.get("_sources") or []
    if not frag_sources:
        return True
    # Если фрагмент того же файла уже фигурирует в источниках — no-op.
    new_src = frag_sources[-1]
    new_file = new_src.get("file")
    if any(s.get("file") == new_file for s in sources):
        # Проверяем что значения не изменились.
        candidate = merge(existing, fragment)
        # Сравниваем без _sources / _updated_at (они всегда обновляются).
        a = {k: v for k, v in existing.items() if not k.startswith("_")}
        b = {k: v for k, v in candidate.items() if not k.startswith("_")}
        return a == b
    return False
