"""
egrn_parser/monitoring/runner.py — цикл мониторинга объектов группы компаний.

ТЗ раздел 3.5 / 19.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path

from egrn_parser.db.connection import get_connection

log = logging.getLogger(__name__)


def get_monitored_cad_numbers(db_path: Path | str) -> list[dict]:
    """Вернуть список объектов с флагом monitored=1."""
    db_path = Path(db_path)
    with get_connection(db_path, readonly=True) as conn:
        land = conn.execute(
            "SELECT cad_number, 'land' AS object_class FROM land_objects WHERE monitored = 1"
        ).fetchall()
        bldg = conn.execute(
            "SELECT cad_number, 'building' AS object_class FROM building_objects WHERE monitored = 1"
        ).fetchall()
    return [dict(r) for r in (list(land) + list(bldg))]


def run_monitoring_cycle(
    db_path: Path | str,
    cad_numbers: list[str] | None = None,
    dry_run: bool = False,
) -> dict:
    """
    Запустить цикл мониторинга.
    В dry_run=True — только журналирование без изменений.
    """
    db_path = Path(db_path)
    stats = {"checked": 0, "changed": 0, "errors": 0}

    monitored = get_monitored_cad_numbers(db_path)
    if cad_numbers:
        monitored = [m for m in monitored if m["cad_number"] in cad_numbers]

    log.info("Мониторинг: %d объектов", len(monitored))

    for item in monitored:
        cad = item["cad_number"]
        stats["checked"] += 1
        try:
            # TODO(v1.11): реальный запрос к Росреестру / PKK API
            log.info("  Проверяем %s ... (заглушка)", cad)
            _log_monitoring_check(db_path, cad, item["object_class"], "ok", dry_run)
        except Exception as e:
            log.error("Ошибка мониторинга %s: %s", cad, e)
            stats["errors"] += 1
            _log_monitoring_check(db_path, cad, item["object_class"], "error", dry_run,
                                  error_message=str(e))

    return stats


def _log_monitoring_check(
    db_path: Path,
    cad_number: str,
    object_class: str,
    status: str,
    dry_run: bool,
    events_generated: int = 0,
    error_message: str | None = None,
) -> None:
    if dry_run:
        return
    with get_connection(db_path) as conn:
        conn.execute(
            """
            INSERT INTO monitoring_log
            (cad_number, object_class, status, events_generated, error_message)
            VALUES (?, ?, ?, ?, ?)
            """,
            (cad_number, object_class, status, events_generated, error_message),
        )
