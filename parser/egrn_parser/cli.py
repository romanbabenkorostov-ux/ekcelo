"""
egrn_parser/cli.py — командный интерфейс (CLI).

Точки входа:
  python -m egrn_parser [command]
  egrn-parser [command]

Команды (ТЗ раздел 13.1):
  parse    — парсинг входных файлов/папок
  enrich   — обогащение из ОСВ / шаблона / DOCX
  merge    — слияние новых данных с существующей БД
  export   — экспорт SQLite → XLSX / JSON / graph.json
  monitor  — мониторинг объектов
  validate — проверка целостности БД
  migrate  — миграция v1.9 → v1.10
  dict-load — загрузка словарей
  serve    — запуск FastAPI
  folders  — управление папками (create / distribute / validate)
"""

from __future__ import annotations

import argparse
import logging
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

from egrn_parser import __version__
from egrn_parser.config import make_run_id, ensure_output_dirs, LOGS_DIR, OUTPUT_DIR
from egrn_parser.utils.colored_output import (
    cp, print_ok, print_err, print_warn, print_info, print_head, print_sep, Colors,
)

log = logging.getLogger("egrn_parser")


# ─────────────────────────────────────────────────────────────────────────────
#  Настройка логирования
# ─────────────────────────────────────────────────────────────────────────────

def _setup_logging(level: str = "INFO") -> None:
    ensure_output_dirs()
    numeric = getattr(logging, level.upper(), logging.INFO)
    fmt = "%(asctime)s %(levelname)s %(name)s — %(message)s"
    logging.basicConfig(
        level=numeric,
        format=fmt,
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler(LOGS_DIR / "parser.log", encoding="utf-8"),
        ],
    )


# ─────────────────────────────────────────────────────────────────────────────
#  Команды
# ─────────────────────────────────────────────────────────────────────────────

