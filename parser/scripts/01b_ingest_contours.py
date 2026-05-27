"""
01b_ingest_contours.py — идемпотентный сборщик контуров → `_data/contours.json`

Читает выводы `01_parsing_nspd_v8.py` (session_export_*.json, snapshot_*.json,
per-object `<cn>.json`) и собирает все `info["Контур"]` в единый sidecar
`<project>/_data/contours.json`.

Идемпотентность — priority-based upgrade-merge: если для cn уже есть запись
с источником лучшего качества (wfs > pkk > screenshot_cv), новая запись не
затирает её. Это гарантирует, что повторный запуск парсера без WFS-доступа
не похоронит хорошие данные предыдущего прогона.

Источник истины schemы — `obsidian/Decisions/2026-05-25-contour-sidecar-architecture.md`.

Usage:
  python 01b_ingest_contours.py --project /path/to/project
  python 01b_ingest_contours.py --project . --sources session_export_*.json
  python 01b_ingest_contours.py --project . --dry-run            # только лог, не пишет
  python 01b_ingest_contours.py --project . --reset              # стереть и собрать заново
"""
import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

SCHEMA_VERSION = "1.0"

# Приоритет источников (см. ADR §3). Чем выше — тем «лучше» контур.
SOURCE_PRIORITY = {
    "manual": 1000,
    "wfs": 800,
    "pkk": 700,
    "network_capture": 600,
    "ol_state": 500,
    "screenshot_cv": 300,
}

# Кадастровый номер: 11:22:3333333:N  или  11:22:3333333:N/M (часть)
CN_RE = re.compile(r"^\d{1,2}:\d{1,2}:\d{1,7}:\d+(?:/\d+)?$")

# Имена per-object файлов от v8: <cn-mask>.json (двоеточия → '_', '/' → '-')
PER_OBJECT_NAME_RE = re.compile(
    r"^(?P<cn>\d{1,2}_\d{1,2}_\d{1,7}_\d+(?:-\d+)?)\.json$"
)

# Источник истины
ALG_VERSION = "ingest-v1.0"


def _utcnow_iso():
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _normalize_cn(cn_or_mask: str) -> str | None:
    """`23_50_0301004_25` или `23:50:0301004:25` → `23:50:0301004:25`. None если не КН."""
    if not cn_or_mask:
        return None
    s = cn_or_mask.strip()
    # mask из v8 snapshot files: '23_50_0301004_25' / '23_50_0301004_25-9'
    if "_" in s and ":" not in s:
        s = s.replace("_", ":", 3)
        s = s.replace("-", "/", 1)
    if CN_RE.match(s):
        return s
    return None


def _source_priority(payload: dict) -> int:
    src = (payload or {}).get("источник") or ""
    return SOURCE_PRIORITY.get(src, 0)


def _alg_version_key(payload: dict) -> tuple:
    """`v8.5` → (8, 5). Для сравнения свежести при равных приоритетах."""
    v = (payload or {}).get("алгоритм_версия") or ""
    m = re.match(r"v?(\d+)\.(\d+)", v)
    if not m:
        return (0, 0)
    return (int(m.group(1)), int(m.group(2)))


def _should_upgrade(existing: dict, candidate: dict) -> tuple[bool, str]:
    """Возвращает (upgrade?, reason)."""
    if existing is None:
        return True, "new"
    pe, pc = _source_priority(existing), _source_priority(candidate)
    if pc > pe:
        return True, f"priority {pc} > {pe} ({candidate.get('источник')} > {existing.get('источник')})"
    if pc < pe:
        return False, f"priority {pc} < {pe} (keep {existing.get('источник')})"
    # Равные приоритеты — берём свежее по версии алгоритма.
    ve, vc = _alg_version_key(existing), _alg_version_key(candidate)
    if vc > ve:
        return True, f"alg {candidate.get('алгоритм_версия')} > {existing.get('алгоритм_версия')}"
    if vc < ve:
        return False, f"alg {candidate.get('алгоритм_версия')} < {existing.get('алгоритм_версия')}"
    # При полном равенстве — оставляем существующее (детерминизм).
    return False, "tie, keep existing"


def _strip_payload(c: dict) -> dict:
    """Оставляет в записи только поля, релевантные sidecar'у (без internal v8-меток).
    Защищает от случайного запихивания debug-полей."""
    keep = {
        "источник", "тип", "полигонов", "колец_всего",
        "площадь_заявленная_кв_м", "площадь_вычисленная_кв_м",
        "коэф_коррекции_масштаба", "центроид",
        "geojson", "полигоны", "локальные_метры",
        "scale_bar_px", "scale_bar_m", "м_на_пиксель",
        "алгоритм_версия",
        # Метаданные WFS/PKK source (можно полезно для debug):
        "wfs_layer_id", "wfs_field", "wfs_method",
        "pkk_url", "pkk_kind", "capture_url",
    }
    return {k: v for k, v in c.items() if k in keep}


