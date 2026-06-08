"""Bundle reverse-export (sub-stage C3.2) — реэкспорт Bundle из БД.

Реализует `SPEC_backend.md §P0.3` C3.2 — обратную операцию к импорту: собирает
Bundle (или его часть) обратно из ekcelo.sqlite §1..§6 + сохранённого KMZ.
Контракт C4: `GET /bundles/{id}/download?fmt={zip,db,json}`.

Форматы:
- `db`   → срез sqlite по `manifest.objects[]` (objects + связанные rights +
           entity_registry + extracts + object_etp_profile + object_restrictions).
- `json` → нормализованные ViewModel объектов bundle (через viewmodel-сервис).
- `zip`  → полный Bundle: `manifest.json` + `db.sqlite` (срез) + `project.kmz`
           (сохранённый). Манифест перегенерируется со СВЕЖИМИ sha256/bytes
           (срез БД не байт-идентичен исходному, но round-trip импорт = no-op).

**Round-trip контракт** (SPEC §P0.3): `export(zip) → import → is_noop == True`.
Идемпотентность гарантируется НЕ байт-идентичностью файлов, а тем, что
повторный импорт среза не меняет ни одной целевой строки.

См. также:
- `backend/app/services/bundle_storage.py` — sidecar (даёт BundleRecord + KMZ).
- `backend/app/services/bundle.py` — импортёр (обратная сторона round-trip).
- `backend/app/services/viewmodel.py` — для fmt=json.
"""
from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import tempfile
import zipfile
from pathlib import Path

from backend.app.services.bundle_storage import BundleRecord


# Таблицы среза и как их фильтровать по списку cad / inn.
_EXPORT_SCHEMA = """
CREATE TABLE objects (
    cad_number TEXT PRIMARY KEY, object_type TEXT NOT NULL, address TEXT,
    area REAL, category TEXT, permitted_use TEXT, purpose TEXT, floors INTEGER
);
CREATE TABLE entity_registry (
    inn TEXT PRIMARY KEY, name_full TEXT NOT NULL, name_short TEXT,
    ogrn TEXT, entity_type TEXT
);
CREATE TABLE rights (
    id INTEGER PRIMARY KEY AUTOINCREMENT, cad_number TEXT NOT NULL,
    right_type TEXT NOT NULL, right_holder_inn TEXT,
    share_numerator INTEGER, share_denominator INTEGER,
    registration_number TEXT, registration_date TEXT
);
CREATE TABLE extracts (
    id INTEGER PRIMARY KEY AUTOINCREMENT, extract_number TEXT,
    cad_number TEXT NOT NULL, extract_date TEXT NOT NULL
);
CREATE TABLE object_restrictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT, cad_number TEXT NOT NULL,
    restrict_type TEXT, description TEXT, registry_number TEXT,
    valid_from TEXT, valid_to TEXT, basis_doc TEXT
);
CREATE TABLE object_etp_profile (
    cad_number TEXT PRIMARY KEY, location_extra TEXT, building_extra TEXT,
    layout TEXT, legal_extra TEXT, risks TEXT, extras TEXT,
    source TEXT NOT NULL, confidence REAL NOT NULL
);
"""


class BundleExportError(Exception):
    """Невозможно собрать экспорт (например, объект из манифеста исчез из БД)."""


# ─────────────────────────────────────────────────────────────────────────────
#  fmt=db — срез sqlite
# ─────────────────────────────────────────────────────────────────────────────

def export_bundle_db(target_db: Path, record: BundleRecord) -> bytes:
    """Собирает sqlite-срез БД для объектов из манифеста. Возвращает bytes."""
    cads = _manifest_cads(record)
    src = sqlite3.connect(target_db)
    src.row_factory = sqlite3.Row
    try:
        with tempfile.TemporaryDirectory(prefix="ekcelo-export-") as tmp:
            out_path = Path(tmp) / "db.sqlite"
            dst = sqlite3.connect(out_path)
            try:
                dst.executescript(_EXPORT_SCHEMA)
                _copy_objects(src, dst, cads)
                inns = _copy_rights(src, dst, cads)
                _copy_entities(src, dst, inns)
                _copy_extracts(src, dst, cads)
                _copy_restrictions(src, dst, cads)
                _copy_etp(src, dst, cads)
                dst.commit()
            finally:
                dst.close()
            return out_path.read_bytes()
    finally:
        src.close()