def cmd_parse(args: argparse.Namespace) -> int:
    """Разобрать входные файлы и сохранить в SQLite."""
    from egrn_parser.db.connection import init_db, check_db
    from egrn_parser.db.seeds import load_dictionaries
    from egrn_parser.parsers.pdf_parser import is_egrn_pdf, parse_egrn_pdf
    from egrn_parser.parsers.xml_parser import parse_egrn_xml
    from egrn_parser.parsers.osv_parser import is_osv_xlsx, parse_osv_xlsx
    from egrn_parser.parsers.docx_parser import parse_docx_inventory
    from egrn_parser.parsers.spravka_parser import (
        is_spravka_docx, parse_spravka_docx,
        is_perechen_docx, parse_perechen_docx,
    )
    from egrn_parser.parsers.xlsx_template_parser import is_assets_template, parse_xlsx_template
    from egrn_parser.utils.filename_filter import is_photo_report
    from egrn_parser.merge.upsert import save_parsed_result, save_osv_result
    from egrn_parser.merge.cad_resolver import resolve_cad_fragments_interactive
    from egrn_parser.monitoring.change_detector import detect_changes
    from egrn_parser.merge.interactive import ask_diff_action

    db_path  = Path(args.db)
    run_id   = make_run_id()
    policy   = args.on_conflict or "ask"

    print_head(f"egrn_parser v{__version__} — ПАРСИНГ")
    print_info(f"БД: {db_path}")

    # Инициализация БД
    if not check_db(db_path):
        print_info("Инициализация новой БД...")
        init_db(db_path)
        load_dictionaries(db_path)
        print_ok("БД создана и заполнена словарями")

    # Сбор входных файлов
    input_paths: list[Path] = []
    if args.input:
        inp = Path(args.input)
        if inp.is_dir():
            input_paths = _scan_directory(inp)
        elif inp.is_file():
            input_paths = [inp]

    # Фильтрация фотоотчётов
    accepted = []
    skipped  = []
    for p in input_paths:
        if p.suffix.lower() in (".docx", ".doc") and is_photo_report(p):
            skipped.append(p)
            print_warn(f"Фотоотчёт пропущен: {p.name}")
        else:
            accepted.append(p)

    # Вывод статистики сканирования
    _print_scan_summary(accepted)

    if not accepted:
        print_warn("Не найдено файлов для парсинга.")
        return 0

    # Обработка
    stats_total = {"inserted": 0, "replaced": 0, "skipped": 0, "rights": 0, "errors": 0}

    include_acc = getattr(args, "accessories", False)
    decisions_log = LOGS_DIR / "interactive_decisions.jsonl"

    for p in accepted:
        suffix = p.suffix.lower()
        print_info(f"→ {p.name}")

        try:
            if suffix == ".pdf" and is_egrn_pdf(p):
                parsed = parse_egrn_pdf(p)
                if not parsed:
                    print_warn(f"  Не удалось разобрать: {p.name}")
                    stats_total["errors"] += 1
                    continue

                # Проверить изменения
                changes = detect_changes(db_path, parsed)
                if changes["has_changes"] and changes["action"] == "replace":
                    action = ask_diff_action(
                        parsed["cad_number"],
                        parsed["object"].get("name", ""),
                        changes["changed_fields"],
                        decisions_log_path=decisions_log,
                        policy=policy,
                    )
                    if action == "skip":
                        stats_total["skipped"] += 1
                        continue
                    # При выборе «enrich» с несколькими полями — уточняем по каждому
                    if action == "enrich" and len(changes["changed_fields"]) > 1:
                        action = "ask_enrich"
                elif changes["action"] == "skip":
                    print_info(f"  Без изменений, пропуск: {parsed['cad_number']}")
                    stats_total["skipped"] += 1
                    continue

                st = save_parsed_result(db_path, parsed, policy=action if 'action' in dir() else policy)
                for k, v in st.items():
                    stats_total[k] = stats_total.get(k, 0) + v
                print_ok(f"  ✓ {parsed['cad_number']} ({parsed['object_type']})")

            elif suffix == ".xml":
                parsed = parse_egrn_xml(p)
                if not parsed:
                    stats_total["errors"] += 1
                    continue
                st = save_parsed_result(db_path, parsed, policy=policy)
                for k, v in st.items():
                    stats_total[k] = stats_total.get(k, 0) + v
                print_ok(f"  ✓ {parsed['cad_number']} (XML)")

            elif suffix in (".xlsx", ".xls") and is_osv_xlsx(p):
                osv_data = parse_osv_xlsx(p, include_accessories=include_acc)
                for w in osv_data.get("warnings", []):
                    print_warn(f"  ОСВ: {w}")
                # Интерактивное сопоставление частичных кадастровых номеров
                if include_acc and any(a.get("cad_number_fragment") for a in osv_data.get("accessories", [])):
                    osv_data["accessories"] = resolve_cad_fragments_interactive(
                        db_path, osv_data["accessories"], policy=policy
                    )
                st = save_osv_result(db_path, osv_data, include_accessories=include_acc)
                print_ok(
                    f"  ✓ ОСВ: {st['accessories']} принадлежностей, "
                    f"{st['valuations']} оценок"
                )

            elif suffix in (".docx", ".doc"):
                if is_perechen_docx(p):
                    per = parse_perechen_docx(p)
                    _save_perechen_result(db_path, per)
                    print_ok(
                        f"  ✓ Перечень: {len(per['land_leases'])} ЗУ (аренда), "
                        f"{len(per['building_enrichments'])} ОКС (данные)"
                    )
                elif is_spravka_docx(p):
                    spr = parse_spravka_docx(p)
                    _save_spravka_result(db_path, spr)
                    print_ok(
                        f"  ✓ Справка: {len(spr['lease_intentions'])} аренд ЗУ, "
                        f"{len(spr['building_statuses'])} ОКС"
                    )
                else:
                    inv_data = parse_docx_inventory(p)
                    for w in inv_data.get("warnings", []):
                        print_warn(f"  DOCX: {w}")
                    print_ok(f"  ✓ DOCX-перечень: {len(inv_data.get('objects', []))} объектов")

            elif suffix in (".xlsx", ".xls") and is_assets_template(p):
                tmpl = parse_xlsx_template(p)
                print_ok(
                    f"  ✓ Шаблон Assets: {len(tmpl['land_rows'])} ЗУ, "
                    f"{len(tmpl['building_rows'])} зданий"
                )

        except KeyboardInterrupt:
            print_warn("Прервано пользователем")
            break
        except Exception as e:
            print_err(f"  ✗ Ошибка обработки {p.name}: {e}")
            log.exception("Ошибка обработки %s", p.name)
            stats_total["errors"] += 1

    print_sep()
    print_ok(f"Итого: вставлено={stats_total['inserted']}, "
             f"обновлено={stats_total['replaced']}, "
             f"пропущено={stats_total['skipped']}, "
             f"прав={stats_total['rights']}, "
             f"ошибок={stats_total['errors']}")

    # Авто-обогащение
    _run_enrichers(db_path)

    return 0 if stats_total["errors"] == 0 else 1


def _run_enrichers(db_path: Path) -> None:
    """Запустить обогащение после парсинга."""
    from egrn_parser.enrichers.room_parent_resolver import resolve_room_parent
    n = resolve_room_parent(db_path)
    if n:
        print_ok(f"Этажность подтянута к {n} помещениям")



def _save_perechen_result(db_path, per: dict) -> None:
    """Сохранить данные Перечня: аренды ЗУ → rights, обогащение зданий → building_objects."""
    from egrn_parser.db.connection import get_connection
    from egrn_parser.merge.upsert import upsert_right

    with get_connection(db_path) as conn:
        conn.execute("BEGIN")
        # 1. Аренды ЗУ (с реальными датами)
        for lease in per.get("land_leases", []):
            cad = lease.get("cad_number")
            if not cad:
                continue
            right = {
                "object_class":      "land",
                "object_key_type":   "cad_number",
                "object_key_value":  cad,
                "right_category":    "encumbrance",
                "right_type":        "Аренда",
                "right_type_code":   "lease",
                "valid_from":        lease.get("valid_from"),
                "valid_until":       lease.get("valid_until"),
                "lease_term_description": lease.get("lease_period_raw"),
                "beneficiary_inn":   lease.get("beneficiary_inn"),
                "source_format":     "docx_perechen",
            }
            upsert_right(conn, right)

        # 2. Обогащение зданий (functional_name, floors, year из перечня)
        for bldg in per.get("building_enrichments", []):
            cad = bldg.get("cad_number")
            if not cad:
                continue
            updates = {}
            if bldg.get("functional_name"):
                updates["name"] = bldg["functional_name"]
            if bldg.get("floors_from_perechen") and bldg["floors_from_perechen"] < 200:
                updates["floors_total"] = bldg["floors_from_perechen"]
            if bldg.get("year_built_from_perechen"):
                updates["year_built"] = bldg["year_built_from_perechen"]
            if updates:
                set_clause = ", ".join(f"{k} = COALESCE({k}, ?)" for k in updates)
                conn.execute(
                    f"UPDATE building_objects SET {set_clause}, updated_at=datetime('now') WHERE cad_number=?",
                    list(updates.values()) + [cad],
                )
        conn.execute("COMMIT")