def _iter_contour_records(data: dict):
    """Из любого v8-output'а (session_export, snapshot, per-object) выдаёт
    последовательность (cn, payload, source_label)."""
    if not isinstance(data, dict):
        return

    # 1) session_export: {"data": {<category>: {<cn>: info}}, "metadata": ...}
    if isinstance(data.get("data"), dict) and "metadata" in data:
        for category, objs in data["data"].items():
            if not isinstance(objs, dict):
                continue
            for cn, info in objs.items():
                contour = (info or {}).get("Контур") if isinstance(info, dict) else None
                if contour:
                    yield cn, contour, f"session_export:{category}"
        return

    # 2) snapshot ИЛИ per-object: на верхнем уровне может быть либо
    #    {<category>: {<cn>: info}} (snapshot/per-object от v8 с категорией),
    #    либо {<cn>: info} (per-object — реально v8 пишет именно так).
    #    Различаем по тому, является ли ключ верхнего уровня кадастровым номером.
    for top_key, top_val in data.items():
        if not isinstance(top_val, dict):
            continue
        # 2a) top_key — это КН → per-object формат {cn: info}
        if _normalize_cn(top_key):
            contour = top_val.get("Контур")
            if contour:
                yield top_key, contour, "per_object"
            continue
        # 2b) top_key — category, top_val — {cn: info}
        for cn, info in top_val.items():
            if not isinstance(info, dict):
                continue
            contour = info.get("Контур")
            if contour:
                yield cn, contour, f"snapshot:{top_key}"


def load_existing(sidecar_path: Path) -> dict:
    """Читает существующий contours.json или возвращает пустой скелет.
    schema_version всегда поднимается до актуального SCHEMA_VERSION
    (раньше setdefault замораживал старую версию навсегда)."""
    if not sidecar_path.exists():
        return {"schema_version": SCHEMA_VERSION, "ingested_at": None, "objects": {}}
    try:
        data = json.loads(sidecar_path.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"  [!] не смог прочитать существующий {sidecar_path.name}: {e} — стартую с пустого")
        return {"schema_version": SCHEMA_VERSION, "ingested_at": None, "objects": {}}
    old_version = data.get("schema_version")
    if old_version != SCHEMA_VERSION:
        print(f"  [migrate] schema_version {old_version!r} → {SCHEMA_VERSION!r}")
        data["schema_version"] = SCHEMA_VERSION
    data.setdefault("ingested_at", None)
    data.setdefault("objects", {})
    return data


def find_source_files(project: Path, patterns: list[str]) -> list[Path]:
    """Список файлов-кандидатов в project'е.
    Спецпаттерн `__per_object__` раскрывается в файлы, у которых имя матчит
    PER_OBJECT_NAME_RE (точное «КН-mask» формата, без ложных срабатываний на
    случайные `foo_bar_baz_qux.json`)."""
    files = []
    seen = set()
    for pat in patterns:
        if pat == "__per_object__":
            for p in list(project.glob("*.json")) + list((project / "_data" / "nspd_cache").glob("*.json")):
                if not p.is_file() or p in seen:
                    continue
                if PER_OBJECT_NAME_RE.match(p.name):
                    seen.add(p)
                    files.append(p)
            continue
        for p in project.glob(pat):
            if p.is_file() and p.suffix.lower() == ".json" and p not in seen:
                seen.add(p)
                files.append(p)
    return sorted(files)


