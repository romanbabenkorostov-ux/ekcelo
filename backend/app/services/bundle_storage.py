"""Bundle storage (sub-stage C3.1) — sidecar таблица + хранилище KMZ.

Реализует часть `SPEC_backend.md §P0.3` — обратная сторона импорта Bundle:
после `import_bundle` (см. `bundle.py`) сохраняет метаданные манифеста в
sidecar-таблицу `bundles` (миграция 0002) и копирует `project.kmz` в файловую
систему `<bundles_dir>/<bundle_id>.kmz`, чтобы потом отдать через
`GET /bundles/{bundle_id}/download?fmt=…`.

Этот модуль — **отдельный** от `bundle.py` (импортёр БД). Импортёр и хранилище
оркеструются на уровне эндпоинта (`lot_orchestrator_web/main.py`), что
сохраняет чистый разрез:
- `bundle.py` — мутирует §1..§6 ЕГРН + ЭТП-профиля в target_db.
- `bundle_storage.py` — записывает метаданные Bundle и кладёт KMZ для
  последующей выдачи.

`bundle_id` = sha256 канонического (sorted_keys, no whitespace) JSON манифеста.
Стабилен между сессиями: повтор `import_bundle` того же манифеста → тот же
bundle_id → нет дубликата строки (идемпотентность).

См. также:
- `schema/migrations/0002_bundles.sql` — DDL sidecar-таблицы.
- `contracts/api/openapi.yaml::/bundles/{id}/download` — контракт реверс-выдачи.
"""
from __future__ import annotations

import hashlib
import json
import shutil
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from backend.app.services.bundle import Manifest


_REPO_ROOT = Path(__file__).resolve().parents[3]
_MIGRATION_0002 = _REPO_ROOT / "schema" / "migrations" / "0002_bundles.sql"

_FALLBACK_DDL = """
CREATE TABLE IF NOT EXISTS bundles (
    bundle_id            TEXT PRIMARY KEY,
    bundle_version       TEXT NOT NULL,
    contracts_version    TEXT NOT NULL,
    kmz_contract_version TEXT NOT NULL,
    kind                 TEXT NOT NULL,
    primary_cad_number   TEXT,
    manifest_json        TEXT NOT NULL,
    kmz_path             TEXT,
    kmz_sha256           TEXT,
    kmz_bytes            INTEGER,
    imported_at          TEXT NOT NULL DEFAULT (datetime('now'))
);
"""


@dataclass
class BundleRecord:
    bundle_id: str
    bundle_version: str
    contracts_version: str
    kmz_contract_version: str
    kind: str
    primary_cad_number: str | None
    manifest_json: dict
    kmz_path: Path | None  # абсолютный путь, если есть локальный KMZ
    kmz_sha256: str | None
    kmz_bytes: int | None
    imported_at: str


# ─────────────────────────────────────────────────────────────────────────────
#  Bundle ID
# ─────────────────────────────────────────────────────────────────────────────

def compute_bundle_id(manifest: Manifest) -> str:
    """Детерминированный bundle_id (sha256 hex) от каноничного манифеста.

    Канонизация — `model_dump_json(exclude_none=True)` + парсинг + json.dumps с
    `sort_keys=True, separators=(",",":"), default=str`. Стабильно между
    запусками; ИДЕНТИЧНОСТЬ двух манифестов с одинаковыми полями → один id.
    """
    raw = manifest.model_dump(mode="json", exclude_none=True)
    canonical = json.dumps(raw, sort_keys=True, separators=(",", ":"),
                           ensure_ascii=False, default=str)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


# ─────────────────────────────────────────────────────────────────────────────
#  Schema
# ─────────────────────────────────────────────────────────────────────────────

def ensure_bundles_schema(conn: sqlite3.Connection) -> None:
    """Применяет миграцию 0002 (или fallback DDL если файл не найден)."""
    if _MIGRATION_0002.is_file():
        conn.executescript(_MIGRATION_0002.read_text(encoding="utf-8"))
    else:
        conn.executescript(_FALLBACK_DDL)


# ─────────────────────────────────────────────────────────────────────────────
#  Store / get
# ─────────────────────────────────────────────────────────────────────────────