def _save_spravka_result(db_path, spr: dict) -> None:
    """Сохранить данные из Справки в БД: аренды ЗУ как rights(encumbrance) + user_notes для ОКС."""
    from egrn_parser.db.connection import get_connection
    from egrn_parser.merge.upsert import upsert_right
    import json

    with get_connection(db_path) as conn:
        conn.execute("BEGIN")
        for lease in spr.get("lease_intentions", []):
            cad = lease.get("cad_number")
            if not cad:
                continue
            right = {
                "object_class":      "land",
                "object_key_type":   "cad_number",
                "object_key_value":  cad,
                "right_category":    "encumbrance",
                "right_type":        "Аренда (планируемая)",
                "right_type_code":   "lease",
                "valid_until":       lease.get("lease_deadline_date"),
                "lease_term_description": lease.get("lease_deadline_text") or lease.get("lease_deadline_date"),
                "beneficiary_inn":   lease.get("beneficiary_inn"),
                "basis":             lease.get("comment"),
                "source_format":     "docx_spravka",
                "source_extract_number": None,
            }
            upsert_right(conn, right)

        # Обновить user_notes для ОКС из таблицы статусов
        for bldg in spr.get("building_statuses", []):
            cad = bldg.get("cad_number")
            status = bldg.get("doc_status")
            if cad and status:
                conn.execute(
                    "UPDATE building_objects SET updated_at=datetime('now') WHERE cad_number=?",
                    (cad,)
                )
        conn.execute("COMMIT")


def cmd_export(args: argparse.Namespace) -> int:
    """Экспорт SQLite → XLSX / JSON / graph.json."""
    from egrn_parser.exporters.xlsx_exporter import export_xlsx
    from egrn_parser.exporters.json_exporter import export_json
    from egrn_parser.exporters.graph_json import export_graph_json

    db_path = Path(args.db)
    run_id  = make_run_id()
    out_dir = Path(args.output) if hasattr(args, "output") and args.output else OUTPUT_DIR
    out_dir.mkdir(parents=True, exist_ok=True)

    print_head("egrn_parser — ЭКСПОРТ")

    # XLSX
    xlsx_path = Path(args.xlsx) if getattr(args, "xlsx", None) else out_dir / f"egrn_{run_id}.xlsx"
    tmpl = getattr(args, "xlsx_template", None)
    print_info(f"XLSX → {xlsx_path.name}")
    export_xlsx(db_path, xlsx_path, template_path=tmpl)
    print_ok(f"XLSX сохранён: {xlsx_path}")

    # JSON
    json_path = Path(args.json) if getattr(args, "json", None) else out_dir / f"egrn_{run_id}.json"
    print_info(f"JSON → {json_path.name}")
    export_json(db_path, json_path, run_id=run_id)
    print_ok(f"JSON сохранён: {json_path}")

    # graph.json
    graph_path = (Path(args.graph_json) if getattr(args, "graph_json", None)
                  else out_dir / "graph.json")
    print_info(f"graph.json → {graph_path.name}")
    export_graph_json(db_path, graph_path, run_id=run_id)
    print_ok(f"graph.json сохранён: {graph_path}")

    return 0


def cmd_migrate(args: argparse.Namespace) -> int:
    """Миграция БД v1.9 → v1.10."""
    from egrn_parser.db.migrations import migrate, rollback

    db_path = Path(args.db)
    if getattr(args, "rollback", False):
        print_info(f"Откат БД: {db_path}")
        rollback(db_path)
        print_ok("Откат выполнен")
    else:
        print_info(f"Миграция: {db_path}")
        migrate(db_path, backup=True)
        print_ok("Миграция v1.9 → v1.10 завершена")
    return 0