def _manifest_cads(record: BundleRecord) -> list[str]:
    objects = record.manifest_json.get("objects") or []
    if not objects:
        raise BundleExportError("в манифесте нет objects[]")
    return list(objects)


def _placeholders(items: list[str]) -> str:
    return ",".join("?" * len(items))


def _copy_objects(src: sqlite3.Connection, dst: sqlite3.Connection,
                  cads: list[str]) -> None:
    if not _table_exists(src, "objects"):
        raise BundleExportError("в целевой БД нет таблицы objects")
    ph = _placeholders(cads)
    rows = src.execute(
        f"SELECT cad_number, object_type, address, area, category, "
        f"permitted_use, purpose, floors FROM objects "
        f"WHERE cad_number IN ({ph}) ORDER BY cad_number", cads,
    ).fetchall()
    found = {r["cad_number"] for r in rows}
    missing = [c for c in cads if c not in found]
    if missing:
        raise BundleExportError(
            f"объекты из манифеста отсутствуют в БД: {', '.join(missing)}"
        )
    dst.executemany(
        "INSERT INTO objects(cad_number, object_type, address, area, "
        "category, permitted_use, purpose, floors) VALUES (?,?,?,?,?,?,?,?)",
        [tuple(r) for r in rows],
    )


def _copy_rights(src: sqlite3.Connection, dst: sqlite3.Connection,
                 cads: list[str]) -> list[str]:
    if not _table_exists(src, "rights"):
        return []
    ph = _placeholders(cads)
    rows = src.execute(
        f"SELECT cad_number, right_type, right_holder_inn, share_numerator, "
        f"share_denominator, registration_number, registration_date "
        f"FROM rights WHERE cad_number IN ({ph}) ORDER BY id", cads,
    ).fetchall()
    dst.executemany(
        "INSERT INTO rights(cad_number, right_type, right_holder_inn, "
        "share_numerator, share_denominator, registration_number, "
        "registration_date) VALUES (?,?,?,?,?,?,?)",
        [tuple(r) for r in rows],
    )
    return sorted({r["right_holder_inn"] for r in rows if r["right_holder_inn"]})


def _copy_entities(src: sqlite3.Connection, dst: sqlite3.Connection,
                   inns: list[str]) -> None:
    if not inns or not _table_exists(src, "entity_registry"):
        return
    ph = _placeholders(inns)
    rows = src.execute(
        f"SELECT inn, name_full, name_short, ogrn, entity_type "
        f"FROM entity_registry WHERE inn IN ({ph}) ORDER BY inn", inns,
    ).fetchall()
    dst.executemany(
        "INSERT INTO entity_registry(inn, name_full, name_short, ogrn, "
        "entity_type) VALUES (?,?,?,?,?)",
        [tuple(r) for r in rows],
    )


def _copy_extracts(src: sqlite3.Connection, dst: sqlite3.Connection,
                   cads: list[str]) -> None:
    if not _table_exists(src, "extracts"):
        return
    ph = _placeholders(cads)
    rows = src.execute(
        f"SELECT extract_number, cad_number, extract_date FROM extracts "
        f"WHERE cad_number IN ({ph}) ORDER BY id", cads,
    ).fetchall()
    dst.executemany(
        "INSERT INTO extracts(extract_number, cad_number, extract_date) "
        "VALUES (?,?,?)",
        [tuple(r) for r in rows],
    )


