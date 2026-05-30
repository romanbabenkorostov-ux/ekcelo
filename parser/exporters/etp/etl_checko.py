"""ETL: checko-данные (innogrn.db) → `object_etp_profile.legal_extra.owner_checko`.

Контекст: см. [[parallel-parsers-map]] и `obsidian/Decisions/ADR-002-parser-checko-integration-policy.md`.

Адаптер opt-in: читает SQLite-кэш `innogrn.db` от parser_checko_ru, НЕ дёргает
checko.ru API сам. Если у пользователя нет `innogrn.db` — CLI/функция отрабатывают
no-op. parser_checko_ru остаётся standalone-модулем.

Поведение:
- Gap-fill: пишет в `legal_extra.owner_checko` только если ключ отсутствует.
- Не перезаписывает `source='osv'/'manual'` (приоритет ручного ввода).
- Для существующих профилей с `source='nspd'/'exif'/'llm'` — мерж в JSON, source не меняется.
- Если профиля нет — создаёт с `source='checko'`, `confidence=0.9`.

Маппинг innogrn.subjects → owner_checko:
    is_active           → is_active            (BOOL)
    status_text         → status_text          (TEXT)
    special_regime      → special_regime       (TEXT, например "УСН, ПСН")
    reg_date            → reg_date             (TEXT ISO)
    termination_date    → termination_date     (TEXT ISO; None для действующих)
    ust_kap             → ust_kap              (REAL, уставный капитал)
    schr                → schr                 (INT, среднесписочная численность работников)
    region              → region               (TEXT)
    + main_okved        → main OKVED через JOIN subject_okveds WHERE is_main=1
"""
from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path


_DEFAULT_SOURCE = "checko"
_DEFAULT_CONFIDENCE = 0.9


@dataclass
class EnrichItem:
    cad_number: str
    inn: str | None = None
    profile_created: bool = False
    legal_extra_filled: list[str] = field(default_factory=list)
    skipped_reason: str | None = None

    @property
    def did_change(self) -> bool:
        return self.profile_created or bool(self.legal_extra_filled)


@dataclass
class EnrichReport:
    items: list[EnrichItem] = field(default_factory=list)

    @property
    def changed_count(self) -> int:
        return sum(1 for it in self.items if it.did_change)

    @property
    def skipped_count(self) -> int:
        return sum(1 for it in self.items if not it.did_change)


def enrich_lot_from_checko(
    ek_conn: sqlite3.Connection,
    innogrn_path: Path,
    lot_id: str,
    *,
    source: str = _DEFAULT_SOURCE,
    confidence: float = _DEFAULT_CONFIDENCE,
) -> EnrichReport:
    """Обогащает все КН лота checko-данными.

    Args:
        ek_conn: соединение к ekcelo.sqlite (objects, rights, object_etp_profile, lot_items).
        innogrn_path: путь к `innogrn.db` (выход parser_checko_ru).
        lot_id: lot:* identifier.

    Returns:
        EnrichReport с per-cad детализацией.
    """
    report = EnrichReport()
    ek_conn.row_factory = sqlite3.Row

    cad_numbers = [
        row["cad_number"]
        for row in ek_conn.execute(
            "SELECT cad_number FROM lot_items WHERE lot_id = ? ORDER BY ord",
            (lot_id,),
        ).fetchall()
    ]
    if not cad_numbers:
        return report

    if not innogrn_path.exists():
        for cad in cad_numbers:
            report.items.append(EnrichItem(cad_number=cad, skipped_reason="innogrn_db_missing"))
        return report

    ino = sqlite3.connect(innogrn_path)
    ino.row_factory = sqlite3.Row
    try:
        for cad in cad_numbers:
            item = _enrich_one(ek_conn, ino, cad, source=source, confidence=confidence)
            report.items.append(item)
    finally:
        ino.close()
    return report


