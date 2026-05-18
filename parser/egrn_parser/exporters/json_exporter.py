"""
egrn_parser/exporters/json_exporter.py — полный JSON-дамп данных.

ТЗ раздел 11.3.
code_dictionary НЕ включается в экспорт.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from egrn_parser.db.connection import get_connection
from egrn_parser import __schema_version__

log = logging.getLogger(__name__)

# Таблицы для экспорта (в порядке ТЗ 11.3)
EXPORT_TABLES = [
    "extracts", "land_objects", "building_objects", "accessories",
    "business_units", "rights", "right_holders", "entity_registry",
    "company_groups", "ownership_chain", "object_events", "right_events",
    "geometry_events", "object_geometries", "valuations", "schema_registry",
]


def export_json(
    db_path: Path | str,
    out_path: Path | str,
    run_id: str | None = None,
) -> Path:
    """
    Экспортировать все данные в JSON-файл.
    BLOB → base64; NULL → null; object_restrictions парсится как объект.
    """
    db_path  = Path(db_path)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    if run_id is None:
        run_id = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")

    output: dict[str, Any] = {
        "schema_version": __schema_version__,
        "generated_at":   datetime.now(timezone.utc).isoformat(),
        "run_id":         run_id,
        "egrn_parser_version": "1.10.0",
        "tables":         {},
    }

    with get_connection(db_path, readonly=True) as conn:
        for table in EXPORT_TABLES:
            try:
                rows = conn.execute(f"SELECT * FROM {table}").fetchall()
            except Exception:
                output["tables"][table] = []
                continue

            table_data = []
            for row in rows:
                row_dict = dict(row)
                # object_restrictions: строка JSON → объект
                for key in ("object_restrictions", "permitted_uses", "old_numbers",
                            "nested_objects", "predecessor_cad_numbers", "successor_cad_numbers",
                            "land_cad_numbers", "changed_fields"):
                    if key in row_dict and isinstance(row_dict[key], str):
                        try:
                            row_dict[key] = json.loads(row_dict[key])
                        except Exception:
                            pass
                table_data.append(row_dict)
            output["tables"][table] = table_data

    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2, default=str)

    log.info("✓ JSON экспорт: %s (%d таблиц)", out_path.name, len(output["tables"]))
    return out_path
