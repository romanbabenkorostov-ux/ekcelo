"""
egrn_parser/bundle_assembler.py — оркестратор каталога Bundle (C3, SPEC_parser §4).

Собирает каталог по `contracts/bundle/BUNDLE_SPEC.md`:

    <bundle_root>/
    ├── manifest.json        # реестр + версии контрактов (bundle_manifest)
    ├── project.kmz          # C1 (вход — выход стадии 08)
    ├── db.sqlite            # C2 §1–§6
    ├── json/<...>.json      # parser-internal (structure/enriched/objects)
    └── raw/<...>            # опционально

Идемпотентно по содержимому: те же входы → те же sha256 файлов. manifest.json
несёт `generated_at` (меняется), но файлы — байт-в-байт. Состав лота — фрагмент
`lot_assembler.lot_manifest`; флаг §6 — `etp_merge.etp_layer_present`.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any, Optional

from egrn_parser import bundle_manifest as _bm


def _copy(src: str | Path, dst: Path) -> None:
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def mask_cad(cad: str) -> str:
    """КН → Windows-safe имя файла: `61:44:0050706:31` → `61_44_0050706_31`
    (`:`→`_`, `/`→`-`). Парсер работает на Win10 — `:` в именах запрещён."""
    return cad.replace(":", "_").replace("/", "-")


def assemble_bundle(out_dir: str | Path, *, kmz: str | Path, db: str | Path,
                    json_files: Optional[list[str | Path]] = None,
                    objects_json: Optional[dict[str, str | Path]] = None,
                    raw_files: Optional[list[str | Path]] = None,
                    kind: str, objects: list[str],
                    primary_cad_number: Optional[str] = None,
                    extract_date: Optional[str] = None,
                    etp_layer_present: Optional[bool] = None,
                    lot: Optional[dict[str, Any]] = None,
                    generated_at: Optional[str] = None,
                    **manifest_kw: Any) -> dict[str, Any]:
    """Собрать каталог Bundle в `out_dir` и записать `manifest.json`.

    kmz/db — обязательны (project.kmz/db.sqlite). `json_files` → json/<имя>;
    `objects_json` {cad: путь} → json/objects/<cad>.json; `raw_files` → raw/<имя>.
    Возвращает manifest-словарь. Бросает ValueError, если manifest невалиден.
    """
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    entries: list[dict[str, Any]] = []

    def add(src: str | Path, arc: str) -> None:
        _copy(src, root / arc)
        entries.append(_bm.file_entry(root / arc, arcname=arc))

    add(kmz, "project.kmz")
    add(db, "db.sqlite")
    for p in (json_files or []):
        add(p, f"json/{Path(p).name}")
    for cad, p in (objects_json or {}).items():
        add(p, f"json/objects/{mask_cad(cad)}.json")   # Windows-safe (КН без `:`)
    for p in (raw_files or []):
        add(p, f"raw/{Path(p).name}")

    # Детерминированный порядок files[] (по path).
    entries.sort(key=lambda e: e["path"])

    manifest = _bm.build_manifest(
        kind=kind, files=entries, objects=objects,
        primary_cad_number=primary_cad_number, extract_date=extract_date,
        etp_layer_present=etp_layer_present, lot=lot,
        generated_at=generated_at, **manifest_kw)

    errs = _bm.validate_manifest(manifest)
    if errs:
        raise ValueError("невалидный manifest: " + "; ".join(errs))

    (root / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8")
    return manifest


def verify_bundle(out_dir: str | Path) -> list[str]:
    """Проверить собранный каталог: manifest валиден, файлы существуют и sha256
    совпадают. Возвращает список расхождений ([] = целостен)."""
    root = Path(out_dir)
    mpath = root / "manifest.json"
    if not mpath.exists():
        return ["нет manifest.json"]
    manifest = json.loads(mpath.read_text(encoding="utf-8"))
    errs = _bm.validate_manifest(manifest)
    for fe in manifest.get("files", []):
        fp = root / fe["path"]
        if not fp.exists():
            errs.append(f"{fe['path']}: файл отсутствует")
            continue
        actual = _bm.sha256_file(fp)
        if actual != fe.get("sha256"):
            errs.append(f"{fe['path']}: sha256 не совпадает")
    return errs
