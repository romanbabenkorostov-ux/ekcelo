"""Замок импортёра Block-2 → C2. Строит синтетическую Block-2 БД, гоняет импорт
в свежую C2 (create_all), проверяет состав сущностей/рёбер/провенанса."""
import sqlite3

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from contracts.db.models import (
    Assertion, Base, Entity, EntityKind, Relation, RelationType,
)
import contracts.db.models_egrn  # noqa: F401 — регистрирует §1-§6
from contracts.db.models_egrn import Object
from contracts.db.import_block2 import import_block2

_BLOCK2_DDL = """
CREATE TABLE land_objects(cad_number TEXT PRIMARY KEY, name TEXT, address TEXT, area REAL, land_category TEXT, lifecycle_status TEXT DEFAULT 'active');
CREATE TABLE building_objects(cad_number TEXT PRIMARY KEY, object_type TEXT, name TEXT, address TEXT, area REAL, purpose TEXT, floors_above_ground INT, floors_total INT, parent_cad_number TEXT, lifecycle_status TEXT DEFAULT 'active');
CREATE TABLE accessories(accessory_id INTEGER PRIMARY KEY, item_name TEXT, re_cad_number TEXT, lat REAL, lon REAL, is_disposed INT DEFAULT 0);
CREATE TABLE object_geometries(geom_id INTEGER PRIMARY KEY, object_class TEXT, cad_number TEXT, geom_type TEXT, geom_source TEXT, geom_geojson TEXT, geom_wkt TEXT, crs TEXT DEFAULT 'EPSG:4326', is_current INT DEFAULT 1);
CREATE TABLE entity_registry(entity_id INTEGER PRIMARY KEY, inn TEXT, ogrn TEXT, entity_type TEXT, name_full TEXT, kpp TEXT);
CREATE TABLE right_holders(holder_id INTEGER PRIMARY KEY, right_id INT, holder_type TEXT, name TEXT, inn TEXT);
CREATE TABLE rights(right_id INTEGER PRIMARY KEY, object_class TEXT, object_key_type TEXT, object_key_value TEXT, right_category TEXT, right_type TEXT, right_type_code TEXT, right_number TEXT, right_date TEXT, is_active INT DEFAULT 1);
CREATE TABLE ownership_chain(chain_id INTEGER PRIMARY KEY, child_entity_id INT, parent_entity_id INT, share_pct REAL, source TEXT, is_active INT DEFAULT 1);
"""


@pytest.fixture()
def block2_db(tmp_path):
    p = tmp_path / "block2.db"
    b = sqlite3.connect(p)
    b.executescript(_BLOCK2_DDL)
    b.execute("INSERT INTO land_objects VALUES('61:44:0040713:100','ЗУ','Суворова 52',1200.5,'поселений','active')")
    b.execute("INSERT INTO building_objects VALUES('61:44:0040713:200','building','Склад','Суворова 52',800.0,'нежилое',2,2,'61:44:0040713:100','active')")
    b.execute("INSERT INTO building_objects VALUES('61:44:0040713:446','room','Пом.8','Суворова 52',54.0,'нежилое',NULL,NULL,'61:44:0040713:200','active')")
    b.execute("INSERT INTO accessories VALUES(1,'Весовая','61:44:0040713:200',47.22,39.71,0)")
    b.execute("INSERT INTO object_geometries VALUES(1,'land','61:44:0040713:100','POLYGON','egrn','{}','POLYGON((1 1,2 2,3 1,1 1))','EPSG:4326',1)")
    b.execute("INSERT INTO entity_registry VALUES(10,'6164000001','1','legal_entity','ООО Лебеди','616401001')")
    b.execute("INSERT INTO entity_registry VALUES(11,'6164000002','2','legal_entity','ООО Холдинг',NULL)")
    b.execute("INSERT INTO rights VALUES(1,'building','cad_number','61:44:0040713:200','right','Собственность','ownership','61-61/001','2020-01-15',1)")
    b.execute("INSERT INTO right_holders VALUES(1,1,'legal','ООО Лебеди','6164000001')")
    b.execute("INSERT INTO rights VALUES(2,'land','cad_number','61:44:0040713:100','right','Аренда','lease','61-61/002','2021-03-10',1)")
    b.execute("INSERT INTO right_holders VALUES(2,2,'legal','ООО Лебеди','6164000001')")
    b.execute("INSERT INTO ownership_chain VALUES(1,10,11,75.0,'checko',1)")
    b.commit(); b.close()
    return str(p)


def test_import_block2(block2_db):
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        counts = import_block2(block2_db, s)

        assert counts["objects"] == 3
        assert s.scalar(select(func.count()).select_from(Object)) == 3

        kinds = {k.value: c for k, c in
                 s.execute(select(Entity.kind, func.count()).group_by(Entity.kind))}
        assert kinds == {"land": 1, "building": 1, "room": 1,
                         "accessory": 1, "beneficiary_legal": 2}

        codes = {c: n for c, n in s.execute(
            select(RelationType.code, func.count()).select_from(Relation)
            .join(RelationType, Relation.relation_type_id == RelationType.id)
            .group_by(RelationType.code))}
        assert codes == {"OWNS": 1, "LEASES": 1, "CONTAINS": 1, "CONTROLS": 1}

        # провенанс: ЕГРН-права → confidence 1.0; checko-цепочка → 0.4 (LLM)
        confs = sorted({round(a.confidence_score, 3)
                        for a in s.scalars(select(Assertion))})
        assert confs == [0.4, 1.0]


def test_import_block2_idempotent(block2_db):
    """Повторный импорт не плодит дубли и не падает (UNIQUE)."""
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        import_block2(block2_db, s)
        ent1 = s.scalar(select(func.count()).select_from(Entity))
        rel1 = s.scalar(select(func.count()).select_from(Relation))
        counts2 = import_block2(block2_db, s)   # второй прогон
        assert counts2["entities"] == 0 and counts2["relations"] == 0
        assert s.scalar(select(func.count()).select_from(Entity)) == ent1
        assert s.scalar(select(func.count()).select_from(Relation)) == rel1