def _enrich_one(
    ek: sqlite3.Connection,
    ino: sqlite3.Connection,
    cad: str,
    *,
    source: str,
    confidence: float,
) -> EnrichItem:
    item = EnrichItem(cad_number=cad)

    inn = _find_right_holder_inn(ek, cad)
    if inn is None:
        item.skipped_reason = "no_right_holder_inn"
        return item
    item.inn = inn

    subject = _lookup_subject(ino, inn)
    if subject is None:
        item.skipped_reason = "inn_not_in_innogrn"
        return item

    payload = _build_owner_checko_payload(ino, subject)
    if not payload:
        item.skipped_reason = "subject_has_no_actionable_fields"
        return item

    existing = ek.execute(
        "SELECT legal_extra, source FROM object_etp_profile WHERE cad_number = ?", (cad,)
    ).fetchone()
    if existing:
        legal_extra = json.loads(existing["legal_extra"]) if existing["legal_extra"] else {}
        if legal_extra.get("owner_checko"):
            item.skipped_reason = "owner_checko_already_present"
            return item
        legal_extra["owner_checko"] = payload
        item.legal_extra_filled.append("owner_checko")
        ek.execute(
            "UPDATE object_etp_profile SET legal_extra=?, updated_at=datetime('now') "
            "WHERE cad_number=?",
            (json.dumps(legal_extra, ensure_ascii=False), cad),
        )
    else:
        legal_extra = {"owner_checko": payload}
        ek.execute(
            "INSERT INTO object_etp_profile(cad_number, legal_extra, source, confidence) "
            "VALUES (?,?,?,?)",
            (cad, json.dumps(legal_extra, ensure_ascii=False), source, confidence),
        )
        item.profile_created = True
        item.legal_extra_filled.append("owner_checko")
    return item


def _find_right_holder_inn(ek: sqlite3.Connection, cad: str) -> str | None:
    row = ek.execute(
        "SELECT right_holder_inn FROM rights WHERE cad_number = ? "
        "AND right_holder_inn IS NOT NULL ORDER BY id LIMIT 1",
        (cad,),
    ).fetchone()
    return row["right_holder_inn"] if row else None


def _lookup_subject(ino: sqlite3.Connection, inn: str) -> sqlite3.Row | None:
    row = ino.execute(
        "SELECT id_subject, is_active, status_text, special_regime, "
        "reg_date, termination_date, ust_kap, schr, region "
        "FROM subjects WHERE inn = ? AND is_branch = 0 LIMIT 1",
        (inn,),
    ).fetchone()
    return row


def _build_owner_checko_payload(ino: sqlite3.Connection, subject: sqlite3.Row) -> dict:
    payload: dict = {}
    for col in (
        "is_active", "status_text", "special_regime",
        "reg_date", "termination_date", "ust_kap", "schr", "region",
    ):
        value = subject[col]
        if value is not None and value != "":
            payload[col] = value

    main_okved_row = ino.execute(
        "SELECT o.number_okved AS num, o.name_okved AS name "
        "FROM subject_okveds so JOIN okveds o ON o.id_okveds = so.id_okveds "
        "WHERE so.id_subject = ? AND so.is_main = 1 LIMIT 1",
        (subject["id_subject"],),
    ).fetchone()
    if main_okved_row:
        payload["main_okved"] = {
            "number": main_okved_row["num"],
            "name": main_okved_row["name"],
        }
    return payload


# ─────────────────────────────────────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    import argparse
    import sys

    p = argparse.ArgumentParser(
        prog="python -m parser.exporters.etp.etl_checko",
        description="ETL: checko (innogrn.db) → object_etp_profile.legal_extra.owner_checko.",
    )
    p.add_argument("--db", required=True, help="Путь к ekcelo.sqlite.")
    p.add_argument("--innogrn-db", required=True,
                   help="Путь к innogrn.db (выход parser_checko_ru).")
    p.add_argument("--lot", required=True, help="lot_id для обогащения.")
    p.add_argument("--source", default=_DEFAULT_SOURCE)
    p.add_argument("--confidence", type=float, default=_DEFAULT_CONFIDENCE)
    p.add_argument("--dry-run", action="store_true",
                   help="Не коммитить транзакцию; печатать только отчёт.")
    args = p.parse_args(argv)

    db_path = Path(args.db)
    innogrn_path = Path(args.innogrn_db)
    if not db_path.exists():
        print(f"error: db not found: {db_path}", file=sys.stderr)
        return 2

    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        report = enrich_lot_from_checko(
            conn, innogrn_path, args.lot,
            source=args.source, confidence=args.confidence,
        )
        if args.dry_run:
            conn.rollback()
        else:
            conn.commit()
    finally:
        conn.close()

    for item in report.items:
        status = "OK  " if item.did_change else "skip"
        detail = (
            f"inn={item.inn} fields={item.legal_extra_filled}"
            if item.did_change
            else (item.skipped_reason or "")
        )
        print(f"[{status}] {item.cad_number}  {detail}")
    print(f"summary: changed={report.changed_count} skipped={report.skipped_count}"
          + (" (dry-run, rolled back)" if args.dry_run else ""))
    return 0


if __name__ == "__main__":
    import sys
    sys.exit(main())
