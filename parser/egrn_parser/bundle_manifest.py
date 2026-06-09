"""
egrn_parser/bundle_manifest.py — эмиттер manifest.json бандла (C3, SPEC_parser §4).

Собирает `manifest.json` по контракту `contracts/bundle/bundle.schema.json`:
версии контрактов + `files[]` с sha256/bytes + состав (`objects`/`lot`) + флаги
(`etp_layer_present`, `extract_date`). Хеши файлов — sha256 байт (идемпотентность:
round-trip даёт те же sha256). Lot-фрагмент — из `lot_assembler.lot_manifest`.

Минимальное ядро Bundle-эмиттера: сборку каталога (kmz/db/json) делает golden-path,
здесь — детерминированный манифест + валидатор формы.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import os
from pathlib import Path
from typing import Any, Optional

# Разрешённые ключи верхнего уровня (bundle.schema.json, additionalProperties:false).
_ALLOWED = {"bundle_version", "contracts_version", "kmz_contract_version", "kind",
            "primary_cad_number", "extract_date", "etp_layer_present", "generated_by",
            "generated_at", "objects", "lot", "files"}
_REQUIRED = {"bundle_version", "contracts_version", "kmz_contract_version", "kind",
             "objects", "files", "generated_at"}
_VER_RE = __import__("re").compile(r"^\d+\.\d+\.\d+$")
_DATE_RE = __import__("re").compile(r"^\d{4}-\d{2}-\d{2}$")
_SHA_RE = __import__("re").compile(r"^[a-f0-9]{64}$")


def sha256_file(path: str | Path) -> str:
    """SHA-256 (hex) содержимого файла, потоково."""
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def file_entry(path: str | Path, *, arcname: Optional[str] = None) -> dict[str, Any]:
    """Запись files[] {path, sha256, bytes} для файла. `arcname` — путь в бандле."""
    p = Path(path)
    return {"path": arcname or p.name, "sha256": sha256_file(p),
            "bytes": p.stat().st_size}


def build_manifest(*, kind: str, files: list[dict[str, Any]], objects: list[str],
                   bundle_version: str = "1.0.0", contracts_version: str = "1.0.0",
                   kmz_contract_version: str = "2.12.0",
                   primary_cad_number: Optional[str] = None,
                   extract_date: Optional[str] = None,
                   etp_layer_present: Optional[bool] = None,
                   lot: Optional[dict[str, Any]] = None,
                   generated_by: str = "egrn-parser / golden-path",
                   generated_at: Optional[str] = None) -> dict[str, Any]:
    """Собрать manifest-словарь (C3). `files` — список file_entry; `lot` —
    фрагмент lot_assembler.lot_manifest (обязателен при kind='lot')."""
    m: dict[str, Any] = {
        "bundle_version": bundle_version,
        "contracts_version": contracts_version,
        "kmz_contract_version": kmz_contract_version,
        "kind": kind,
        "objects": list(objects),
        "files": files,
        "generated_at": generated_at or _dt.datetime.now(_dt.timezone.utc).isoformat(),
        "generated_by": generated_by,
    }
    if primary_cad_number is not None:
        m["primary_cad_number"] = primary_cad_number
    if extract_date is not None:
        m["extract_date"] = extract_date
    if etp_layer_present is not None:
        m["etp_layer_present"] = etp_layer_present
    if lot is not None:
        m["lot"] = lot
    return m


def validate_manifest(manifest: dict[str, Any]) -> list[str]:
    """Лёгкая проверка формы манифеста по контракту. [] = валиден."""
    errs = []
    keys = set(manifest)
    for k in _REQUIRED - keys:
        errs.append(f"отсутствует обязательное поле '{k}'")
    for k in keys - _ALLOWED:
        errs.append(f"недопустимое поле '{k}' (additionalProperties:false)")
    for k in ("bundle_version", "contracts_version", "kmz_contract_version"):
        if k in manifest and not _VER_RE.match(str(manifest[k])):
            errs.append(f"{k}: ожидался semver X.Y.Z")
    if manifest.get("kind") not in ("object", "lot"):
        errs.append("kind: ожидается 'object' | 'lot'")
    if manifest.get("kind") == "lot" and "lot" not in manifest:
        errs.append("kind='lot', но отсутствует блок 'lot'")
    ed = manifest.get("extract_date")
    if ed is not None and not _DATE_RE.match(str(ed)):
        errs.append("extract_date: ожидался YYYY-MM-DD")
    for i, fe in enumerate(manifest.get("files") or []):
        if "path" not in fe or "sha256" not in fe:
            errs.append(f"files[{i}]: нужны path и sha256")
        elif not _SHA_RE.match(str(fe["sha256"])):
            errs.append(f"files[{i}].sha256: ожидался hex64")
    if "lot" in manifest:
        lot = manifest["lot"]
        for k in ("lot_id", "as_of_date", "members"):
            if k not in lot:
                errs.append(f"lot: отсутствует '{k}'")
        if "as_of_date" in lot and not _DATE_RE.match(str(lot["as_of_date"])):
            errs.append("lot.as_of_date: ожидался YYYY-MM-DD")
    return errs
