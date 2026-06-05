"""Генератор ДЕМО Block-2 БД — для проверки конвейера C2 без запуска парсера.

Создаёт маленькую SQLite в формате egrn_parser/db/schema.sql (нужное подмножество)
с парой объектов, правами и корпоративной цепочкой. Затем её можно скормить
import_block2 и graph_emit как настоящую БД парсера.

    python -m contracts.db.make_demo_block2 demo_block2.db
"""
import os
import sqlite3
import sys

_DDL = """
CREATE TABLE land_objects(cad_number TEXT PRIMARY KEY, name TEXT, address TEXT, area REAL, land_category TEXT, lifecycle_status TEXT DEFAULT 'active');
CREATE TABLE building_objects(cad_number TEXT PRIMARY KEY, object_type TEXT, name TEXT, address TEXT, area REAL, purpose TEXT, floors_above_ground INT, floors_total INT, parent_cad_number TEXT, lifecycle_status TEXT DEFAULT 'active');
CREATE TABLE accessories(accessory_id INTEGER PRIMARY KEY, item_name TEXT, re_cad_number TEXT, lat REAL, lon REAL, is_disposed INT DEFAULT 0);
CREATE TABLE object_geometries(geom_id INTEGER PRIMARY KEY, object_class TEXT, cad_number TEXT, geom_type TEXT, geom_source TEXT, geom_geojson TEXT, geom_wkt TEXT, crs TEXT DEFAULT 'EPSG:4326', is_current INT DEFAULT 1);
CREATE TABLE entity_registry(entity_id INTEGER PRIMARY KEY, inn TEXT, ogrn TEXT, entity_type TEXT, name_full TEXT, kpp TEXT);
CREATE TABLE right_holders(holder_id INTEGER PRIMARY KEY, right_id INT, holder_type TEXT, name TEXT, inn TEXT);
CREATE TABLE rights(right_id INTEGER PRIMARY KEY, object_class TEXT, object_key_type TEXT, object_key_value TEXT, right_category TEXT, right_type TEXT, right_type_code TEXT, right_number TEXT, right_date TEXT, is_active INT DEFAULT 1);
CREATE TABLE ownership_chain(chain_id INTEGER PRIMARY KEY, child_entity_id INT, parent_entity_id INT, share_pct REAL, source TEXT, is_active INT DEFAULT 1);
"""


def build(path: str) -> None:
    b = sqlite3.connect(path)
    b.executescript(_DDL)
    b.execute("INSERT INTO land_objects VALUES('61:44:0040713:100','ЗУ 100','Ростов, Суворова 52',1200.5,'земли поселений','active')")
    b.execute("INSERT INTO building_objects VALUES('61:44:0040713:200','building','Склад','Ростов, Суворова 52',800.0,'нежилое',2,2,'61:44:0040713:100','active')")
    b.execute("INSERT INTO building_objects VALUES('61:44:0040713:446','room','Помещение 8','Ростов, Суворова 52',54.0,'нежилое',NULL,NULL,'61:44:0040713:200','active')")
    b.execute("INSERT INTO accessories VALUES(1,'Весовая будка','61:44:0040713:200',47.2226,39.7188,0)")
    b.execute("INSERT INTO object_geometries VALUES(1,'land','61:44:0040713:100','POLYGON','egrn','{}','POLYGON((39.71 47.22,39.72 47.22,39.72 47.23,39.71 47.22))','EPSG:4326',1)")
    b.execute("INSERT INTO entity_registry VALUES(10,'6164000001','1116100000001','legal_entity','ООО Лебеди','616401001')")
    b.execute("INSERT INTO entity_registry VALUES(11,'6164000002','1116100000002','legal_entity','ООО Холдинг',NULL)")
    b.execute("INSERT INTO rights VALUES(1,'building','cad_number','61:44:0040713:200','right','Собственность','ownership','61-61/001','2020-01-15',1)")
    b.execute("INSERT INTO right_holders VALUES(1,1,'legal','ООО Лебеди','6164000001')")
    b.execute("INSERT INTO rights VALUES(2,'land','cad_number','61:44:0040713:100','right','Аренда','lease','61-61/002','2021-03-10',1)")
    b.execute("INSERT INTO right_holders VALUES(2,2,'legal','ООО Лебеди','6164000001')")
    b.execute("INSERT INTO ownership_chain VALUES(1,10,11,75.0,'checko',1)")
    b.commit(); b.close()
    print(f"демо Block-2 БД создана: {path}")


def main() -> None:
    args = [a for a in sys.argv[1:] if a != "--force"]
    force = "--force" in sys.argv
    out = args[0] if args else "demo_block2.db"

    if os.path.exists(out):
        if force:
            os.remove(out)
        elif not sys.stdin.isatty():
            sys.exit(f"БД {out} уже существует. Удалите её или запустите с --force.")
        else:
            ans = input(f"БД {out} уже существует. Удалить и создать заново? [y/N]: ").strip().lower()
            if ans in ("y", "yes", "д", "да"):
                os.remove(out)
            else:
                print("Оставлено без изменений.")
                return
    build(out)


if __name__ == "__main__":
    main()
