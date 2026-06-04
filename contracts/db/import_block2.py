"""Импорт Block-2 БД парсера (egrn_parser/db/schema.sql) → C2-схема.

Маппинг по PARSER_VOCAB_MAP §5:
    land_objects / building_objects → objects(§1) + entities(§7)
    accessories                     → entities(kind='accessory') + geometries(POINT) + CONTAINS
    object_geometries               → geometries (WKT/GeoJSON, crs→srid)
    entity_registry + right_holders → subjects(§10) + entity_registry(§2, compat) + subject_kpp
    rights                          → relations[legal] + legal_relation + assertions + evidences
    ownership_chain                 → relations[legal/corporate CONTROLS] + assertions + evidences

Источник читается сырым sqlite3 (read-only), цель пишется через ORM-Session.
v1 НЕ импортит: company_groups, business_units, valuations, object_events (TODO).

Запуск:
    EKCELO_DB_URL=sqlite:///c2.db python -m contracts.db.import_block2 path/to/block2.db
"""
import sqlite3
import sys
import uuid
from typing import Optional

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from contracts.db.models import (
    AccountingRelation, Assertion, DataSourceType, Entity, EntityKind, Evidence,
    Geometry, LegalRelation, Relation, RelationDomain, RelationType, Subject,
    SubjectKpp, SubjectType, SOURCE_WEIGHTS, confidence_from_evidences,
)
from contracts.db.models_egrn import EntityRegistry, Object
from contracts.db.relation_types_seed import RELATION_TYPES_SEED


# ── справочники маппинга ──────────────────────────────────────────────────────
_OBJTYPE_TO_KIND = {
    "land": EntityKind.land, "building": EntityKind.building, "room": EntityKind.room,
    "structure": EntityKind.structure, "parking": EntityKind.structure, "ons": EntityKind.ons,
}
_ENTITY_TYPE_TO_SUBJECT = {
    "individual": SubjectType.INDIVIDUAL, "legal_entity": SubjectType.LEGAL_ENTITY,
    "public_entity": SubjectType.STATE_BODY, "individual_entrepreneur": SubjectType.INDIVIDUAL_ENTREPRENEUR,
}
_CHAIN_SOURCE_TO_DS = {
    "court": DataSourceType.COURT_DECISION, "egrn": DataSourceType.EGRN,
    "osv": DataSourceType.OSV, "checko": DataSourceType.LLM, "egrul": DataSourceType.LLM,
}


