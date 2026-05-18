"""
egrn_parser/api.py — FastAPI приложение (ТЗ раздел 14).

Все функции CLI доступны как HTTP-эндпоинты.
Запуск: egrn-parser serve [--host 0.0.0.0] [--port 8000]
"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

try:
    from fastapi import FastAPI, HTTPException, Query, Body
    from fastapi.responses import FileResponse
    from pydantic import BaseModel
except ImportError:
    # FastAPI не обязателен для CLI-режима
    FastAPI = None  # type: ignore

from egrn_parser import __version__
from egrn_parser.config import make_run_id, OUTPUT_DIR, ensure_output_dirs


if FastAPI is not None:
    app = FastAPI(
        title="egrn_parser API",
        version=__version__,
        description="REST API для парсинга выписок ЕГРН",
    )

    class ParseRequest(BaseModel):
        input_path:  str
        db_path:     str = str(OUTPUT_DIR / "egrn.db")
        on_conflict: str = "replace"
        accessories: bool = False

    class ExportRequest(BaseModel):
        db_path:       str
        output_dir:    str = str(OUTPUT_DIR)
        xlsx_template: Optional[str] = None

    @app.get("/")
    def root():
        return {"version": __version__, "status": "ok"}

    @app.get("/health")
    def health():
        return {"status": "healthy", "version": __version__}

    @app.post("/parse")
    def parse_files(req: ParseRequest):
        """Запустить парсинг файлов/папки."""
        import argparse
        from egrn_parser.cli import cmd_parse
        args = argparse.Namespace(
            input=req.input_path,
            db=req.db_path,
            output=req.output_dir if hasattr(req, "output_dir") else str(OUTPUT_DIR),
            on_conflict=req.on_conflict,
            accessories=req.accessories,
        )
        rc = cmd_parse(args)
        return {"status": "ok" if rc == 0 else "error", "return_code": rc}

    @app.post("/export")
    def export_data(req: ExportRequest):
        """Экспортировать данные из БД."""
        import argparse
        from egrn_parser.cli import cmd_export
        run_id = make_run_id()
        args = argparse.Namespace(
            db=req.db_path,
            output=req.output_dir,
            xlsx=None,
            json=None,
            graph_json=None,
            xlsx_template=req.xlsx_template,
        )
        rc = cmd_export(args)
        out_dir = Path(req.output_dir)
        return {
            "status": "ok" if rc == 0 else "error",
            "files": {
                "xlsx":       str(out_dir / f"egrn_{run_id}.xlsx"),
                "json":       str(out_dir / f"egrn_{run_id}.json"),
                "graph_json": str(out_dir / "graph.json"),
            },
        }

    @app.get("/graph.json")
    def get_graph_json(db_path: str = Query(str(OUTPUT_DIR / "egrn.db"))):
        """Сгенерировать и вернуть graph.json."""
        from egrn_parser.exporters.graph_json import export_graph_json
        ensure_output_dirs()
        out = OUTPUT_DIR / "graph.json"
        export_graph_json(db_path, out)
        return FileResponse(str(out), media_type="application/json")

    @app.get("/objects/land")
    def get_land_objects(db_path: str = Query(str(OUTPUT_DIR / "egrn.db"))):
        """Вернуть все земельные участки."""
        from egrn_parser.db.connection import get_connection
        with get_connection(db_path, readonly=True) as conn:
            rows = conn.execute(
                "SELECT cad_number, address, area, land_category, cadastral_value, lifecycle_status "
                "FROM land_objects ORDER BY cad_number"
            ).fetchall()
        return [dict(r) for r in rows]

    @app.get("/objects/buildings")
    def get_buildings(db_path: str = Query(str(OUTPUT_DIR / "egrn.db"))):
        """Вернуть все ОКС."""
        from egrn_parser.db.connection import get_connection
        with get_connection(db_path, readonly=True) as conn:
            rows = conn.execute(
                "SELECT cad_number, object_type, name, address, area, purpose, "
                "floors_above_ground, underground_floors, cadastral_value, lifecycle_status "
                "FROM building_objects ORDER BY cad_number"
            ).fetchall()
        return [dict(r) for r in rows]

    @app.get("/objects/{cad_number}")
    def get_object(cad_number: str, db_path: str = Query(str(OUTPUT_DIR / "egrn.db"))):
        """Вернуть объект по кадастровому номеру."""
        from egrn_parser.db.connection import get_connection
        with get_connection(db_path, readonly=True) as conn:
            row = (
                conn.execute("SELECT * FROM land_objects WHERE cad_number = ?", (cad_number,)).fetchone()
                or conn.execute("SELECT * FROM building_objects WHERE cad_number = ?", (cad_number,)).fetchone()
            )
        if not row:
            raise HTTPException(status_code=404, detail=f"Объект {cad_number} не найден")
        return dict(row)

    @app.get("/rights/{cad_number}")
    def get_rights(cad_number: str, db_path: str = Query(str(OUTPUT_DIR / "egrn.db"))):
        """Вернуть все права/обременения для объекта."""
        from egrn_parser.db.connection import get_connection
        with get_connection(db_path, readonly=True) as conn:
            rows = conn.execute(
                "SELECT * FROM rights WHERE object_key_value = ? ORDER BY right_category, right_date",
                (cad_number,),
            ).fetchall()
        return [dict(r) for r in rows]

    @app.post("/migrate")
    def migrate_db(db_path: str = Body(..., embed=True)):
        """Мигрировать БД v1.9 → v1.10."""
        from egrn_parser.db.migrations import migrate
        migrate(db_path)
        return {"status": "ok", "message": "Миграция завершена"}

    @app.get("/stats")
    def get_stats(db_path: str = Query(str(OUTPUT_DIR / "egrn.db"))):
        """Базовая статистика по БД."""
        from egrn_parser.db.connection import get_connection
        with get_connection(db_path, readonly=True) as conn:
            return {
                "land_objects":      conn.execute("SELECT COUNT(*) FROM land_objects").fetchone()[0],
                "building_objects":  conn.execute("SELECT COUNT(*) FROM building_objects").fetchone()[0],
                "accessories":       conn.execute("SELECT COUNT(*) FROM accessories").fetchone()[0],
                "rights":            conn.execute("SELECT COUNT(*) FROM rights").fetchone()[0],
                "extracts":          conn.execute("SELECT COUNT(*) FROM extracts").fetchone()[0],
                "valuations":        conn.execute("SELECT COUNT(*) FROM valuations").fetchone()[0],
            }

else:
    # Заглушка если FastAPI не установлен
    app = None  # type: ignore