def cmd_dict_load(args: argparse.Namespace) -> int:
    """Загрузить словари в code_dictionary."""
    from egrn_parser.db.seeds import load_dictionaries

    db_path = Path(args.db)
    n = load_dictionaries(db_path)
    print_ok(f"Загружено {n} записей в code_dictionary")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    """Проверить целостность БД."""
    from egrn_parser.db.connection import check_db, get_connection
    from egrn_parser.utils.personal_data_filter import assert_no_personal_data

    db_path = Path(args.db)
    print_head("Валидация БД")

    if not check_db(db_path):
        print_err("БД не найдена или некорректна")
        return 1

    errors = 0
    with get_connection(db_path, readonly=True) as conn:
        # Проверка 1: нет персональных данных
        print_info("Проверка персональных данных...")
        for table in ("land_objects", "building_objects", "rights", "right_holders"):
            rows = conn.execute(f"SELECT * FROM {table} LIMIT 100").fetchall()
            for row in rows:
                try:
                    assert_no_personal_data(dict(row))
                except AssertionError as e:
                    print_err(f"Таблица {table}: {e}")
                    errors += 1

        # Проверка 2: целостность ссылок
        print_info("Проверка целостности FK...")
        orphan_rights = conn.execute(
            """
            SELECT COUNT(*) AS cnt FROM rights
            WHERE object_key_type = 'cad_number'
              AND object_key_value NOT IN
                  (SELECT cad_number FROM land_objects UNION
                   SELECT cad_number FROM building_objects)
            """
        ).fetchone()["cnt"]
        if orphan_rights > 0:
            print_warn(f"Права без объекта: {orphan_rights}")

        # Проверка 3: version
        ver = conn.execute(
            "SELECT value FROM system_meta WHERE key='schema_version'"
        ).fetchone()
        if ver:
            print_ok(f"Версия схемы: {ver['value']}")
        else:
            print_warn("system_meta.schema_version отсутствует")
            errors += 1

    if errors == 0:
        print_ok("Валидация пройдена")
        return 0
    else:
        print_err(f"Валидация завершена с {errors} ошибками")
        return 1


def cmd_enrich(args: argparse.Namespace) -> int:
    """Обогащение из внешних источников."""
    db_path = Path(args.db)
    print_head("Обогащение данных")
    _run_enrichers(db_path)
    print_ok("Обогащение завершено")
    return 0


def cmd_monitor(args: argparse.Namespace) -> int:
    """Запустить мониторинг."""
    from egrn_parser.monitoring.runner import run_monitoring_cycle

    db_path = Path(args.db)
    print_head("Мониторинг")
    cad_numbers = args.cad_numbers.split(",") if getattr(args, "cad_numbers", None) else None
    stats = run_monitoring_cycle(db_path, cad_numbers=cad_numbers,
                                 dry_run=getattr(args, "dry_run", False))
    print_ok(f"Проверено: {stats['checked']}, изменений: {stats['changed']}, ошибок: {stats['errors']}")
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    """Запустить FastAPI сервер."""
    try:
        import uvicorn
        from egrn_parser.api import app

        host = getattr(args, "host", "127.0.0.1")
        port = getattr(args, "port", 8000)
        print_head(f"FastAPI сервер: http://{host}:{port}")
        uvicorn.run(app, host=host, port=port)
    except ImportError:
        print_err("Для запуска сервера установите: pip install uvicorn fastapi")
        return 1
    return 0


def cmd_bundle(args: argparse.Namespace) -> int:
    """Собрать Bundle-каталог (C3): project.kmz + db.sqlite + json/[+raw] + manifest.json.

    Состав лота читается из --db по --lot-id (lot_assembler); флаг §6 — etp_merge.
    """
    import datetime as _dt
    import sqlite3

    from egrn_parser import bundle_assembler as _BA
    from egrn_parser import etp_merge as _EM
    from egrn_parser import lot_assembler as _LA

    kind = args.kind
    objects = list(args.objects or [])
    lot_fragment = None
    if getattr(args, "lot_id", None):
        with sqlite3.connect(args.db) as _c:
            lot_fragment = _LA.lot_manifest(_c, args.lot_id,
                                            as_of=getattr(args, "extract_date", None))
        objects = lot_fragment["members"]
        kind = "lot"

    with sqlite3.connect(args.db) as _c:
        etp = _EM.etp_layer_present(_c)

    # В Bundle кладём C2-совместимую БД (ADR-007): если --export-c2 — конвертируем
    # рабочую БД парсера в C2-формат и пакуем её; иначе — БД как есть.
    db_for_bundle = args.db
    if getattr(args, "export_c2", False):
        import tempfile as _tmp

        from egrn_parser import schema_export as _SE
        db_for_bundle = Path(_tmp.mkdtemp(prefix="ekcelo_c2_")) / "db.sqlite"
        _SE.export_to_c2(args.db, db_for_bundle)
        print(f"[bundle] db.sqlite экспортирована в C2-формат: {db_for_bundle}")

    objects_json = None
    if getattr(args, "objects_json_dir", None):
        objects_json = {p.stem: p for p in Path(args.objects_json_dir).glob("*.json")}

    ts = _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()
    try:
        manifest = _BA.assemble_bundle(
            args.out, kmz=args.kmz, db=db_for_bundle,
            json_files=list(args.json or []), objects_json=objects_json,
            raw_files=list(args.raw or []), kind=kind, objects=objects,
            primary_cad_number=getattr(args, "primary_cad", None),
            extract_date=getattr(args, "extract_date", None),
            etp_layer_present=etp, lot=lot_fragment, generated_at=ts)
    except (ValueError, OSError) as exc:
        print(f"[bundle] ошибка: {exc}", file=sys.stderr)
        return 1

    print(f"[bundle] собран: {args.out}  kind={manifest['kind']}  "
          f"файлов={len(manifest['files'])}  объектов={len(manifest['objects'])}"
          f"  etp_layer={manifest.get('etp_layer_present')}")
    return 0