def _rows(con: sqlite3.Connection, table: str) -> list[dict]:
    try:
        cur = con.execute(f"SELECT * FROM {table}")
    except sqlite3.OperationalError:
        return []
    cols = [d[0] for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def import_block2(src_db_path: str, session: Session) -> dict[str, int]:
    src = sqlite3.connect(f"file:{src_db_path}?mode=ro", uri=True)
    counts = {k: 0 for k in (
        "objects", "entities", "geometries", "subjects", "relations", "assertions")}

    # relation_types должны быть засеяны — поднимем индекс code→id (досеем недостающее).
    rt_index = {rt.code: rt for rt in session.scalars(select(RelationType)).all()}
    if not rt_index:
        for rt in RELATION_TYPES_SEED:
            session.add(RelationType(code=rt["code"], name=rt["name"],
                                     domain=rt["domain"], category=rt["category"]))
        session.flush()
        rt_index = {rt.code: rt for rt in session.scalars(select(RelationType)).all()}

    ent_cache: dict[str, Entity] = {}

    def get_entity(kind: EntityKind, gnid: str, ref_table: str, ref_pk: str,
                   label: Optional[str] = None, cad: Optional[str] = None) -> Entity:
        if gnid in ent_cache:
            return ent_cache[gnid]
        e = Entity(graph_node_id=gnid, kind=kind, ref_table=ref_table,
                   ref_pk=ref_pk, label=label, cad_number=cad)
        session.add(e); session.flush()
        ent_cache[gnid] = e
        counts["entities"] += 1
        return e

    def add_relation(frm: Entity, to: Entity, code: str, *,
                     source: DataSourceType, doc_meta: Optional[dict] = None) -> Relation:
        rt = rt_index[code]
        rel = Relation(from_entity_id=frm.id, to_entity_id=to.id,
                       relation_type_id=rt.id, domain=rt.domain, meta=doc_meta)
        session.add(rel); session.flush()
        counts["relations"] += 1
        w = SOURCE_WEIGHTS.get(source, 0.3)
        a = Assertion(relation_id=rel.id, confidence_score=confidence_from_evidences([w]))
        session.add(a); session.flush()
        session.add(Evidence(assertion_id=a.id, source_type=source, weight=w))
        counts["assertions"] += 1
        return rel

    # ── §1 объекты (land + building) → objects + entities ─────────────────────
    obj_entity: dict[str, Entity] = {}  # cad → entity
    for src_table, otype_fixed in (("land_objects", "land"), ("building_objects", None)):
        for r in _rows(src, src_table):
            cad = r["cad_number"]
            otype = otype_fixed or (r.get("object_type") or "building")
            kind = _OBJTYPE_TO_KIND.get(otype, EntityKind.building)
            floors = r.get("floors_above_ground") or r.get("floors_total") or r.get("floors")
            session.merge(Object(
                cad_number=cad, object_type=otype, address=r.get("address"),
                area=r.get("area"), category=r.get("land_category"),
                permitted_use=None, purpose=r.get("purpose"), floors=floors,
            ))
            counts["objects"] += 1
            e = get_entity(kind, f"{kind.value}:{cad}", "objects", cad,
                           label=r.get("name"), cad=cad)
            obj_entity[cad] = e
    session.flush()

    # ── object_geometries → geometries ────────────────────────────────────────
    for g in _rows(src, "object_geometries"):
        if not g.get("is_current", 1):
            continue
        ent = obj_entity.get(g["cad_number"])
        srid = 4326 if str(g.get("crs", "")).endswith("4326") else 4326
        session.add(Geometry(
            entity_id=ent.id if ent else None, cad_number=g["cad_number"],
            geometry_type=(g.get("geom_type") or "POLYGON").upper(),
            coordinates_wkt=g.get("geom_wkt") or "", geojson=None, srid=srid,
            source_type=DataSourceType.EGRN,
        ))
        counts["geometries"] += 1

    # ── accessories → entities(accessory) + geometries(POINT) + CONTAINS ──────
    for a in _rows(src, "accessories"):
        if a.get("is_disposed"):
            continue
        aid = a["accessory_id"]
        ae = get_entity(EntityKind.accessory, f"accessory:{aid}", "accessories", str(aid),
                        label=a.get("item_name"))
        if a.get("lat") is not None and a.get("lon") is not None:
            session.add(Geometry(
                entity_id=ae.id, geometry_type="POINT",
                coordinates_wkt=f"POINT({a['lon']} {a['lat']})", srid=4326,
                source_type=DataSourceType.EXIF,
            ))
            counts["geometries"] += 1
        parent = obj_entity.get(a.get("re_cad_number"))
        if parent is not None:
            add_relation(parent, ae, "CONTAINS", source=DataSourceType.EGRN)

    # ── entity_registry → subjects(§10) + entity_registry(§2 compat) + kpp ────
    subj_entity: dict[str, Entity] = {}   # inn → entity
    subj_by_inn: dict[str, Subject] = {}
    for er in _rows(src, "entity_registry"):
        inn = er.get("inn")
        stype = _ENTITY_TYPE_TO_SUBJECT.get((er.get("entity_type") or "").lower(),
                                            SubjectType.LEGAL_ENTITY)
        subj = Subject(subject_type=stype, inn=inn, ogrn=er.get("ogrn"),
                       name_current=er.get("name_full") or er.get("name_short") or (inn or "?"))
        session.add(subj); session.flush()
        counts["subjects"] += 1
        if inn:
            subj_by_inn[inn] = subj
            session.merge(EntityRegistry(
                inn=inn, name_full=subj.name_current, name_short=er.get("name_short"),
                ogrn=er.get("ogrn"), entity_type=er.get("entity_type")))
        if er.get("kpp"):
            session.add(SubjectKpp(subject_id=subj.id, kpp=er["kpp"], is_main=True))
        gnid = f"subj:{inn}" if inn else f"subj:uuid:{uuid.uuid4().hex[:12]}"
        skind = (EntityKind.beneficiary_person if stype == SubjectType.INDIVIDUAL
                 else EntityKind.state_body if stype == SubjectType.STATE_BODY
                 else EntityKind.beneficiary_legal)
        e = get_entity(skind, gnid, "subjects", str(subj.id), label=subj.name_current)
        if inn:
            subj_entity[inn] = e
    session.flush()

    # ── rights + right_holders → relations[legal] + legal_relation + provenance
    holders_by_right: dict[int, list[dict]] = {}
    for h in _rows(src, "right_holders"):
        holders_by_right.setdefault(h["right_id"], []).append(h)

    for r in _rows(src, "rights"):
        if not r.get("is_active", 1):
            continue
        obj_e = obj_entity.get(r.get("object_key_value"))
        if obj_e is None:
            continue
        cat = r.get("right_category")
        code = ("RESTRICTED_BY" if cat == "restriction"
                else "MORTGAGED_BY" if cat == "encumbrance"
                else "LEASES" if (r.get("right_type_code") == "lease") else "OWNS")
        for h in holders_by_right.get(r["right_id"], []):
            inn = h.get("inn")
            if inn and inn in subj_entity:
                subj_e = subj_entity[inn]
            else:
                gnid = f"subj:uuid:{uuid.uuid4().hex[:12]}"
                subj_e = get_entity(EntityKind.beneficiary_legal, gnid, "right_holders",
                                    str(h["holder_id"]), label=h.get("name"))
            rel = add_relation(subj_e, obj_e, code, source=DataSourceType.EGRN,
                               doc_meta={"right_number": r.get("right_number"),
                                         "since": r.get("right_date")})
            session.add(LegalRelation(
                relation_id=rel.id, registration_number=r.get("right_number"),
                registry_source="EGRN", right_type_code=r.get("right_type_code")))

    # ── ownership_chain → relations[legal/corporate CONTROLS] ─────────────────
    er_id_to_inn = {er["entity_id"]: er.get("inn")
                    for er in _rows(src, "entity_registry") if er.get("inn")}
    for ch in _rows(src, "ownership_chain"):
        if not ch.get("is_active", 1):
            continue
        p_inn = er_id_to_inn.get(ch["parent_entity_id"])
        c_inn = er_id_to_inn.get(ch["child_entity_id"])
        if p_inn in subj_entity and c_inn in subj_entity:
            ds = _CHAIN_SOURCE_TO_DS.get((ch.get("source") or "").lower(), DataSourceType.SURVEY_MANUAL)
            add_relation(subj_entity[p_inn], subj_entity[c_inn], "CONTROLS",
                         source=ds, doc_meta={"share_pct": ch.get("share_pct")})

    session.commit()
    src.close()
    return counts


def main() -> None:
    if len(sys.argv) < 2:
        sys.exit("usage: python -m contracts.db.import_block2 <block2.sqlite>")
    import os
    engine = create_engine(os.environ.get("EKCELO_DB_URL", "sqlite:///c2.db"))
    with Session(engine) as s:
        counts = import_block2(sys.argv[1], s)
    print("imported:", counts)


if __name__ == "__main__":
    main()