def store_bundle(
    target_db: Path,
    bundles_dir: Path,
    bundle_path: Path,
    manifest: Manifest,
) -> str:
    """Сохраняет метаданные Bundle + KMZ-файл (если есть).

    Идемпотентно: повторный вызов для того же манифеста → возвращает тот же
    bundle_id, не дублирует запись и не перекопирует KMZ.

    Args:
        target_db: путь к ekcelo.sqlite, куда уже импортирован Bundle.
        bundles_dir: корень хранилища KMZ; будет создан если отсутствует.
        bundle_path: каталог Bundle (где лежит project.kmz).
        manifest: распарсенный манифест (источник правды для bundle_id).

    Returns:
        bundle_id (sha256 hex).
    """
    bundle_id = compute_bundle_id(manifest)
    bundles_dir = Path(bundles_dir)
    bundles_dir.mkdir(parents=True, exist_ok=True)

    kmz_src = bundle_path / "project.kmz"
    kmz_present = kmz_src.is_file()
    kmz_rel: str | None = None
    kmz_sha: str | None = None
    kmz_size: int | None = None
    if kmz_present:
        kmz_dst = bundles_dir / f"{bundle_id}.kmz"
        if not kmz_dst.exists():
            shutil.copyfile(kmz_src, kmz_dst)
        kmz_rel = kmz_dst.name
        kmz_sha = _sha256_file(kmz_dst)
        kmz_size = kmz_dst.stat().st_size

    manifest_json_text = json.dumps(
        manifest.model_dump(mode="json", exclude_none=True),
        sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str,
    )

    conn = sqlite3.connect(target_db)
    try:
        ensure_bundles_schema(conn)
        existing = conn.execute(
            "SELECT bundle_id FROM bundles WHERE bundle_id = ?", (bundle_id,)
        ).fetchone()
        if existing is None:
            conn.execute(
                "INSERT INTO bundles(bundle_id, bundle_version, contracts_version, "
                "  kmz_contract_version, kind, primary_cad_number, manifest_json, "
                "  kmz_path, kmz_sha256, kmz_bytes) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    bundle_id, manifest.bundle_version, manifest.contracts_version,
                    manifest.kmz_contract_version, manifest.kind,
                    manifest.primary_cad_number, manifest_json_text,
                    kmz_rel, kmz_sha, kmz_size,
                ),
            )
            conn.commit()
    finally:
        conn.close()
    return bundle_id


def get_bundle(
    target_db: Path,
    bundles_dir: Path,
    bundle_id: str,
) -> BundleRecord | None:
    """Возвращает BundleRecord или None если запись отсутствует."""
    if not target_db.exists():
        return None
    conn = sqlite3.connect(target_db)
    conn.row_factory = sqlite3.Row
    try:
        if not _bundles_table_exists(conn):
            return None
        row = conn.execute(
            "SELECT bundle_id, bundle_version, contracts_version, "
            "       kmz_contract_version, kind, primary_cad_number, "
            "       manifest_json, kmz_path, kmz_sha256, kmz_bytes, imported_at "
            "FROM bundles WHERE bundle_id = ?",
            (bundle_id,),
        ).fetchone()
        if row is None:
            return None
        kmz_abs = (
            (Path(bundles_dir) / row["kmz_path"]).resolve()
            if row["kmz_path"] else None
        )
        if kmz_abs is not None and not kmz_abs.exists():
            kmz_abs = None  # запись есть, но файл потерян (вернём None как путь)
        try:
            manifest_dict = json.loads(row["manifest_json"])
        except (json.JSONDecodeError, TypeError):
            manifest_dict = {}
        return BundleRecord(
            bundle_id=row["bundle_id"],
            bundle_version=row["bundle_version"],
            contracts_version=row["contracts_version"],
            kmz_contract_version=row["kmz_contract_version"],
            kind=row["kind"],
            primary_cad_number=row["primary_cad_number"],
            manifest_json=manifest_dict,
            kmz_path=kmz_abs,
            kmz_sha256=row["kmz_sha256"],
            kmz_bytes=row["kmz_bytes"],
            imported_at=row["imported_at"],
        )
    finally:
        conn.close()


# ─────────────────────────────────────────────────────────────────────────────
#  Утилиты
# ─────────────────────────────────────────────────────────────────────────────

def _bundles_table_exists(conn: sqlite3.Connection) -> bool:
    row = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='bundles'"
    ).fetchone()
    return row is not None


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()