def cmd_ingest_project(args: argparse.Namespace) -> int:
    """Загрузить всю папку заполненных шаблонов в БД одним вызовом (идемпотентно)."""
    import sqlite3

    from egrn_parser import project_ingest as _PI
    pmap = None
    if getattr(args, "pledge_map", None):
        try:
            pmap = {int(k): v for k, v in
                    (kv.split("=", 1) for kv in args.pledge_map.split(","))}
        except ValueError:
            print("[ingest-project] --pledge-map: формат «66=КН,69=КН»", file=sys.stderr)
            return 1
    conn = sqlite3.connect(args.db)
    try:
        rep = _PI.ingest_project(conn, args.dir, land_cad_by_pledge=pmap)
    finally:
        conn.close()
    print(f"[ingest-project] папка: {rep['dir']}")
    for f in rep["files"]:
        status = f.get("error") or f.get("result")
        print(f"    {f['file']:<30} {f['type']:<10} {status}")
    t = rep["totals"]
    print(f"  итого файлов: {t['files']}  по типам: {t['by_type']}  ошибок: {t['errors']}")
    return 1 if t["errors"] else 0


def cmd_kmz(args: argparse.Namespace) -> int:
    """Собрать KMZ объектов в пределах ЗУ: контуры если есть, иначе точки по спирали."""
    import sqlite3

    from egrn_parser import geo_kmz as _K
    cads = [c.strip() for c in args.parcels.replace(";", ",").split(",") if c.strip()]
    if not cads:
        print("[kmz] укажите --parcels «КН1,КН2,…»", file=sys.stderr)
        return 1
    modes = [m.strip() for m in (args.objects or "").split(",") if m.strip()] or _K.DEFAULT_MODES
    bsrc = [s.strip() for s in (getattr(args, "buildings", "") or "").split(",")
            if s.strip()] or _K.DEFAULT_BUILDING_SOURCES
    extra = [c.strip() for c in (getattr(args, "building_cads", "") or "").replace(";", ",").split(",")
             if c.strip()] or None
    fetcher = discovery = None
    if getattr(args, "nspd", False):
        from egrn_parser import geo_nspd as _N
        fetcher = _N.fetch_geometry                  # геометрия ЗУ/строений по КН (сеть)
        discovery = _N.discover_buildings            # обнаружение ОКС в границах ЗУ (источник 2)
    conn = sqlite3.connect(args.db)
    try:
        parcels = _K.collect_from_db(conn, cads, modes=modes, geometry_fetcher=fetcher,
                                     building_sources=bsrc, building_discovery=discovery,
                                     extra_building_cads=extra)
    finally:
        conn.close()
    res = _K.build_kmz(args.out, parcels)
    s = res["stats"]
    print(f"[kmz] {res['path']}")
    print(f"    ЗУ: {s['parcels']} (с границей: {s['parcels_with_geom']})  "
          f"объектов с контуром: {s['objects_with_contour']}  по спирали: {s['objects_spiral']}")
    if s["parcels_with_geom"] < s["parcels"]:
        print("    ⚠ у части ЗУ нет геометрии в БД — сначала загрузите контуры "
              "(ingest-project / 01c). Объекты таких ЗУ без геометрии не размещены.")
    return 0


def cmd_export_c2(args: argparse.Namespace) -> int:
    """Экспорт рабочей БД парсера в C2-формат (`schema/egrn_current_schema.sql`, ADR-007)."""
    from egrn_parser import schema_export as _SE
    try:
        counts = _SE.export_to_c2(args.db, args.out)
    except (OSError, ValueError) as exc:
        print(f"[export-c2] ошибка: {exc}", file=sys.stderr)
        return 1
    print(f"[export-c2] C2-БД: {args.out}")
    for t, n in counts.items():
        print(f"    {t:<22} {n}")
    return 0


def cmd_folders(args: argparse.Namespace) -> int:
    """Управление папками по кадастровым номерам."""
    subcmd = getattr(args, "folders_cmd", None)
    root   = Path(getattr(args, "root", "."))

    if subcmd == "create":
        cad_list = _read_cad_list(args)
        _folders_create(root, cad_list)
    elif subcmd == "distribute":
        src = Path(getattr(args, "source", "."))
        _folders_distribute(root, src)
    elif subcmd == "validate":
        _folders_validate(root)
    else:
        print_err("Укажите подкоманду: create, distribute, validate")
        return 1
    return 0


def _folders_create(root: Path, cad_list: list[str]) -> None:
    root.mkdir(parents=True, exist_ok=True)
    created = 0
    for cad in cad_list:
        folder = root / cad.replace(":", "_")
        folder.mkdir(exist_ok=True)
        created += 1
    print_ok(f"Создано папок: {created}")


