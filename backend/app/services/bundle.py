"""Bundle (C3) — манифест-схема, валидация, идемпотентный импорт.

Реализует SPEC_backend.md §P0.2: импортёр Bundle. Контракт — `contracts/bundle/`.

Bundle = единица обмена между локальным парсером (Win10) и веб-бэкендом:

    <bundle_root>/
    ├── manifest.json          # обязателен, JSON Schema → contracts/bundle/bundle.schema.json
    ├── project.kmz            # C1 wire 2.12.0
    ├── db.sqlite              # C2 §1-§6 (объекты, права, ЭТП-профиль)
    ├── json/                  # parser-internal промежуточные
    └── raw/                   # опц.: исходные документы

Этот модуль:
- Валидирует `manifest.json` по C3 (`Manifest` Pydantic-схема).
- Идемпотентно импортирует `db.sqlite` Bundle'а в целевую ekcelo-БД,
  гэп-fill upsert по `cad_number` (НЕ перезатирает manual/osv записи
  ЭТП-профиля — соответствует ADR-001 §6).
- Возвращает `ImportReport` с детализацией: что добавлено / обновлено / пропущено.

См. также: `contracts/bundle/BUNDLE_SPEC.md`, `parser/egrn_parser/merge/upsert.py`
(паттерн UPSERT-стратегий, переиспользуется здесь концептуально).
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


# ─────────────────────────────────────────────────────────────────────────────
#  Манифест-схема (C3) — Pydantic-зеркало bundle.schema.json
# ─────────────────────────────────────────────────────────────────────────────

class FileEntry(BaseModel):
    model_config = ConfigDict(extra="allow")

    path: str
    sha256: str = Field(..., pattern=r"^[0-9a-f]{64}$")
    bytes: int = Field(..., ge=0)


class LotInfo(BaseModel):
    model_config = ConfigDict(extra="allow")

    lot_id: str
    as_of_date: date | None = None
    include: dict[str, Any] | None = None
    exclude: dict[str, Any] | None = None
    members: list[str] = Field(default_factory=list)


class Manifest(BaseModel):
    """C3 manifest.json — нормативная Pydantic-схема."""

    model_config = ConfigDict(extra="allow")

    bundle_version: str
    contracts_version: str
    kmz_contract_version: str
    kind: Literal["object", "lot"]
    primary_cad_number: str | None = None
    extract_date: date | None = None
    etp_layer_present: bool = False
    generated_by: str | None = None
    generated_at: datetime
    objects: list[str] = Field(..., min_length=1)
    lot: LotInfo | None = None
    files: list[FileEntry] = Field(..., min_length=1)

    @field_validator("objects")
    @classmethod
    def _objects_unique(cls, v: list[str]) -> list[str]:
        if len(set(v)) != len(v):
            raise ValueError("objects[] содержит дубликаты")
        return v


# ─────────────────────────────────────────────────────────────────────────────
#  Импорт
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ImportReport:
    bundle_path: Path
    manifest: Manifest | None = None
    objects_inserted: int = 0
    objects_updated: int = 0
    objects_skipped_identical: int = 0
    rights_inserted: int = 0
    entities_inserted: int = 0
    etp_profiles_inserted: int = 0
    etp_profiles_skipped_authoritative: int = 0
    files_verified: int = 0
    files_failed: list[str] = field(default_factory=list)
    schema_violations: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    @property
    def is_noop(self) -> bool:
        """True если ни одна целевая строка не изменилась (повтор того же Bundle)."""
        return (
            self.objects_inserted == 0
            and self.objects_updated == 0
            and self.rights_inserted == 0
            and self.entities_inserted == 0
            and self.etp_profiles_inserted == 0
            and not self.errors
        )


def load_manifest(bundle_path: Path) -> Manifest:
    """Читает `<bundle>/manifest.json`, валидирует по C3."""
    manifest_path = bundle_path / "manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(f"Bundle invalid: нет manifest.json в {bundle_path}")
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    return Manifest.model_validate(raw)


def verify_files(bundle_path: Path, manifest: Manifest) -> list[str]:
    """Проверяет sha256 каждого файла из `manifest.files[]`. Возвращает список фейлов."""
    failures: list[str] = []
    for entry in manifest.files:
        fpath = bundle_path / entry.path
        if not fpath.is_file():
            failures.append(f"missing: {entry.path}")
            continue
        actual = _sha256_file(fpath)
        if actual != entry.sha256:
            failures.append(f"sha256 mismatch: {entry.path} (expected {entry.sha256[:8]}…, got {actual[:8]}…)")
        size = fpath.stat().st_size
        if size != entry.bytes:
            failures.append(f"size mismatch: {entry.path} (expected {entry.bytes}, got {size})")
    return failures


def import_bundle(
    bundle_path: Path,
    target_db: Path,
    *,
    verify_hashes: bool = True,
    dry_run: bool = False,
    validate_schema: bool = False,
) -> ImportReport:
    """Главная точка входа: валидирует Bundle и идемпотентно импортирует в `target_db`.

    Args:
        bundle_path: каталог с manifest.json + db.sqlite + project.kmz.
        target_db: путь к ekcelo.sqlite (целевая БД).
        verify_hashes: если True — сверяет sha256 файлов с manifest.files[].
        dry_run: если True — открывает транзакцию и откатывает (отчёт остаётся).
        validate_schema: если True — сверяет `db.sqlite` Bundle'а с C2-контрактом
            (`contracts/bundle-db-slice/schema.json`) ДО мутации target_db. Нарушения → в
            `report.schema_violations` + `report.errors`; импорт прерывается.
            По умолчанию False (не ломает минимальные тест-фикстуры; реальные
            Bundle от парсера — полная схема, для них имеет смысл True).

    Returns:
        ImportReport с детализацией. `is_noop=True` при повторе того же Bundle.

    Raises:
        FileNotFoundError, ValueError (Pydantic), sqlite3.Error.
    """
    bundle_path = Path(bundle_path)
    target_db = Path(target_db)
    report = ImportReport(bundle_path=bundle_path)

    report.manifest = load_manifest(bundle_path)

    if verify_hashes:
        failures = verify_files(bundle_path, report.manifest)
        report.files_verified = len(report.manifest.files) - len(failures)
        report.files_failed = failures
        if failures:
            report.errors.append(f"file integrity: {len(failures)} проблем")
            return report

    source_db_path = bundle_path / "db.sqlite"
    if not source_db_path.is_file():
        report.errors.append("Bundle invalid: db.sqlite отсутствует")
        return report

    if validate_schema:
        from backend.app.services.db_contract import validate_db
        violations = validate_db(source_db_path)
        if violations:
            report.schema_violations = violations
            report.errors.append(
                f"schema contract: {len(violations)} нарушений C2-схемы"
            )
            return report

    target_db.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(target_db)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        _ensure_schema(conn)
        src = sqlite3.connect(source_db_path)
        src.row_factory = sqlite3.Row
        try:
            _import_objects(conn, src, report)
            _import_entities(conn, src, report)
            _import_rights(conn, src, report)
            if report.manifest.etp_layer_present:
                _import_etp_profiles(conn, src, report)
        finally:
            src.close()
        if dry_run:
            conn.rollback()
            report.warnings.append("dry-run: транзакция откачена")
        else:
            conn.commit()
    finally:
        conn.close()

    return report


# ─────────────────────────────────────────────────────────────────────────────
#  Internals
# ─────────────────────────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).resolve().parents[3]
_MIGRATION_0001 = _REPO_ROOT / "schema" / "migrations" / "0001_etp_profile.sql"

_MIN_EGRN_SCHEMA = """
CREATE TABLE IF NOT EXISTS objects (
    cad_number    TEXT PRIMARY KEY,
    object_type   TEXT NOT NULL,
    address       TEXT,
    area          REAL,
    category      TEXT,
    permitted_use TEXT,
    purpose       TEXT,
    floors        INTEGER,
    updated_at    TEXT DEFAULT (datetime('now'))
);
CREATE TABLE IF NOT EXISTS entity_registry (
    inn         TEXT PRIMARY KEY,
    name_full   TEXT NOT NULL,
    name_short  TEXT,
    ogrn        TEXT,
    entity_type TEXT
);
CREATE TABLE IF NOT EXISTS rights (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cad_number TEXT NOT NULL REFERENCES objects(cad_number),
    right_type TEXT NOT NULL,
    right_holder_inn TEXT REFERENCES entity_registry(inn),
    share_numerator INTEGER, share_denominator INTEGER,
    registration_number TEXT, registration_date TEXT, source_extract_id INTEGER
);
CREATE TABLE IF NOT EXISTS object_restrictions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    cad_number TEXT NOT NULL REFERENCES objects(cad_number),
    restrict_type TEXT, description TEXT, registry_number TEXT,
    valid_from TEXT, valid_to TEXT, basis_doc TEXT
);
"""


def _ensure_schema(conn: sqlite3.Connection) -> None:
    """Создаёт минимальную ЕГРН-схему + миграцию 0001 (ЭТП-слой) если их нет."""
    conn.executescript(_MIN_EGRN_SCHEMA)
    if _MIGRATION_0001.exists():
        conn.executescript(_MIGRATION_0001.read_text(encoding="utf-8"))


def _table_exists(conn: sqlite3.Connection, name: str) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)
    ).fetchone()
    return row is not None


_OBJECT_FIELDS = ("cad_number", "object_type", "address", "area",
                  "category", "permitted_use", "purpose", "floors")


def _import_objects(conn: sqlite3.Connection, src: sqlite3.Connection,
                    report: ImportReport) -> None:
    if not _table_exists(src, "objects"):
        report.warnings.append("source: нет таблицы objects")
        return
    for row in src.execute("SELECT * FROM objects"):
        cad = row["cad_number"]
        new_hash = _row_content_hash(row, _OBJECT_FIELDS)
        existing = conn.execute(
            "SELECT object_type, address, area, category, permitted_use, purpose, floors "
            "FROM objects WHERE cad_number = ?", (cad,)
        ).fetchone()
        values = tuple(_row_get(row, f) for f in _OBJECT_FIELDS)
        if existing is None:
            conn.execute(
                f"INSERT INTO objects({','.join(_OBJECT_FIELDS)}) "
                f"VALUES ({','.join('?' * len(_OBJECT_FIELDS))})",
                values,
            )
            report.objects_inserted += 1
            continue
        old_hash = _row_content_hash_from_tuple(
            (cad,) + tuple(existing), _OBJECT_FIELDS,
        )
        if new_hash == old_hash:
            report.objects_skipped_identical += 1
            continue
        conn.execute(
            "UPDATE objects SET object_type=?, address=?, area=?, "
            "category=?, permitted_use=?, purpose=?, floors=?, "
            "updated_at=datetime('now') WHERE cad_number=?",
            values[1:] + (cad,),
        )
        report.objects_updated += 1


def _import_entities(conn: sqlite3.Connection, src: sqlite3.Connection,
                     report: ImportReport) -> None:
    if not _table_exists(src, "entity_registry"):
        return
    for row in src.execute("SELECT * FROM entity_registry"):
        inn = row["inn"]
        existing = conn.execute(
            "SELECT 1 FROM entity_registry WHERE inn=?", (inn,)
        ).fetchone()
        if existing:
            continue
        conn.execute(
            "INSERT INTO entity_registry(inn, name_full, name_short, ogrn, entity_type) "
            "VALUES (?,?,?,?,?)",
            (inn, _row_get(row, "name_full"), _row_get(row, "name_short"),
             _row_get(row, "ogrn"), _row_get(row, "entity_type")),
        )
        report.entities_inserted += 1


def _import_rights(conn: sqlite3.Connection, src: sqlite3.Connection,
                   report: ImportReport) -> None:
    if not _table_exists(src, "rights"):
        return
    for row in src.execute("SELECT * FROM rights"):
        cad = row["cad_number"]
        rtype = row["right_type"]
        rinn = _row_get(row, "right_holder_inn")
        existing = conn.execute(
            "SELECT 1 FROM rights WHERE cad_number=? AND right_type=? "
            "AND COALESCE(right_holder_inn,'')=COALESCE(?,'')",
            (cad, rtype, rinn),
        ).fetchone()
        if existing:
            continue
        # FK guard: пропустить если objects нет (целостность).
        if not conn.execute("SELECT 1 FROM objects WHERE cad_number=?",
                            (cad,)).fetchone():
            report.warnings.append(f"rights: пропуск (нет object {cad})")
            continue
        conn.execute(
            "INSERT INTO rights(cad_number, right_type, right_holder_inn) "
            "VALUES (?,?,?)",
            (cad, rtype, rinn),
        )
        report.rights_inserted += 1


# ЭТП-профиль: ADR-001 §6 — manual/osv приоритетнее, не перезатираем.
_AUTHORITATIVE_SOURCES = frozenset({"manual", "osv"})


def _import_etp_profiles(conn: sqlite3.Connection, src: sqlite3.Connection,
                         report: ImportReport) -> None:
    if not _table_exists(src, "object_etp_profile"):
        return
    for row in src.execute("SELECT * FROM object_etp_profile"):
        cad = row["cad_number"]
        existing = conn.execute(
            "SELECT source FROM object_etp_profile WHERE cad_number=?", (cad,)
        ).fetchone()
        if existing and existing[0] in _AUTHORITATIVE_SOURCES:
            report.etp_profiles_skipped_authoritative += 1
            continue
        if existing:
            # Перезаписываем неавторитетный профиль (nspd/exif/llm).
            conn.execute(
                "DELETE FROM object_etp_profile WHERE cad_number=?", (cad,)
            )
        # PRAGMA table_info → (cid, name, type, notnull, dflt, pk); имя в [1].
        cols = [d[1] for d in src.execute("PRAGMA table_info(object_etp_profile)")]
        target_cols = [d[1] for d in conn.execute(
            "PRAGMA table_info(object_etp_profile)"
        )]
        common = [c for c in cols if c in target_cols]
        vals = [row[c] for c in common]
        placeholders = ",".join("?" * len(common))
        conn.execute(
            f"INSERT INTO object_etp_profile({','.join(common)}) "
            f"VALUES ({placeholders})",
            vals,
        )
        report.etp_profiles_inserted += 1


def _row_get(row: sqlite3.Row, col: str) -> Any:
    """Безопасный доступ к колонке: вернуть None если её нет в источнике."""
    try:
        return row[col]
    except (IndexError, KeyError):
        return None


def _row_content_hash(row: sqlite3.Row, fields: tuple[str, ...]) -> str:
    payload = {f: _row_get(row, f) for f in fields}
    return _hash_json(payload)


def _row_content_hash_from_tuple(vals: tuple, fields: tuple[str, ...]) -> str:
    return _hash_json(dict(zip(fields, vals)))


def _hash_json(payload: dict) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, ensure_ascii=False, default=str).encode("utf-8")
    ).hexdigest()


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


__all__ = [
    "FileEntry", "LotInfo", "Manifest",
    "ImportReport", "load_manifest", "verify_files", "import_bundle",
]
