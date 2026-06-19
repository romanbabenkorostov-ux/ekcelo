"""
egrn_parser/etp_merge.py — единый gap-fill merge ЭТП-слоя §6 (SPEC_parser item 5).

`object_etp_profile` (не-ЕГРН слой, ADR-001) наполняется из нескольких источников
(ОСВ/ручной ввод/NSPD/EXIF/LLM). Здесь — консолидированный приоритет-aware merge:

  Приоритет источников: manual > osv > nspd > exif > llm.
  Правило на поле: источник с приоритетом ≥ текущего ROW-источника МОЖЕТ
  перезаписывать значения; источник ниже — только заполняет пустоты (gap-fill,
  не затирает ручной ввод экономиста). Пустые входные значения игнорируются.

Глубокий merge по 6 JSON-колонкам (location_extra/building_extra/layout/legal_extra/
risks/extras). ROW source = max(существующий, входящий) по приоритету. Идемпотентно.

§6 при пересоздании БД из выписок НЕ восстанавливается → `etp_layer_present` помечает
наличие слоя для manifest (bundle_manifest).
"""
from __future__ import annotations

import json
import sqlite3
from typing import Any, Optional

# Приоритет источников (выше — авторитетнее). checko — field-level (в legal_extra),
# не ROW-источник (CHECK object_etp_profile.source = osv|exif|manual|nspd|llm).
SOURCE_PRIORITY = {"manual": 100, "osv": 90, "nspd": 50, "exif": 40, "llm": 30}

_JSON_COLUMNS = ("location_extra", "building_extra", "layout",
                 "legal_extra", "risks", "extras")


def _is_empty(v: Any) -> bool:
    return v is None or v == "" or v == [] or v == {}


def _priority(source: Optional[str]) -> int:
    return SOURCE_PRIORITY.get(source or "", -1)


def _load_json(s: Any) -> dict:
    if isinstance(s, dict):
        return s
    if isinstance(s, str) and s.strip():
        try:
            v = json.loads(s)
            return v if isinstance(v, dict) else {}
        except ValueError:
            return {}
    return {}


def deep_merge(existing: dict, incoming: dict, *, overwrite: bool) -> tuple[dict, int]:
    """Слить incoming в existing. Возвращает (результат, число заполненных/изменённых).

    Пустые входные значения пропускаются. `overwrite=False` — заполнять только
    пустые (gap-fill); `True` — входящий выигрывает конфликты (вложенно)."""
    out = dict(existing)
    changed = 0
    for k, v in (incoming or {}).items():
        if _is_empty(v):
            continue
        if k not in out or _is_empty(out[k]):
            out[k] = v
            changed += 1
        elif isinstance(out[k], dict) and isinstance(v, dict):
            out[k], sub = deep_merge(out[k], v, overwrite=overwrite)
            changed += sub
        elif overwrite and out[k] != v:
            out[k] = v
            changed += 1
    return out, changed


def _append_merge(existing: Any, incoming: Any) -> Any:
    """Аддитивное слияние (для exif advantages/notes): объединение без дублей,
    порядок сохраняется. Списки → union; строки → join по '; '; иначе — непустое."""
    if isinstance(existing, list) or isinstance(incoming, list):
        ex = existing if isinstance(existing, list) else ([existing] if not _is_empty(existing) else [])
        inc = incoming if isinstance(incoming, list) else ([incoming] if not _is_empty(incoming) else [])
        out = list(ex)
        for v in inc:
            if v not in out:
                out.append(v)
        return out
    if isinstance(existing, str) or isinstance(incoming, str):
        parts = [p.strip() for p in str(existing or "").split(";") if p.strip()]
        for p in [q.strip() for q in str(incoming or "").split(";") if q.strip()]:
            if p not in parts:
                parts.append(p)
        return "; ".join(parts)
    return incoming if _is_empty(existing) else existing


def merge_profile(conn: sqlite3.Connection, cad_number: str,
                  incoming: dict[str, Any], *, source: str,
                  confidence: float, strategy: str = "priority",
                  append_keys: Optional[dict[str, list[str]]] = None) -> dict[str, Any]:
    """Gap-fill merge входящего профиля в object_etp_profile[cad] (единая точка §6).

    `incoming` — подмножество JSON-колонок (location_extra/building_extra/layout/
    legal_extra/risks/extras), значения — dict. Идемпотентно.

    `strategy`:
      • 'priority' (по умолч.) — источник с приоритетом ≥ ROW перезаписывает поля,
        ниже — только заполняет пустоты (nspd/checko/llm безопасны над osv/manual);
      • 'gapfill' — никогда не перезаписывает существующие значения (чистый gap-fill).
    `append_keys` — {колонка: [ключи]} для аддитивного слияния (exif: advantages/
    notes) — объединение без дублей независимо от стратегии.
    """
    if source not in SOURCE_PRIORITY:
        raise ValueError(f"неизвестный source '{source}' (ожидается {sorted(SOURCE_PRIORITY)})")
    if strategy not in ("priority", "gapfill"):
        raise ValueError("strategy ∈ {'priority','gapfill'}")
    append_keys = append_keys or {}
    row = conn.execute(
        f"SELECT {', '.join(_JSON_COLUMNS)}, source, confidence "
        "FROM object_etp_profile WHERE cad_number=?", (cad_number,)).fetchone()

    existing_source = row[len(_JSON_COLUMNS)] if row else None
    overwrite = (strategy == "priority" and _priority(source) >= _priority(existing_source))

    merged: dict[str, Optional[str]] = {}
    total_changed = 0
    for i, col in enumerate(_JSON_COLUMNS):
        cur = _load_json(row[i]) if row else {}
        inc = _load_json(incoming.get(col))
        # аддитивные ключи — объединяем до deep_merge (комбинация, не gap-fill)
        for k in append_keys.get(col, []):
            if not _is_empty(inc.get(k)) or not _is_empty(cur.get(k)):
                combined = _append_merge(cur.get(k), inc.get(k))
                if combined != cur.get(k):
                    cur[k] = combined
                    total_changed += 1
                inc.pop(k, None)
        new, changed = deep_merge(cur, inc, overwrite=overwrite)
        total_changed += changed
        merged[col] = json.dumps(new, ensure_ascii=False) if new else None

    # ROW source/confidence — авторитетнейший из вкладчиков.
    if row and _priority(existing_source) > _priority(source):
        new_source, new_conf = existing_source, row[len(_JSON_COLUMNS) + 1]
    else:
        new_source, new_conf = source, confidence

    cols = list(_JSON_COLUMNS)
    if row:
        conn.execute(
            f"UPDATE object_etp_profile SET {', '.join(c+'=?' for c in cols)}, "
            "source=?, confidence=?, updated_at=datetime('now') WHERE cad_number=?",
            (*[merged[c] for c in cols], new_source, new_conf, cad_number))
    else:
        conn.execute(
            f"INSERT INTO object_etp_profile(cad_number, {', '.join(cols)}, source, confidence) "
            f"VALUES(?, {', '.join('?' for _ in cols)}, ?, ?)",
            (cad_number, *[merged[c] for c in cols], new_source, new_conf))
    conn.commit()
    return {"cad_number": cad_number, "row_source": new_source,
            "overwrite": overwrite, "fields_changed": total_changed,
            "created": row is None}


def etp_layer_present(conn: sqlite3.Connection) -> bool:
    """Есть ли §6 ЭТП-слой (для manifest.etp_layer_present, ADR-001)."""
    r = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='object_etp_profile'"
    ).fetchone()
    if not r:
        return False
    return conn.execute("SELECT 1 FROM object_etp_profile LIMIT 1").fetchone() is not None