def _folders_distribute(root: Path, source: Path) -> None:
    """Распределить файлы из source по папкам ЦКН в root."""
    from egrn_parser.parsers._common import CAD_NUMBER_RE
    moved = 0
    for f in source.iterdir():
        if not f.is_file():
            continue
        m = CAD_NUMBER_RE.search(f.name)
        if not m:
            print_warn(f"Нет кад. номера в имени: {f.name}")
            continue
        cad = m.group(1)
        target_dir = root / cad.replace(":", "_")
        target_dir.mkdir(exist_ok=True)
        target = target_dir / f.name
        f.rename(target)
        moved += 1
    print_ok(f"Перемещено файлов: {moved}")


def _folders_validate(root: Path) -> None:
    """Проверить соответствие имён папок и содержимого."""
    from egrn_parser.parsers._common import CAD_NUMBER_RE
    errors = 0
    for d in root.iterdir():
        if not d.is_dir():
            continue
        folder_cad = d.name.replace("_", ":").replace(".", ":")
        for f in d.iterdir():
            m = CAD_NUMBER_RE.search(f.name)
            if m and m.group(1) != folder_cad:
                print_warn(f"Несоответствие: папка {d.name}, файл {f.name} ({m.group(1)})")
                errors += 1
    if errors == 0:
        print_ok("Все папки и файлы согласованы")
    else:
        print_warn(f"Найдено несоответствий: {errors}")


def _read_cad_list(args) -> list[str]:
    if getattr(args, "cad_file", None):
        return Path(args.cad_file).read_text(encoding="utf-8").splitlines()
    if getattr(args, "cad_numbers", None):
        return args.cad_numbers.split(",")
    return []


def _scan_directory(root: Path) -> list[Path]:
    """Рекурсивно сканировать папку до 3 уровней."""
    from egrn_parser.config import PDF_MAX_FOLDER_DEPTH
    found: list[Path] = []
    for ext in ("*.pdf", "*.PDF", "*.xml", "*.XML", "*.xlsx", "*.XLSX", "*.docx", "*.DOCX", "*.doc"):
        found.extend(root.rglob(ext))
    return sorted(set(found))


def _print_scan_summary(paths: list[Path]) -> None:
    from collections import Counter
    ext_count = Counter(p.suffix.lower() for p in paths)
    print_sep("Найдено файлов:")
    for ext, cnt in sorted(ext_count.items()):
        print_info(f"  {ext:<8}: {cnt}")
    print_info(f"  Итого   : {len(paths)}")


