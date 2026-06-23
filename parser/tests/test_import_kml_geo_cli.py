"""CLI импорта KML → §7. Покрывает:
- парсинг полигона и точки;
- извлечение основного и reference cad;
- unlinked (geo есть, asset_geo_link нет);
- идемпотентность при повторном запуске;
- извлечение valid_from из имени файла;
- KMZ-распаковка;
- dry-run (нет записи);
- ошибки CLI.
"""
from __future__ import annotations

import sqlite3
import sys
import zipfile
from pathlib import Path

import pytest

from parser.exporters.etp.import_kml_geo_cli import (
    description_label,
    extract_valid_from_from_filename,
    import_kml,
    main,
)


REPO_ROOT = Path(__file__).resolve().parents[2]
MIGRATION_0003 = REPO_ROOT / "schema" / "migrations" / "0003_geo_entities.sql"


KML_SAMPLE = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
<Placemark><name/>
  <description><![CDATA[Поле 23:15:0000000:2267 · Шардоне 2023]]></description>
  <Polygon><outerBoundaryIs><LinearRing><coordinates>
    37.7,45.0 37.8,45.0 37.75,45.05 37.7,45.0
  </coordinates></LinearRing></outerBoundaryIs></Polygon>
</Placemark>
<Placemark><name/>
  <description><![CDATA[23:15:0314001:623 Здание лит.И модуль (23:15:0314001:40)]]></description>
  <Polygon><outerBoundaryIs><LinearRing><coordinates>
    37.77,45.07 37.78,45.07 37.775,45.075 37.77,45.07
  </coordinates></LinearRing></outerBoundaryIs></Polygon>
</Placemark>
<Placemark><name/>
  <description><![CDATA[Площадка 12А. Емкостной парк]]></description>
  <Polygon><outerBoundaryIs><LinearRing><coordinates>
    37.78,45.08 37.79,45.08 37.785,45.085 37.78,45.08
  </coordinates></LinearRing></outerBoundaryIs></Polygon>
</Placemark>
<Placemark><name/>
  <description><![CDATA[Скважина № 3]]></description>
  <Point><coordinates>37.77370,45.06876</coordinates></Point>
