"""
tests/test_egrul_egrip_pipeline.py — связка parse_any + enrich_record + CLI.
Сетевой вызов checko/dadata подменяется (без ключей/сети).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).parent.parent))

from egrn_parser.parsers import egrul_egrip_pipeline as PIPE   # noqa: E402
from egrn_parser.parsers import egrul_egrip_sources as SRC     # noqa: E402

FIX = Path(__file__).parent / "fixtures" / "fns"


# ── parse_any: автоопределение XML/PDF ───────────────────────────────────────
def test_parse_any_xml():
    out = PIPE.parse_any(FIX / "egrul_408_min.xml")
    assert out["format"]["registry"] == "ЕГРЮЛ"
    assert out["records"][0]["subject"]["inn"] == "7707083893"


def test_parse_any_pdf_text():
    # .txt идёт по ветке «текст PDF-выписки»
    out = PIPE.parse_any(FIX / "egrul_pdf_min.txt")
    assert out["records"][0]["subject"]["ogrn"] == "1027700132195"


# ── enrich_record: merge с обогащением ───────────────────────────────────────
def test_enrich_record_merges_checko(monkeypatch):
    checko = json.loads((FIX / "checko_min.json").read_text(encoding="utf-8"))
    monkeypatch.setattr(SRC, "fetch_by_inn",
                        lambda inn, **k: SRC.from_checko_json(checko))
    pdf = PIPE.parse_any(FIX / "egrul_pdf_min.txt")["records"][0]
    pdf["managing_orgs"] = []  # у PDF нет — должно прийти из checko (директор) при merge
    enriched = PIPE.enrich_record(pdf, vendor="checko")
    # ИНН сохранён, источник-приоритет — PDF (официальный выше checko)
    assert enriched["subject"]["inn"] == "7707083893"
    assert enriched["source"]["merged_from"][0] == "ФНС-ЕГРЮЛ-PDF"


def test_enrich_record_no_inn_is_noop():
    rec = {"subject": {}, "source": {}}
    out = PIPE.enrich_record(rec, vendor="checko")
    assert "нет ИНН" in out["source"]["enrich_error"]


def test_enrich_record_no_key_graceful(monkeypatch):
    monkeypatch.setattr(SRC, "load_env", lambda *a, **k: {})
    monkeypatch.delenv("CHECKO_API_KEY", raising=False)
    pdf = PIPE.parse_any(FIX / "egrul_pdf_min.txt")["records"][0]
    out = PIPE.enrich_record(pdf, vendor="checko")
    # без ключа не падаем, помечаем ошибку, ИНН на месте
    assert out["subject"]["inn"] == "7707083893"
    assert "CHECKO_API_KEY" in out["source"]["enrich_error"]


# ── CLI ──────────────────────────────────────────────────────────────────────
def test_cli_outputs_json(capsys):
    rc = PIPE.main([str(FIX / "egrul_pdf_min.txt")])
    assert rc == 0
    data = json.loads(capsys.readouterr().out)
    assert data["records"][0]["subject"]["inn"] == "7707083893"


def test_cli_bad_file_returns_1(capsys, tmp_path):
    bad = tmp_path / "x.txt"
    bad.write_text("не выписка", encoding="utf-8")
    assert PIPE.main([str(bad)]) == 1


def test_cli_db_writes_entity_registry(capsys, tmp_path):
    import sqlite3
    db = tmp_path / "out.sqlite"
    rc = PIPE.main([str(FIX / "egrul_pdf_min.txt"), "--db", str(db)])
    assert rc == 0
    rows = sqlite3.connect(db).execute(
        "SELECT inn FROM entity_registry").fetchall()
    assert ("7707083893",) in rows   # субъект (+ учредитель из ownership)
    assert "inserted 7707083893" in capsys.readouterr().err


def test_cli_db_const_default(monkeypatch, tmp_path, capsys):
    # --db без аргумента → DEFAULT_DB в текущей папке
    monkeypatch.chdir(tmp_path)
    rc = PIPE.main([str(FIX / "egrul_pdf_min.txt"), "--db"])
    assert rc == 0
    assert (tmp_path / PIPE.DEFAULT_DB).exists()


def test_write_to_db_helper(tmp_path):
    db = tmp_path / "h.sqlite"
    rec = PIPE.parse_any(FIX / "egrul_pdf_min.txt")["records"]
    actions = PIPE.write_to_db(rec, str(db))
    assert actions[0]["action"] == "inserted"