# ─────────────────────────────────────────────────────────────────────────────
#  Парсер аргументов
# ─────────────────────────────────────────────────────────────────────────────

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="egrn-parser",
        description=f"egrn_parser v{__version__} — система парсинга выписок ЕГРН",
    )
    p.add_argument("--version", action="version", version=f"egrn_parser {__version__}")
    p.add_argument("--log-level", default="INFO", help="Уровень логирования (INFO/DEBUG/WARNING)")

    sub = p.add_subparsers(dest="command", required=False)

    # parse
    sp_parse = sub.add_parser("parse", help="Парсинг входных файлов/папок")
    sp_parse.add_argument("--input",  "-i", required=True, help="Файл или папка")
    sp_parse.add_argument("--db",     "-d", default="output/egrn.db", help="Путь к SQLite БД")
    sp_parse.add_argument("--output", "-o", default="output/", help="Папка для результатов")
    sp_parse.add_argument("--on-conflict", default="ask",
                          choices=["ask", "replace", "enrich", "new", "skip", "fail"],
                          help="Политика при конфликте данных")
    sp_parse.add_argument("--accessories", action="store_true", help="Сохранять принадлежности из ОСВ")
    sp_parse.set_defaults(func=cmd_parse)

    # export
    sp_export = sub.add_parser("export", help="Экспорт SQLite → XLSX / JSON / graph.json")
    sp_export.add_argument("--db",           "-d", required=True, help="SQLite БД")
    sp_export.add_argument("--output",       "-o", default="output/", help="Папка для файлов")
    sp_export.add_argument("--xlsx",         help="Путь к XLSX-файлу")
    sp_export.add_argument("--json",         help="Путь к JSON-файлу")
    sp_export.add_argument("--graph-json",   help="Путь к graph.json")
    sp_export.add_argument("--xlsx-template",help="Шаблон XLSX для листов 1–2")
    sp_export.set_defaults(func=cmd_export)

    # migrate
    sp_mig = sub.add_parser("migrate", help="Миграция БД v1.9 → v1.10")
    sp_mig.add_argument("--db", "-d", required=True)
    sp_mig.add_argument("--rollback", action="store_true", help="Откатить миграцию из бэкапа")
    sp_mig.set_defaults(func=cmd_migrate)

    # dict-load
    sp_dict = sub.add_parser("dict-load", help="Загрузка словарей в code_dictionary")
    sp_dict.add_argument("--db", "-d", required=True)
    sp_dict.set_defaults(func=cmd_dict_load)

    # validate
    sp_val = sub.add_parser("validate", help="Проверка целостности БД")
    sp_val.add_argument("--db", "-d", required=True)
    sp_val.set_defaults(func=cmd_validate)

    # enrich
    sp_enr = sub.add_parser("enrich", help="Обогащение данных")
    sp_enr.add_argument("--db", "-d", required=True)
    sp_enr.set_defaults(func=cmd_enrich)

    # monitor
    sp_mon = sub.add_parser("monitor", help="Мониторинг объектов")
    sp_mon.add_argument("--db",          "-d", required=True)
    sp_mon.add_argument("--cad-numbers", help="Список кад. номеров через запятую")
    sp_mon.add_argument("--dry-run",     action="store_true")
    sp_mon.set_defaults(func=cmd_monitor)

    # serve
    sp_srv = sub.add_parser("serve", help="Запуск FastAPI сервера")
    sp_srv.add_argument("--host", default="127.0.0.1")
    sp_srv.add_argument("--port", default=8000, type=int)
    sp_srv.set_defaults(func=cmd_serve)

    # folders
    sp_fld = sub.add_parser("folders", help="Управление папками")
    fld_sub = sp_fld.add_subparsers(dest="folders_cmd")

    fld_create = fld_sub.add_parser("create", help="Создать папки по кад. номерам")
    fld_create.add_argument("--root",        required=True, help="Корневая папка")
    fld_create.add_argument("--cad-file",    help="Файл со списком кад. номеров")
    fld_create.add_argument("--cad-numbers", help="Кад. номера через запятую")

    fld_dist = fld_sub.add_parser("distribute", help="Распределить файлы по папкам")
    fld_dist.add_argument("--root",   required=True, help="Корневая папка с ЦКН-папками")
    fld_dist.add_argument("--source", required=True, help="Папка-источник файлов")

    fld_val = fld_sub.add_parser("validate", help="Проверить содержимое папок")
    fld_val.add_argument("--root", required=True)

    sp_fld.set_defaults(func=cmd_folders)

    # bundle: сборка каталога Bundle (C3) поверх bundle_assembler
    sp_bundle = sub.add_parser("bundle", help="Собрать Bundle-каталог (C3): kmz+db+json → manifest.json")
    sp_bundle.add_argument("--out", required=True, help="Каталог Bundle (создаётся)")
    sp_bundle.add_argument("--kmz", required=True, help="project.kmz (выход стадии 08)")
    sp_bundle.add_argument("--db",  required=True, help="db.sqlite (C2 §1–§6)")
    sp_bundle.add_argument("--kind", choices=["object", "lot"], default="object")
    sp_bundle.add_argument("--json", nargs="*", help="parser-internal JSON → json/")
    sp_bundle.add_argument("--objects-json-dir", help="Каталог per-object JSON → json/objects/")
    sp_bundle.add_argument("--raw", nargs="*", help="Исходники → raw/ (опционально)")
    sp_bundle.add_argument("--objects", nargs="*", help="КН объектов (kind=object)")
    sp_bundle.add_argument("--primary-cad", help="Главный КН")
    sp_bundle.add_argument("--extract-date", help="Дата выписки YYYY-MM-DD (для лота — as_of)")
    sp_bundle.add_argument("--lot-id", help="ID лота (состав из --db; kind=lot)")
    sp_bundle.add_argument("--export-c2", action="store_true",
                           help="Положить в Bundle db.sqlite в C2-формате (ADR-007)")
    sp_bundle.set_defaults(func=cmd_bundle)

    # ingest-project: загрузка папки заполненных шаблонов одним вызовом
    sp_ip = sub.add_parser("ingest-project",
                           help="Загрузить папку шаблонов (геометрия/перечень/техкарта/ОСВ/правки) в БД")
    sp_ip.add_argument("--dir", required=True, help="Папка с заполненными файлами-шаблонами")
    sp_ip.add_argument("--db",  required=True, help="Рабочая БД (создаётся/дополняется, идемпотентно)")
    sp_ip.add_argument("--pledge-map", help="Привязка насаждений к КН ЗУ: «66=23:..,69=23:..»")
    sp_ip.set_defaults(func=cmd_ingest_project)

    # kmz: объекты в пределах ЗУ → KMZ (контуры / спираль)
    sp_kmz = sub.add_parser("kmz", help="KMZ объектов в пределах ЗУ (контуры / точки по спирали)")
    sp_kmz.add_argument("--parcels", required=True, help="КН участков через запятую: «23:15:..,23:15:..»")
    sp_kmz.add_argument("--db",  required=True, help="Рабочая БД (контуры/объекты)")
    sp_kmz.add_argument("--out", required=True, help="Выходной .kmz")
    sp_kmz.add_argument("--objects", default="linked,agro,geo",
                        help="Что считать объектом внутри ЗУ: linked(а),agro(в),geo(г) — через запятую")
    sp_kmz.add_argument("--buildings", default="nspd,db,cads",
                        help="Источник строений (порядок): nspd(2,обнаружение в границах ЗУ),"
                             "db(1,из БД),cads(3,список --building-cads)")
    sp_kmz.add_argument("--building-cads", help="КН строений (источник 3): «КН1,КН2,…»")
    sp_kmz.add_argument("--nspd", action="store_true",
                        help="Тянуть геометрию/обнаруживать ОКС из ПКК/НSPD (нужна сеть)")
    sp_kmz.set_defaults(func=cmd_kmz)

    # export-c2: конвертация рабочей БД парсера → C2 (контракт обмена)
    sp_c2 = sub.add_parser("export-c2", help="Экспорт БД парсера → C2-формат (ADR-007)")
    sp_c2.add_argument("--db",  required=True, help="Рабочая БД парсера")
    sp_c2.add_argument("--out", required=True, help="C2-БД (создаётся/перезаписывается)")
    sp_c2.set_defaults(func=cmd_export_c2)

    return p


