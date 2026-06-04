"""Замок единого граф-эмиттера: импорт synthetic Block-2 → emit_graph → проверка,
что узлы/рёбра/confidence выведены из табличной модели (C1 graph_node_id, C4 edges)."""
import sqlite3

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from contracts.db.models import Base
import contracts.db.models_egrn  # noqa: F401
from contracts.db.import_block2 import import_block2
from contracts.db.graph_emit import emit_graph
from contracts.db.tests.test_import_block2 import _BLOCK2_DDL  # переиспуем DDL


@pytest.fixture()
def block2_db(tmp_path):
    p = tmp_path / "b2.db"
    b = sqlite3.connect(p)
    b.executescript(_BLOCK2_DDL)
    b.execute("INSERT INTO land_objects VALUES('61:44:0040713:100','ЗУ','адр',1200.5,'пос','active')")
    b.execute("INSERT INTO building_objects VALUES('61:44:0040713:200','building','Склад','адр',800.0,'нежилое',2,2,'61:44:0040713:100','active')")
    b.execute("INSERT INTO accessories VALUES(1,'Весовая','61:44:0040713:200',47.22,39.71,0)")
    b.execute("INSERT INTO entity_registry VALUES(10,'6164000001','1','legal_entity','ООО Лебеди','616401001')")
    b.execute("INSERT INTO entity_registry VALUES(11,'6164000002','2','legal_entity','ООО Холдинг',NULL)")
    b.execute("INSERT INTO rights VALUES(1,'building','cad_number','61:44:0040713:200','right','Собственность','ownership','61/1','2020-01-15',1)")
    b.execute("INSERT INTO right_holders VALUES(1,1,'legal','ООО Лебеди','6164000001')")
    b.execute("INSERT INTO ownership_chain VALUES(1,10,11,75.0,'checko',1)")
    b.commit(); b.close()
    return str(p)


def test_emit_graph(block2_db):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        import_block2(block2_db, s)
        g = emit_graph(s)

    assert g["schemaVersion"].startswith("graph.json/2.0")
    # узлы: 2 объекта + 1 accessory + 2 субъекта = 5
    assert g["metadata"]["nodeCount"] == 5
    assert g["metadata"]["nodesByKind"]["accessory"] == 1

    # graph_node_id формат C1
    ids = {n["id"] for n in g["nodes"]}
    assert "land:61:44:0040713:100" in ids
    assert "subj:6164000001" in ids

    # рёбра выведены из relations с confidence
    by_kind = {e["kind"] for e in g["edges"]}
    assert {"owns", "contains", "controls"} <= by_kind
    owns = next(e for e in g["edges"] if e["kind"] == "owns")
    assert owns["source"] == "subj:6164000001"
    assert owns["confidence"] == 1.0      # ЕГРН
    ctrl = next(e for e in g["edges"] if e["kind"] == "controls")
    assert ctrl["confidence"] == 0.4      # checko→LLM
