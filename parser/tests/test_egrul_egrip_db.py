"""
tests/test_egrul_egrip_db.py — запись subject ЕГРЮЛ/ЕГРИП в entity_registry.
Проверяет идемпотентность upsert и COALESCE (NULL не затирает имеющееся).
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from egrn_parser.parsers import egrul_egrip_db as DB  # noqa: E402

# Минимальная entity_registry, совместимая с egrn_parser/db/schema.sql
_DDL = """
CREATE TABLE entity_registry (
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


@pytest.fixture
def conn():
    c = sqlite3.connect(":memory:")
    c.executescript(_DDL)
    yield c
    c.close()


def _rec(**subject):
    base = {"kind": "org", "inn": "7707083893", "ogrn": "1027700132195",
            "name_full": "ООО ПРИМЕР", "kpp": "770701001"}
    base.update(subject)
    return {"registry": "ЕГРЮЛ", "subject": base}


def test_insert_then_idempotent_update(conn):
    r1 = DB.upsert_subject(conn, _rec(okved_main={"code": "62.01", "name": "ПО"}))
    assert r1 == {"action": "inserted", "inn": "7707083893"}
    row = conn.execute("SELECT entity_type, name_full, kpp, okved_main, egrul_enriched_at "
                       "FROM entity_registry WHERE inn=?", ("7707083893",)).fetchone()
    assert row[0] == "legal_entity" and row[1] == "ООО ПРИМЕР" and row[2] == "770701001"
    assert '"code": "62.01"' in row[3] and row[4] is not None

    # повторная запись того же ИНН — update, без дублей
    r2 = DB.upsert_subject(conn, _rec())
    assert r2["action"] == "updated"
    assert conn.execute("SELECT COUNT(*) FROM entity_registry").fetchone()[0] == 1


def test_coalesce_does_not_wipe_existing(conn):
    DB.upsert_subject(conn, _rec(name_short="ООО ПРИМЕР"))
    # второй источник без name_short — не должен обнулить имеющееся
    DB.upsert_subject(conn, _rec(name_short=None))
    short = conn.execute("SELECT name_short FROM entity_registry WHERE inn=?",
                         ("7707083893",)).fetchone()[0]
    assert short == "ООО ПРИМЕР"


def test_value_refreshes_when_present(conn):
    DB.upsert_subject(conn, _rec(egrul_status=None, status=None))
    DB.upsert_subject(conn, _rec(status={"name": "Действует"}))
    st = conn.execute("SELECT egrul_status FROM entity_registry WHERE inn=?",
                      ("7707083893",)).fetchone()[0]
    assert st == "Действует"


def test_ip_entity_type_individual(conn):
    rec = {"registry": "ЕГРИП", "subject": {"kind": "person", "inn": "770700000001",
           "ogrnip": "304770000000001", "name_full": None}}
    DB.upsert_subject(conn, rec)
    et = conn.execute("SELECT entity_type, ogrn FROM entity_registry WHERE inn=?",
                      ("770700000001",)).fetchone()
    assert et[0] == "individual" and et[1] == "304770000000001"  # ogrnip → ogrn


def test_no_inn_skipped(conn):
    res = DB.upsert_subject(conn, {"registry": "ЕГРЮЛ", "subject": {"kind": "org"}})
    assert res["action"] == "skipped"
    assert conn.execute("SELECT COUNT(*) FROM entity_registry").fetchone()[0] == 0


def test_terminated_status_text(conn):
    DB.upsert_subject(conn, _rec(status={"terminated": True, "method": "реорганизация"}))
    st = conn.execute("SELECT egrul_status FROM entity_registry WHERE inn=?",
                      ("7707083893",)).fetchone()[0]
    assert "реорганизация" in st


def test_auto_creates_table_on_fresh_db():
    """Пустая БД (как свежий ekcelo.sqlite) — таблица создаётся автоматически."""
    c = sqlite3.connect(":memory:")
    res = DB.upsert_subject(c, _rec(okved_main={"code": "62.01", "name": "ПО"}))
    assert res["action"] == "inserted"
    row = c.execute("SELECT name_full, okved_main FROM entity_registry WHERE inn=?",
                    ("7707083893",)).fetchone()
    assert row[0] == "ООО ПРИМЕР" and '"code": "62.01"' in row[1]
    c.close()


def _rec_with_founders():
    return {"registry": "ЕГРЮЛ", "subject": {
                "kind": "org", "inn": "7707083893", "ogrn": "1027700132195",
                "name_full": "ООО ПРИМЕР"},
            "source": {"system": "checko"},
            "founders": [
                {"kind": "legal", "inn": "7700000000", "ogrn": "1037700000000",
                 "name": "ООО МАТЕРИНСКАЯ", "share_percent": 100},
                {"kind": "person", "inn": "771100000000",
                 "fio": {"last": "ПЕТРОВ"}, "share_percent": 0},
                {"kind": "legal", "name": "БЕЗ ИНН"},  # без ИНН → skip ребра
            ]}


def test_ownership_edges_inserted(conn):
    res = DB.upsert_records(conn, [_rec_with_founders()])
    edges = res[0]["ownership"]
    inserted = [e for e in edges if e["action"] == "inserted_edge"]
    assert len(inserted) == 2                       # 2 учредителя с ИНН
    assert any(e["reason"] == "учредитель без ИНН" for e in edges if "reason" in e)
    rows = conn.execute(
        """SELECT ce.inn, pe.inn, oc.share_pct, oc.source
           FROM ownership_chain oc
           JOIN entity_registry ce ON ce.entity_id = oc.child_entity_id
           JOIN entity_registry pe ON pe.entity_id = oc.parent_entity_id""").fetchall()
    assert ("7707083893", "7700000000", 100.0, "checko") in rows
    assert ("7707083893", "771100000000", 0.0, "checko") in rows


def test_ownership_idempotent(conn):
    DB.upsert_records(conn, [_rec_with_founders()])
    res2 = DB.upsert_records(conn, [_rec_with_founders()])
    assert all(e["action"] == "updated_edge"
               for e in res2[0]["ownership"]
               if e["action"] in ("inserted_edge", "updated_edge"))
    assert conn.execute("SELECT COUNT(*) FROM ownership_chain").fetchone()[0] == 2


def _rec_with_relations():
    return {"registry": "ЕГРЮЛ", "subject": {
                "kind": "org", "inn": "2312122992", "name_full": "ООО АНТАРЕС"},
            "source": {"system": "ФНС-ЕГРЮЛ-PDF"},
            "directors": [{"fio": {"last": "Оборин", "first": "Алексей",
                                   "middle": "Анатольевич"},
                           "inn": "772918490807", "post": "ДИРЕКТОР"}],
            "managing_orgs": [{"inn": "2314017030", "ogrn": "1032308528042",
                               "name": "ООО АГРОКОМПЛЕКС"}],
            "successors": [{"inn": "2334001455", "ogrn": "1022303978080",
                            "name": "АО ПОБЕДА"}],
            "predecessors": []}


def test_relations_edges_by_type(conn):
    res = DB.upsert_records(conn, [_rec_with_relations()])
    rels = res[0]["relations"]
    types = {e["type"] for e in rels if e["action"] == "inserted_edge"}
    assert types == {"director", "managing_org", "successor"}
    rows = conn.execute(
        """SELECT se.inn, te.inn, er.relation_type, er.post, er.source
           FROM entity_relations er
           JOIN entity_registry se ON se.entity_id = er.source_entity_id
           JOIN entity_registry te ON te.entity_id = er.target_entity_id
           ORDER BY er.relation_type""").fetchall()
    assert ("2312122992", "772918490807", "director", "ДИРЕКТОР", "ФНС-ЕГРЮЛ-PDF") in rows
    assert ("2312122992", "2334001455", "successor", None, "ФНС-ЕГРЮЛ-PDF") in rows


def test_relations_idempotent(conn):
    DB.upsert_records(conn, [_rec_with_relations()])
    DB.upsert_records(conn, [_rec_with_relations()])
    assert conn.execute("SELECT COUNT(*) FROM entity_relations").fetchone()[0] == 3


def test_relations_target_without_inn_skipped(conn):
    rec = {"registry": "ЕГРЮЛ", "subject": {"kind": "org", "inn": "2312122992",
           "name_full": "ООО АНТАРЕС"}, "source": {"system": "checko"},
           "directors": [{"fio": {"last": "Безынн"}, "post": "ДИРЕКТОР"}]}
    res = DB.upsert_records(conn, [rec])
    assert any(e.get("reason") == "цель без ИНН" for e in res[0]["relations"])


def test_relations_skipped_on_root_schema():
    c = sqlite3.connect(":memory:")
    c.executescript("CREATE TABLE entity_registry(inn TEXT PRIMARY KEY, name_full TEXT, "
                    "name_short TEXT, ogrn TEXT, entity_type TEXT, updated_at TEXT);")
    res = DB.upsert_records(c, [_rec_with_relations()])
    assert res[0]["relations"][0]["action"] == "skipped_graph"
    c.close()


def test_ownership_skipped_on_root_schema():
    c = sqlite3.connect(":memory:")
    c.executescript("CREATE TABLE entity_registry(inn TEXT PRIMARY KEY, name_full TEXT, "
                    "name_short TEXT, ogrn TEXT, entity_type TEXT, updated_at TEXT);")
    res = DB.upsert_records(c, [_rec_with_founders()])
    assert res[0]["ownership"][0]["action"] == "skipped_graph"
    c.close()


def test_compatible_with_root_schema_without_egrul_columns():
    """Корневая schema/egrn_current_schema.sql: только базовые колонки — пишем их."""
    c = sqlite3.connect(":memory:")
    c.executescript("CREATE TABLE entity_registry(inn TEXT PRIMARY KEY, name_full TEXT, "
                    "name_short TEXT, ogrn TEXT, entity_type TEXT, updated_at TEXT);")
    res = DB.upsert_subject(c, _rec(okved_main={"code": "62.01", "name": "ПО"}))
    assert res["action"] == "inserted"
    row = c.execute("SELECT inn, ogrn, entity_type FROM entity_registry").fetchone()
    assert row == ("7707083893", "1027700132195", "legal_entity")
    c.close()