def _copy_restrictions(src: sqlite3.Connection, dst: sqlite3.Connection,
                       cads: list[str]) -> None:
    if not _table_exists(src, "object_restrictions"):
        return
    ph = _placeholders(cads)
    rows = src.execute(
        f"SELECT cad_number, restrict_type, description, registry_number, "
        f"valid_from, valid_to, basis_doc FROM object_restrictions "
        f"WHERE cad_number IN ({ph}) ORDER BY id", cads,
    ).fetchall()
    dst.executemany(
        "INSERT INTO object_restrictions(cad_number, restrict_type, "
        "description, registry_number, valid_from, valid_to, basis_doc) "
        "VALUES (?,?,?,?,?,?,?)",
        [tuple(r) for r in rows],
    )


def _copy_etp(src: sqlite3.Connection, dst: sqlite3.Connection,
              cads: list[str]) -> None:
    if not _table_exists(src, "object_etp_profile"):
        return
    ph = _placeholders(cads)
    rows = src.execute(
        f"SELECT cad_number, location_extra, building_extra, layout, "
        f"legal_extra, risks, extras, source, confidence "
        f"FROM object_etp_profile WHERE cad_number IN ({ph}) "
        f"ORDER BY cad_number", cads,
    ).fetchall()
    dst.executemany(
        "INSERT INTO object_etp_profile(cad_number, location_extra, "
        "building_extra, layout, legal_extra, risks, extras, source, "
        "confidence) VALUES (?,?,?,?,?,?,?,?,?)",
        [tuple(r) for r in rows],
    )


# ─────────────────────────────────────────────────────────────────────────────
#  fmt=json — ViewModel объектов
# ─────────────────────────────────────────────────────────────────────────────

def export_bundle_json(target_db: Path, record: BundleRecord) -> dict:
    """Собирает нормализованный JSON: {bundle_id, objects: [ViewModel...]}."""
    from backend.app.services.viewmodel import (
        ObjectNotFound,
        build_object_viewmodel,
    )

    cads = _manifest_cads(record)
    objects = []
    for cad in cads:
        try:
            vm = build_object_viewmodel(target_db, cad)
        except ObjectNotFound as exc:
            raise BundleExportError(f"объект {cad} отсутствует в БД") from exc
        objects.append(vm.model_dump(exclude_none=True))
    return {
        "bundle_id": record.bundle_id,
        "kind": record.kind,
        "primary_cad_number": record.primary_cad_number,
        "objects": objects,
    }


# ─────────────────────────────────────────────────────────────────────────────
#  fmt=zip — полный Bundle (manifest + db + kmz)
# ─────────────────────────────────────────────────────────────────────────────

def export_bundle_zip(target_db: Path, record: BundleRecord) -> bytes:
    """Собирает полный Bundle-zip с перегенерированным манифестом.

    Манифест берётся из сохранённого `record.manifest_json`, но его `files[]`
    перезаписывается СВЕЖИМИ sha256/bytes реально упакованных файлов (db.sqlite
    + project.kmz если есть). Round-trip: импорт результата = no-op.
    """
    db_bytes = export_bundle_db(target_db, record)
    kmz_bytes: bytes | None = None
    if record.kmz_path is not None and Path(record.kmz_path).is_file():
        kmz_bytes = Path(record.kmz_path).read_bytes()

    manifest = dict(record.manifest_json)
    files = [{
        "path": "db.sqlite",
        "sha256": _sha256_bytes(db_bytes),
        "bytes": len(db_bytes),
    }]
    if kmz_bytes is not None:
        files.append({
            "path": "project.kmz",
            "sha256": _sha256_bytes(kmz_bytes),
            "bytes": len(kmz_bytes),
        })
    manifest["files"] = files
    manifest_text = json.dumps(manifest, ensure_ascii=False, sort_keys=True,
                               separators=(",", ":"))

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("manifest.json", manifest_text)
        zf.writestr("db.sqlite", db_bytes)
        if kmz_bytes is not None:
            zf.writestr("project.kmz", kmz_bytes)
    return buf.getvalue()


# ─────────────────────────────────────────────────────────────────────────────
#  Утилиты
# ─────────────────────────────────────────────────────────────────────────────

def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    return conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone() is not None


def _sha256_bytes(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()