# ─────────────────────────────────────────────────────────────────────────────
#  Точка входа
# ─────────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> None:
    parser = build_parser()
    args = parser.parse_args(argv)

    _setup_logging(getattr(args, "log_level", "INFO"))

    if not getattr(args, "command", None):
        # Интерактивный режим (ТЗ раздел 2.1)
        _interactive_mode()
        return

    if hasattr(args, "func"):
        sys.exit(args.func(args))
    else:
        parser.print_help()


def _find_or_create_output_dir(source_dir: Path, ask_user: bool = True) -> Path:
    """
    Найти или создать папку output.
    При ask_user=True предлагает выбор пользователю (Fix 21).
    """
    candidates = {
        "1": source_dir / "output",
        "2": Path(__file__).parent.parent / "output",
        "3": Path.cwd() / "output",
    }

    # Проверить доступность каждого кандидата
    available = {}
    for key, path in candidates.items():
        try:
            path.mkdir(parents=True, exist_ok=True)
            test = path / ".write_test"
            test.write_text("t"); test.unlink()
            available[key] = path
        except (OSError, PermissionError):
            pass

    if not available:
        print_warn("Нет доступных папок для записи — используется текущая папка")
        return Path.cwd()

    if not ask_user or not __import__("sys").stdin.isatty():
        # Авто: первый доступный
        return next(iter(available.values()))

    # Показать варианты пользователю
    print_sep("Куда сохранять результаты?")
    labels = {
        "1": "рядом с выписками",
        "2": "папка запуска скрипта",
        "3": "активная папка",
    }
    for key, path in available.items():
        print_info(f"  [{key}] {path}  ({labels[key]})")

    default_key = next(iter(available))
    while True:
        ans = input(f"Выбор [Enter={default_key}]: ").strip()
        if ans == "":
            ans = default_key
        if ans in available:
            chosen = available[ans]
            print_ok(f"Папка вывода: {chosen}")
            return chosen
        print_warn(f"Введите {'/'.join(available.keys())}")


def _interactive_mode() -> None:
    """Интерактивный режим CLI (ТЗ раздел 3.1)."""
    print_head(f"egrn_parser v{__version__} — ИНТЕРАКТИВНЫЙ РЕЖИМ")
    print_info("Укажите путь к файлу или папке с выписками ЕГРН:")
    print_info('Пример: D:\\ОБЪЕКТЫ\\Суворова')
    print("")

    sources: list[Path] = []
    while True:
        raw = input("Путь [или Enter для завершения ввода]: ").strip().strip('"').strip("'")
        if not raw:
            break
        p = Path(raw)
        if not p.exists():
            print_err(f"Путь не существует: {p}")
            continue
        sources.append(p.resolve())
        print_ok(f"Добавлено: {p}")
        more = input("Добавить ещё источник? [д/н] (Enter=н): ").strip().lower()
        if more not in ("д", "да", "y", "yes", "1"):
            break

    if not sources:
        print_warn("Источники не указаны. Завершение.")
        return

    include_acc = input("Учитывать принадлежности и оборудование из ОСВ? [д/н] (Enter=н): ").strip().lower()
    include_acc = include_acc in ("д", "да", "y", "yes", "1")

    # Fix 13: найти/создать папку output рядом с источником
    source_dir = sources[0].parent if sources[0].is_file() else sources[0]
    output_dir = _find_or_create_output_dir(source_dir)
    db_path = output_dir / "egrn.db"
    print_info(f"Папка вывода: {output_dir}")
    print_info(f"БД: {db_path}")

    # Проверить наличие ранее созданных файлов результатов
    existing_results = list(output_dir.glob("egrn*.db")) + list(output_dir.glob("egrn*.xlsx"))
    if existing_results:
        print_info(f"Найдено {len(existing_results)} файлов предыдущего парсинга — идемпотентный режим")

    # Запустить парсинг для каждого источника
    for source in sources:
        args = argparse.Namespace(
            input=str(source),
            db=str(db_path),
            output=str(OUTPUT_DIR),
            on_conflict="ask",
            accessories=include_acc,
            log_level="INFO",
        )
        cmd_parse(args)

    print_sep()
    print_info("Экспорт результатов...")
    export_args = argparse.Namespace(
        db=str(db_path),
        output=str(output_dir),
        xlsx=None,
        json=None,
        graph_json=None,
        xlsx_template=None,
    )
    cmd_export(export_args)
    print_ok(f"Всё готово! Результаты в {output_dir}")
