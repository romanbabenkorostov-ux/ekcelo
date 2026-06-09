"""
egrn_parser/parsers/egrul_egrip_db.py — запись нормализованной записи
ЕГРЮЛ/ЕГРИП в существующую таблицу `entity_registry`.

Пишется ТОЛЬКО `subject` (идентификация субъекта) — таблица `entity_registry`
(`egrn_parser/db/schema.sql`) под это и спроектирована: `inn UNIQUE`, `ogrn`,
`entity_type`, `name_full/short`, `egrul_status`, `reg_date`, `kpp`,
`okved_main`, `egrul_enriched_at`.

Учредители пишутся в граф владения `ownership_chain` (учредитель → parent,
субъект → child, доля % → share_pct; см. `upsert_ownership`). Прочие связи
(руководитель, управляющая организация, право-предшественник/преемник) —
в `entity_relations` (source = субъект, target = связанное лицо/орг,
`relation_type`; см. `upsert_relations`), чтобы не смешивать с долями владения.

Идемпотентность: upsert по `inn` (`ON CONFLICT(inn) DO UPDATE`), значения
обновляются через `COALESCE(excluded, existing)` — непустое из выписки
актуализирует, NULL не затирает имеющееся.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from typing import Any, Optional

log = logging.getLogger(__name__)

# registry/kind → entity_registry.entity_type
#   ('individual' | 'legal_entity' | 'public_entity')
_ENTITY_TYPE = {"ЕГРЮЛ": "legal_entity", "ЕГРИП": "individual"}

# DDL для авто-создания, если таблицы нет (совместимо с egrn_parser/db/schema.sql:
# богатый вариант с ЕГРЮЛ-полями). На уже существующую таблицу НЕ влияет.
_ENSURE_DDL = """
CREATE TABLE IF NOT EXISTS entity_registry (
    entity_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    inn          TEXT,
    ogrn         TEXT,
    entity_type  TEXT NOT NULL,
    name_full    TEXT,
    name_short   TEXT,
    egrul_status TEXT,
    reg_date     TEXT,
    kpp          TEXT,
    okved_main   TEXT,
    egrul_enriched_at TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at   TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(inn)
);
"""

# Колонки, которые мы умеем заполнять (помимо inn). Реально пишутся только те,
# что есть в таблице (интроспекция) — чтобы работать и с корневой схемой
# (schema/egrn_current_schema.sql), где ЕГРЮЛ-полей нет.
_OPTIONAL_COLS = (
    "ogrn", "entity_type", "name_full", "name_short",
    "egrul_status", "reg_date", "kpp", "okved_main",
)


def ensure_table(conn: sqlite3.Connection) -> None:
    """Создать entity_registry, если её ещё нет (на существующую — no-op)."""
    conn.executescript(_ENSURE_DDL)


# Граф владения (egrn_parser/db/schema.sql::ownership_chain). Авто-создаём на
# свежей БД; на существующую — no-op. FK на entity_registry(entity_id).
_ENSURE_OWNERSHIP_DDL = """
CREATE TABLE IF NOT EXISTS ownership_chain (
    chain_id          INTEGER PRIMARY KEY AUTOINCREMENT,
    child_entity_id   INTEGER NOT NULL REFERENCES entity_registry(entity_id),
    parent_entity_id  INTEGER NOT NULL REFERENCES entity_registry(entity_id),
    share_pct         REAL,
    source            TEXT NOT NULL,
    source_date       TEXT,
    notes             TEXT,
    is_active         INTEGER NOT NULL DEFAULT 1,
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(child_entity_id, parent_entity_id)
);
"""

# Прочие (не-владельческие) направленные связи субъекта: руководитель,
# управляющая организация, право-предшественник/преемник. Отдельно от
# ownership_chain, чтобы не ломать его контракт (там — только доли владения).
_ENSURE_RELATIONS_DDL = """
CREATE TABLE IF NOT EXISTS entity_relations (
    rel_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    source_entity_id  INTEGER NOT NULL REFERENCES entity_registry(entity_id),
    target_entity_id  INTEGER NOT NULL REFERENCES entity_registry(entity_id),
    relation_type     TEXT NOT NULL,   -- director|managing_org|predecessor|successor
    post              TEXT,            -- должность (для director)
    source            TEXT NOT NULL,
    source_date       TEXT,
    is_active         INTEGER NOT NULL DEFAULT 1,
    created_at        TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(source_entity_id, target_entity_id, relation_type)
);
"""


def _table_columns(conn: sqlite3.Connection) -> set[str]:
    return {r[1] for r in conn.execute("PRAGMA table_info(entity_registry)")}


def _entity_id_by_inn(conn: sqlite3.Connection, inn: str) -> Optional[int]:
    row = conn.execute(
        "SELECT entity_id FROM entity_registry WHERE inn = ?", (inn,)).fetchone()
    return row[0] if row else None


def _write_entity(conn: sqlite3.Connection, values: dict[str, Any]) -> str:
    """Записать identity в entity_registry по существующим колонкам (идемпотентно).

    `values` — словарь с `inn` + любым подмножеством `_OPTIONAL_COLS`; недостающие
    трактуются как None (COALESCE не затирает). Возвращает 'inserted'|'updated'.
    """
    ensure_table(conn)
    inn = values["inn"]
    available = _table_columns(conn)
    full = {c: values.get(c) for c in ("inn", *_OPTIONAL_COLS)}
    cols = ["inn"] + [c for c in _OPTIONAL_COLS if c in available]
    params = {c: full[c] for c in cols}

    insert_cols = list(cols)
    insert_ph = [f":{c}" for c in cols]
    now_cols = [c for c in ("egrul_enriched_at", "updated_at") if c in available]
    insert_cols += now_cols
    insert_ph += ["datetime('now')"] * len(now_cols)

    set_parts = []
    for c in cols:
        if c == "inn":
            continue
        if c == "entity_type":
            set_parts.append(f"{c} = excluded.{c}")
        else:
            set_parts.append(f"{c} = COALESCE(excluded.{c}, entity_registry.{c})")
    set_parts += [f"{c} = datetime('now')" for c in now_cols]

    existed = conn.execute(
        "SELECT 1 FROM entity_registry WHERE inn = ?", (inn,)).fetchone() is not None
    conn.execute(
        f"""INSERT INTO entity_registry ({', '.join(insert_cols)})
            VALUES ({', '.join(insert_ph)})
            ON CONFLICT(inn) DO UPDATE SET {', '.join(set_parts)}""",
        params,
    )
    return "updated" if existed else "inserted"


def _entity_type(rec: dict[str, Any]) -> str:
    kind = (rec.get("subject") or {}).get("kind")
    if kind == "person":
        return "individual"
    if kind == "org":
        return "legal_entity"
    return _ENTITY_TYPE.get(rec.get("registry"), "legal_entity")


def _status_text(subject: dict[str, Any]) -> Optional[str]:
    st = subject.get("status") or {}
    if not st:
        return None
    if st.get("name"):
        return st["name"]
    if st.get("terminated"):
        return "Прекращено" + (f": {st['method']}" if st.get("method") else "")
    return None


def upsert_subject(conn: sqlite3.Connection, record: dict[str, Any]) -> dict[str, Any]:
    """Записать `subject` нормализованной записи в `entity_registry` (идемпотентно).

    Создаёт таблицу при отсутствии. Пишет только те колонки, что реально есть
    в таблице (совместимо и с корневой, и с пакетной схемой). Возвращает
    {action: 'inserted'|'updated'|'skipped', inn, reason?}. Без ИНН — skip.
    """
    subject = record.get("subject") or {}
    inn = subject.get("inn")
    if not inn:
        return {"action": "skipped", "inn": None, "reason": "нет ИНН (ключ entity_registry)"}
    okved = subject.get("okved_main")
    action = _write_entity(conn, {
        "inn": inn,
        "ogrn": subject.get("ogrn") or subject.get("ogrnip"),
        "entity_type": _entity_type(record),
        "name_full": subject.get("name_full"),
        "name_short": subject.get("name_short"),
        "egrul_status": _status_text(subject),
        "reg_date": subject.get("reg_date"),
        "kpp": subject.get("kpp"),
        "okved_main": json.dumps(okved, ensure_ascii=False) if okved else None,
    })
    return {"action": action, "inn": inn}


def upsert_ownership(conn: sqlite3.Connection, record: dict[str, Any]) -> list[dict[str, Any]]:
    """Записать рёбра владения (учредитель → субъект) в ownership_chain.

    Учредитель = parent, субъект записи = child, доля % = share_pct. Идемпотентно
    по UNIQUE(child, parent). Требует схему с `entity_id` (пакетная); на корневой
    схеме (без entity_id / без графа) — мягкий skip. Директора/управляющие сюда
    НЕ пишутся (это не владение).
    """
    if "entity_id" not in _table_columns(conn):
        return [{"action": "skipped_graph", "reason": "схема entity_registry без entity_id"}]
    subject = record.get("subject") or {}
    child_inn = subject.get("inn")
    if not child_inn:
        return [{"action": "skipped_graph", "reason": "нет ИНН субъекта"}]
    conn.executescript(_ENSURE_OWNERSHIP_DDL)
    child_id = _entity_id_by_inn(conn, child_inn)
    src = (record.get("source") or {}).get("system") or "fns"

    out: list[dict[str, Any]] = []
    for f in record.get("founders") or []:
        finn = f.get("inn")
        if not finn:
            out.append({"action": "skipped_edge", "reason": "учредитель без ИНН"})
            continue
        etype = "individual" if f.get("kind") == "person" else "legal_entity"
        _write_entity(conn, {"inn": finn, "ogrn": f.get("ogrn"),
                             "entity_type": etype, "name_full": f.get("name")})
        parent_id = _entity_id_by_inn(conn, finn)
        if parent_id is None or child_id is None or parent_id == child_id:
            continue
        existed = conn.execute(
            "SELECT 1 FROM ownership_chain WHERE child_entity_id=? AND parent_entity_id=?",
            (child_id, parent_id)).fetchone() is not None
        conn.execute(
            """INSERT INTO ownership_chain
                   (child_entity_id, parent_entity_id, share_pct, source, is_active, created_at)
               VALUES (?, ?, ?, ?, 1, datetime('now'))
               ON CONFLICT(child_entity_id, parent_entity_id) DO UPDATE SET
                   share_pct = COALESCE(excluded.share_pct, ownership_chain.share_pct),
                   source    = excluded.source,
                   is_active = 1""",
            (child_id, parent_id, f.get("share_percent"), src))
        out.append({"action": "updated_edge" if existed else "inserted_edge",
                    "parent": finn, "child": child_inn})
    return out


def _fio_name(fio: Optional[dict]) -> Optional[str]:
    if not fio:
        return None
    return " ".join(p for p in (fio.get("last"), fio.get("first"),
                                fio.get("middle")) if p) or None


def upsert_relations(conn: sqlite3.Connection, record: dict[str, Any]) -> list[dict[str, Any]]:
    """Записать не-владельческие связи субъекта в entity_relations.

    director / managing_org / predecessor / successor. Направление:
    source = субъект записи, target = связанное лицо/организация. Идемпотентно
    по UNIQUE(source, target, relation_type). Требует схему с `entity_id`;
    иначе — мягкий skip. Цель без ИНН пропускается.
    """
    if "entity_id" not in _table_columns(conn):
        return [{"action": "skipped_graph", "reason": "схема entity_registry без entity_id"}]
    subject = record.get("subject") or {}
    src_inn = subject.get("inn")
    if not src_inn:
        return [{"action": "skipped_graph", "reason": "нет ИНН субъекта"}]
    conn.executescript(_ENSURE_RELATIONS_DDL)
    source_id = _entity_id_by_inn(conn, src_inn)
    src = (record.get("source") or {}).get("system") or "fns"

    # (список связей, relation_type, как достать identity цели)
    plan = [
        (record.get("directors") or [], "director",
         lambda d: (d.get("inn"), "individual", _fio_name(d.get("fio")), None, d.get("post"))),
        (record.get("managing_orgs") or [], "managing_org",
         lambda d: (d.get("inn"), "legal_entity", d.get("name"), d.get("ogrn"), None)),
        (record.get("predecessors") or [], "predecessor",
         lambda d: (d.get("inn"), "legal_entity", d.get("name"), d.get("ogrn"), None)),
        (record.get("successors") or [], "successor",
         lambda d: (d.get("inn"), "legal_entity", d.get("name"), d.get("ogrn"), None)),
    ]
    out: list[dict[str, Any]] = []
    for items, rtype, extract in plan:
        for it in items:
            inn, etype, name, ogrn, post = extract(it)
            if not inn:
                out.append({"action": "skipped_edge", "type": rtype, "reason": "цель без ИНН"})
                continue
            _write_entity(conn, {"inn": inn, "ogrn": ogrn,
                                "entity_type": etype, "name_full": name})
            target_id = _entity_id_by_inn(conn, inn)
            if target_id is None or source_id is None or target_id == source_id:
                continue
            existed = conn.execute(
                "SELECT 1 FROM entity_relations WHERE source_entity_id=? AND "
                "target_entity_id=? AND relation_type=?",
                (source_id, target_id, rtype)).fetchone() is not None
            conn.execute(
                """INSERT INTO entity_relations
                       (source_entity_id, target_entity_id, relation_type, post,
                        source, is_active, created_at)
                   VALUES (?, ?, ?, ?, ?, 1, datetime('now'))
                   ON CONFLICT(source_entity_id, target_entity_id, relation_type)
                   DO UPDATE SET post = COALESCE(excluded.post, entity_relations.post),
                                 source = excluded.source, is_active = 1""",
                (source_id, target_id, rtype, post, src))
            out.append({"action": "updated_edge" if existed else "inserted_edge",
                        "type": rtype, "target": inn})
    return out


def upsert_records(conn: sqlite3.Connection, records: list[dict[str, Any]], *,
                   graph: bool = True) -> list[dict]:
    """Записать subject'ы (+ при graph=True рёбра владения и связи) и закоммитить раз."""
    results = []
    for r in records:
        res = upsert_subject(conn, r)
        if graph and res["action"] in ("inserted", "updated"):
            res["ownership"] = upsert_ownership(conn, r)
            res["relations"] = upsert_relations(conn, r)
        results.append(res)
    conn.commit()
    return results
