"""tests/test_etl_exif.py — Stage 6: импорт ЭТП-обогащений из EXIF UserComment.

Создаёт реальные JPG'и с piexif + Pillow → проверяет полный путь
scan_directory → enrich_from_exif → object_etp_profile.
"""
from __future__ import annotations

import io
import json
import sqlite3
from pathlib import Path

import piexif
import pytest
from piexif.helper import UserComment
from PIL import Image

from parser.exporters.etp.etl_exif import (
    enrich_from_exif,
    read_userComment,
    scan_directory,
)
from parser.exporters.etp.etl_exif_cli import main as cli_main


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION = REPO_ROOT / "schema" / "migrations" / "0001_etp_profile.sql"


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _make_jpg(path: Path, payload: dict | None) -> None:
    """Записать минимальный JPG с EXIF UserComment payload."""
    img = Image.new("RGB", (4, 4), color=(255, 255, 255))
    if payload is None:
        img.save(path, "JPEG")
        return
    user_comment = UserComment.dump(
        json.dumps(payload, ensure_ascii=False), encoding="unicode"
    )
    exif_dict = {
        "Exif": {piexif.ExifIFD.UserComment: user_comment},
    }
    exif_bytes = piexif.dump(exif_dict)
    buf = io.BytesIO()
    img.save(buf, "JPEG", exif=exif_bytes)
    path.write_bytes(buf.getvalue())