</Placemark>
</Document></kml>
"""


@pytest.fixture
def conn(tmp_path: Path) -> sqlite3.Connection:
    c = sqlite3.connect(tmp_path / "geo.sqlite")
    c.execute("PRAGMA foreign_keys = ON")
    c.executescript(MIGRATION_0003.read_text(encoding="utf-8"))
    yield c
    c.close()


def test_description_label_strips_html_and_after_dot():
    assert description_label("Гараж (офис) <br/>cad · 256,8 кв. м") == "Гараж (офис) cad"
    assert description_label("") == ""
    assert description_label("Площадка 12А") == "Площадка 12А"


def test_extract_valid_from_from_filename():
    assert extract_valid_from_from_filename(Path("Олимп_15-06-2026_10-22.kml")) == "2026-06-15"
    assert extract_valid_from_from_filename(Path("noDate.kml")) is None


def test_import_counts_geo_contour_point_links(conn):
    s = import_kml(conn, KML_SAMPLE, "2026-06-01")
    assert s.total == 4
    assert s.geo_created == 4
    assert s.contours == 3
    assert s.points == 1
    assert s.primary_links == 2          # :2267, :623
    assert s.secondary_links == 1        # :40 (parent в скобках)
    assert s.unlinked == 2                # Площадка 12А + Скважина
    assert s.skipped_existing == 0


def test_primary_and_reference_links_use_correct_roles(conn):
    import_kml(conn, KML_SAMPLE, "2026-06-01")
    primary = conn.execute(
        "SELECT asset_id FROM asset_geo_link WHERE role='primary' ORDER BY asset_id"
    ).fetchall()
    refs = conn.execute(
        "SELECT asset_id FROM asset_geo_link WHERE role='reference'"
    ).fetchall()
    assert [r[0] for r in primary] == ["23:15:0000000:2267", "23:15:0314001:623"]
    assert [r[0] for r in refs] == ["23:15:0314001:40"]


def test_point_stores_lat_lon_correctly(conn):
    """Yandex coords = lon,lat. Парсер инвертирует в lat,lon."""
    import_kml(conn, KML_SAMPLE, "2026-06-01")
    pt = conn.execute(
        "SELECT lat, lon FROM geo_entity_point LIMIT 1"
    ).fetchone()
    assert pt == pytest.approx((45.06876, 37.77370), abs=1e-5)


def test_idempotent_rerun_skips_existing_primary_links(conn):
    import_kml(conn, KML_SAMPLE, "2026-06-01")
    s2 = import_kml(conn, KML_SAMPLE, "2026-06-01")
    # 2 primary линка уже есть → 2 placemark skipped;
    # 2 placemark без cad обрабатываются всегда (unlinked-логика).
    assert s2.skipped_existing == 2
    assert s2.primary_links == 0


def test_rerun_with_new_valid_from_does_not_skip(conn):
    import_kml(conn, KML_SAMPLE, "2026-06-01")
    s2 = import_kml(conn, KML_SAMPLE, "2026-07-01")
    assert s2.skipped_existing == 0
    assert s2.primary_links == 2


def test_dry_run_makes_no_writes(conn):
    s = import_kml(conn, KML_SAMPLE, "2026-06-01", dry_run=True)
    assert s.geo_created == 4
    # БД пуста после dry-run
    cnt = conn.execute("SELECT COUNT(*) FROM geo_entity").fetchone()[0]
    assert cnt == 0


def test_cli_smoke_writes_to_db(tmp_path: Path, capsys, monkeypatch):
    kml_path = tmp_path / "Олимп_15-06-2026.kml"
    kml_path.write_text(KML_SAMPLE, encoding="utf-8")
    db_path = tmp_path / "test.sqlite"
    sqlite3.connect(db_path).executescript(
        MIGRATION_0003.read_text(encoding="utf-8")
    )

    rc = main(["--kml", str(kml_path), "--db", str(db_path)])
    assert rc == 0
    out = capsys.readouterr().out
    assert "valid_from=2026-06-15" in out  # из имени файла
    assert "placemark'ов:    4" in out

    c = sqlite3.connect(db_path)
    assert c.execute("SELECT COUNT(*) FROM geo_entity").fetchone()[0] == 4


def test_cli_dry_run(tmp_path: Path, capsys):
    kml_path = tmp_path / "x_01-06-2026.kml"
    kml_path.write_text(KML_SAMPLE, encoding="utf-8")
    db_path = tmp_path / "test.sqlite"
    sqlite3.connect(db_path).executescript(
        MIGRATION_0003.read_text(encoding="utf-8")
    )
    rc = main(["--kml", str(kml_path), "--db", str(db_path), "--dry-run"])
    assert rc == 0
    assert "[DRY-RUN]" in capsys.readouterr().out
    c = sqlite3.connect(db_path)
    assert c.execute("SELECT COUNT(*) FROM geo_entity").fetchone()[0] == 0


def test_cli_missing_kml_returns_error(tmp_path: Path, capsys):
    db_path = tmp_path / "x.sqlite"
    sqlite3.connect(db_path).executescript(
        MIGRATION_0003.read_text(encoding="utf-8")
    )
    rc = main(["--kml", str(tmp_path / "nope.kml"), "--db", str(db_path)])
    assert rc == 2
    assert "KML not found" in capsys.readouterr().err


def test_cli_no_date_in_filename_requires_flag(tmp_path: Path, capsys):
    kml_path = tmp_path / "noDate.kml"
    kml_path.write_text(KML_SAMPLE, encoding="utf-8")
    db_path = tmp_path / "x.sqlite"
    sqlite3.connect(db_path).executescript(
        MIGRATION_0003.read_text(encoding="utf-8")
    )
    rc = main(["--kml", str(kml_path), "--db", str(db_path)])
    assert rc == 2
    assert "не удалось извлечь дату" in capsys.readouterr().err


def test_cli_kmz_unpacks_inner_kml(tmp_path: Path):
    kmz_path = tmp_path / "Олимп_15-06-2026.kmz"
    with zipfile.ZipFile(kmz_path, "w") as z:
        z.writestr("doc.kml", KML_SAMPLE)
    db_path = tmp_path / "x.sqlite"
    sqlite3.connect(db_path).executescript(
        MIGRATION_0003.read_text(encoding="utf-8")
    )
    rc = main(["--kml", str(kmz_path), "--db", str(db_path)])
    assert rc == 0
    c = sqlite3.connect(db_path)
    assert c.execute("SELECT COUNT(*) FROM geo_entity").fetchone()[0] == 4