def ingest_one(records, file_path: Path, sink: dict, stats: dict):
    """Применяет upgrade-merge к sink["objects"] для записей из одного файла.

    Side-effect-free относительно диска: только обновляет in-memory `sink`.
    dry-run применяется на write-step в main() — здесь симуляция всегда
    полная, иначе порядок обработки файлов даёт ложные upgrade-reports."""
    objects = sink.setdefault("objects", {})
    now = _utcnow_iso()
    for cn, contour, src_label in records:
        cn_norm = _normalize_cn(cn)
        if not cn_norm:
            stats["skipped_bad_cn"] += 1
            continue
        if not isinstance(contour, dict):
            stats["skipped_bad_contour"] += 1
            continue
        candidate = _strip_payload(contour)
        existing = objects.get(cn_norm)
        do, reason = _should_upgrade(existing, candidate)
        if do:
            candidate = dict(candidate)
            candidate["_ingested_at"] = now
            candidate["_source_file"] = file_path.name
            candidate["_source_label"] = src_label
            objects[cn_norm] = candidate
            stats["upgraded"].append((cn_norm, reason))
        else:
            stats["kept"].append((cn_norm, reason))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--project", required=True, help="Корень проекта (с _data/)")
    ap.add_argument("--sources", nargs="*", default=[
        "session_export_*.json",
        "snapshot_*.json",
        "__per_object__",          # spec-token: файлы вида 23_50_0301004_25.json и 23_50_0301004_25-9.json
        "_data/nspd_cache/*.json",
    ], help="Glob-паттерны для поиска input-файлов. "
            "Спецтокен `__per_object__` ищет файлы, чьё имя матчит формат КН-маски.")
    ap.add_argument("--dry-run", action="store_true", help="Не писать contours.json, только лог")
    ap.add_argument("--reset", action="store_true", help="Стереть существующий sidecar перед ingest")
    args = ap.parse_args()

    project = Path(args.project).resolve()
    data_dir = project / "_data"
    if not data_dir.exists():
        print(f"[!] {data_dir} не существует. Сначала запусти 07_init_project.")
        sys.exit(1)

    sidecar = data_dir / "contours.json"

    if args.reset and sidecar.exists() and not args.dry_run:
        print(f"[reset] удаляю {sidecar.name}")
        sidecar.unlink()

    sink = {"schema_version": SCHEMA_VERSION, "ingested_at": None, "objects": {}} \
        if args.reset else load_existing(sidecar)
    # snapshot для byte-level идемпотентности: top-level ingested_at обновляется
    # только если objects реально менялись.
    initial_objects = json.dumps(sink.get("objects", {}), sort_keys=True, ensure_ascii=False)

    sources = find_source_files(project, args.sources)
    if not sources:
        print(f"[i] нет input-файлов в {project} по паттернам {args.sources}")
        # Всё равно создаём пустой скелет, чтобы downstream не падал
        if not sidecar.exists() and not args.dry_run:
            sink["ingested_at"] = _utcnow_iso()
            sidecar.write_text(json.dumps(sink, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"[+] создан пустой скелет {sidecar}")
        return 0

    print(f"[i] project: {project}")
    print(f"[i] sources: {len(sources)} файл(а/ов)")
    for p in sources[:20]:
        print(f"    {p.relative_to(project) if p.is_relative_to(project) else p}")
    if len(sources) > 20:
        print(f"    ... ещё {len(sources) - 20}")

    stats = {
        "files_read": 0, "files_failed": 0,
        "records_seen": 0,
        "skipped_bad_cn": 0, "skipped_bad_contour": 0,
        "upgraded": [], "kept": [],
    }

    for path in sources:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"  [!] {path.name}: parse error {e.__class__.__name__}")
            stats["files_failed"] += 1
            continue
        stats["files_read"] += 1
        records = list(_iter_contour_records(data))
        stats["records_seen"] += len(records)
        ingest_one(records, path, sink, stats)

    final_objects = json.dumps(sink.get("objects", {}), sort_keys=True, ensure_ascii=False)
    changed = (final_objects != initial_objects)
    if changed:
        sink["ingested_at"] = _utcnow_iso()
    # иначе оставляем старый top-level ingested_at — файл побитово не меняется

    n_objs = len(sink["objects"])
    print(f"\n[i] результат:")
    print(f"    файлов прочитано: {stats['files_read']} (ошибок: {stats['files_failed']})")
    print(f"    записей с контуром: {stats['records_seen']}")
    print(f"    upgraded: {len(stats['upgraded'])}")
    print(f"    kept (lower priority): {len(stats['kept'])}")
    print(f"    skipped (bad cn): {stats['skipped_bad_cn']}")
    print(f"    skipped (bad contour): {stats['skipped_bad_contour']}")
    print(f"    итого объектов в sidecar: {n_objs}")

    by_source = {}
    for cn, payload in sink["objects"].items():
        src = payload.get("источник", "?")
        by_source[src] = by_source.get(src, 0) + 1
    if by_source:
        print(f"    по источникам:")
        for src, cnt in sorted(by_source.items(), key=lambda x: -x[1]):
            print(f"      {src:>18}: {cnt}")

    if args.dry_run:
        print(f"\n[dry-run] {sidecar.name} НЕ записан (changed={changed})")
        return 0

    if not changed and sidecar.exists():
        print(f"\n[i] {sidecar.name} не изменён (идемпотентный no-op)")
        return 0

    sidecar.write_text(json.dumps(sink, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[+] записан {sidecar}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