@pytest.fixture
def db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
        CREATE TABLE objects (cad_number TEXT PRIMARY KEY, object_type TEXT NOT NULL,
            address TEXT, area REAL, category TEXT, permitted_use TEXT, purpose TEXT, floors INTEGER);
    """)
    conn.executescript(MIGRATION.read_text(encoding="utf-8"))
    for cad in ("61:44:0050706:31", "61:44:0050706:42"):
        conn.execute("INSERT INTO objects(cad_number, object_type) VALUES (?, 'room')", (cad,))
    conn.commit()
    return conn


# ─────────────────────────────────────────────────────────────────────────────
#  read_userComment
# ─────────────────────────────────────────────────────────────────────────────

def test_read_user_comment_valid(tmp_path):
    p = tmp_path / "good.jpg"
    _make_jpg(p, {"app": "ekcelo", "kind": "photo", "cad": "61:44:0050706:31"})
    payload = read_userComment(p)
    assert payload is not None
    assert payload["cad"] == "61:44:0050706:31"


def test_read_user_comment_no_exif(tmp_path):
    p = tmp_path / "bare.jpg"
    _make_jpg(p, None)
    assert read_userComment(p) is None


def test_read_user_comment_not_ekcelo(tmp_path):
    """payload без `app: ekcelo` — игнорируется."""
    p = tmp_path / "other.jpg"
    _make_jpg(p, {"app": "other_tool", "cad": "61:44:0050706:31"})
    assert read_userComment(p) is None


def test_read_user_comment_corrupted(tmp_path):
    """Не-JPG → не падает, возвращает None."""
    p = tmp_path / "junk.jpg"
    p.write_bytes(b"not a jpeg")
    assert read_userComment(p) is None


# ─────────────────────────────────────────────────────────────────────────────
#  scan_directory
# ─────────────────────────────────────────────────────────────────────────────

def test_scan_directory_recurses(tmp_path):
    photos = tmp_path / "Фотографии"
    (photos / "subdir").mkdir(parents=True)
    _make_jpg(photos / "a.jpg",
              {"app": "ekcelo", "kind": "photo", "cad": "61:44:0050706:31",
               "category": "Фасад"})
    _make_jpg(photos / "subdir" / "b.jpg",
              {"app": "ekcelo", "kind": "photo", "cad": "61:44:0050706:31",
               "category": "Кровля"})
    metas = scan_directory(photos)
    assert len(metas) == 2
    assert {m.category for m in metas} == {"Фасад", "Кровля"}


def test_scan_directory_skips_non_ekcelo(tmp_path):
    photos = tmp_path / "p"
    photos.mkdir()
    _make_jpg(photos / "ours.jpg",
              {"app": "ekcelo", "kind": "photo", "cad": "61:44:0050706:31"})
    _make_jpg(photos / "stranger.jpg",
              {"app": "other_tool", "cad": "x"})
    _make_jpg(photos / "no_exif.jpg", None)
    metas = scan_directory(photos)
    assert len(metas) == 1
    assert metas[0].cad == "61:44:0050706:31"


# ─────────────────────────────────────────────────────────────────────────────
#  enrich_from_exif: создание профиля + advantages
# ─────────────────────────────────────────────────────────────────────────────

def test_enrich_creates_profile_with_advantages(db, tmp_path):
    photos = tmp_path / "p"
    photos.mkdir()
    _make_jpg(photos / "a.jpg",
              {"app": "ekcelo", "kind": "photo", "cad": "61:44:0050706:31",
               "category": "Фасад"})
    _make_jpg(photos / "b.jpg",
              {"app": "ekcelo", "kind": "photo", "cad": "61:44:0050706:31",
               "category": "Кровля"})
    reports = enrich_from_exif(db, scan_directory(photos))
    assert len(reports) == 1
    r = reports[0]
    assert r.changed
    assert r.profile_created
    assert r.photos_count == 2
    assert r.categories == ["Кровля", "Фасад"]
    row = db.execute("SELECT extras, source, confidence FROM object_etp_profile WHERE cad_number=?",
                     ("61:44:0050706:31",)).fetchone()
    payload = json.loads(row[0])
    assert payload["advantages"] == ["Комплексная фотофиксация: Кровля, Фасад."]
    assert row[1] == "exif"
    assert row[2] == 0.7


def test_enrich_preserves_existing_advantages(db, tmp_path):
    """advantages: ['прежний пункт'] → после EXIF: 2 пункта (старый сохранён)."""
    db.execute(
        "INSERT INTO object_etp_profile(cad_number, extras, source, confidence) "
        "VALUES (?, ?, 'osv', 1.0)",
        ("61:44:0050706:31",
         json.dumps({"advantages": ["расположение в центре"]})),
    )
    db.commit()
    photos = tmp_path / "p"
    photos.mkdir()
    _make_jpg(photos / "a.jpg",
              {"app": "ekcelo", "kind": "photo", "cad": "61:44:0050706:31",
               "category": "Фасад"})
    reports = enrich_from_exif(db, scan_directory(photos))
    assert reports[0].changed
    assert not reports[0].profile_created  # обновление, не создание
    payload = json.loads(db.execute(
        "SELECT extras FROM object_etp_profile WHERE cad_number=?",
        ("61:44:0050706:31",)).fetchone()[0])
    assert payload["advantages"] == [
        "расположение в центре",
        "Комплексная фотофиксация: Фасад.",
    ]


def test_enrich_idempotent(db, tmp_path):
    """Повторный прогон с тем же набором фото → second call skip."""
    photos = tmp_path / "p"
    photos.mkdir()
    _make_jpg(photos / "a.jpg",
              {"app": "ekcelo", "kind": "photo", "cad": "61:44:0050706:31",
               "category": "Фасад"})
    enrich_from_exif(db, scan_directory(photos))
    reports = enrich_from_exif(db, scan_directory(photos))
    assert reports[0].skipped_reason == "photo_summary_already_present"
    payload = json.loads(db.execute(
        "SELECT extras FROM object_etp_profile WHERE cad_number=?",
        ("61:44:0050706:31",)).fetchone()[0])
    assert payload["advantages"] == ["Комплексная фотофиксация: Фасад."]


def test_enrich_skips_photos_without_category(db, tmp_path):
    photos = tmp_path / "p"
    photos.mkdir()
    _make_jpg(photos / "a.jpg",
              {"app": "ekcelo", "kind": "photo", "cad": "61:44:0050706:31"})
    reports = enrich_from_exif(db, scan_directory(photos))
    assert reports[0].skipped_reason == "no_categories_in_exif"
    assert not reports[0].changed


def test_enrich_skips_non_photo_kind(db, tmp_path):
    """kind:doc (документы) — не считаются фотофиксацией."""
    photos = tmp_path / "p"
    photos.mkdir()
    _make_jpg(photos / "doc.jpg",
              {"app": "ekcelo", "kind": "egrn", "cad": "61:44:0050706:31"})
    reports = enrich_from_exif(db, scan_directory(photos))
    assert reports == []  # документы отфильтрованы


def test_enrich_groups_by_cad(db, tmp_path):
    photos = tmp_path / "p"
    photos.mkdir()
    for i, (cad, cat) in enumerate([
        ("61:44:0050706:31", "Фасад"),
        ("61:44:0050706:31", "Кровля"),
        ("61:44:0050706:42", "Интерьер"),
    ]):
        _make_jpg(photos / f"p{i}.jpg",
                  {"app": "ekcelo", "kind": "photo", "cad": cad, "category": cat})
    reports = enrich_from_exif(db, scan_directory(photos))
    cads = {r.cad_number for r in reports}
    assert cads == {"61:44:0050706:31", "61:44:0050706:42"}
    r31 = next(r for r in reports if r.cad_number == "61:44:0050706:31")
    assert r31.photos_count == 2
    r42 = next(r for r in reports if r.cad_number == "61:44:0050706:42")
    assert r42.photos_count == 1


def test_enrich_fk_error_recorded(db, tmp_path):
    """КН :999 нет в objects → FK fail записан в skipped_reason."""
    photos = tmp_path / "p"
    photos.mkdir()
    _make_jpg(photos / "p.jpg",
              {"app": "ekcelo", "kind": "photo", "cad": "99:99:9999999:9",
               "category": "Фасад"})
    reports = enrich_from_exif(db, scan_directory(photos))
    assert reports[0].skipped_reason is not None
    assert "fk_error" in reports[0].skipped_reason


# ─────────────────────────────────────────────────────────────────────────────
#  CLI
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def db_file(tmp_path) -> Path:
    db = tmp_path / "ekcelo.sqlite"
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript("""
        CREATE TABLE objects (cad_number TEXT PRIMARY KEY, object_type TEXT NOT NULL,
            address TEXT, area REAL, category TEXT, permitted_use TEXT, purpose TEXT, floors INTEGER);
    """)
    conn.executescript(MIGRATION.read_text(encoding="utf-8"))
    for cad in ("61:44:0050706:31",):
        conn.execute("INSERT INTO objects(cad_number, object_type) VALUES (?, 'room')", (cad,))
    conn.commit()
    conn.close()
    return db


def test_cli_writes(db_file, tmp_path, capsys):
    photos = tmp_path / "Фото"
    photos.mkdir()
    _make_jpg(photos / "p.jpg",
              {"app": "ekcelo", "kind": "photo", "cad": "61:44:0050706:31",
               "category": "Фасад"})
    rc = cli_main(["--db", str(db_file), "--photos", str(photos)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "APPLIED" in out
    assert "changed: 1" in out


def test_cli_dry_run_does_not_persist(db_file, tmp_path):
    photos = tmp_path / "Фото"
    photos.mkdir()
    _make_jpg(photos / "p.jpg",
              {"app": "ekcelo", "kind": "photo", "cad": "61:44:0050706:31",
               "category": "Фасад"})
    cli_main(["--db", str(db_file), "--photos", str(photos), "--dry-run"])
    conn = sqlite3.connect(db_file)
    rows = conn.execute("SELECT COUNT(*) FROM object_etp_profile").fetchone()[0]
    assert rows == 0


def test_cli_empty_dir(db_file, tmp_path, capsys):
    photos = tmp_path / "empty"
    photos.mkdir()
    rc = cli_main(["--db", str(db_file), "--photos", str(photos)])
    assert rc == 0
    assert "NO-PHOTOS" in capsys.readouterr().err


def test_cli_missing_db_returns_2(tmp_path, capsys):
    photos = tmp_path / "p"
    photos.mkdir()
    rc = cli_main(["--db", str(tmp_path / "nope.sqlite"), "--photos", str(photos)])
    assert rc == 2


def test_cli_missing_photos_dir_returns_2(db_file, tmp_path):
    rc = cli_main(["--db", str(db_file), "--photos", str(tmp_path / "nope")])
    assert rc == 2
