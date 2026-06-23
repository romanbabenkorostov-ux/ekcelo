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


# ─────────────────────────────────────────────────────────────────────────────
#  F: Project-KMZ (CONTRACT_KMZ.md) — prefix routing + ExtendedData
# ─────────────────────────────────────────────────────────────────────────────

KML_PROJECT = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>

<Placemark id="cad_zu_23-15-0000000-2267"><name>ЗУ 2267</name>
  <styleUrl>#cad_zu_default</styleUrl>
  <ExtendedData>
    <Data name="cad_number"><value>23:15:0000000:2267</value></Data>
    <Data name="object_type"><value>земельный участок</value></Data>
  </ExtendedData>
  <Polygon><outerBoundaryIs><LinearRing><coordinates>
    37.7,45.0 37.8,45.0 37.75,45.05 37.7,45.0
  </coordinates></LinearRing></outerBoundaryIs></Polygon>
</Placemark>

<Placemark id="cad_oks_23-15-0314001-1594"><name>ОКС склад</name>
  <styleUrl>#cad_oks_default</styleUrl>
  <ExtendedData>
    <Data name="cad_number"><value>23:15:0314001:1594</value></Data>
    <Data name="parent_cad"><value>23:15:0000000:2267</value></Data>
  </ExtendedData>
  <Polygon><outerBoundaryIs><LinearRing><coordinates>
    37.77,45.07 37.78,45.07 37.775,45.075 37.77,45.07
  </coordinates></LinearRing></outerBoundaryIs></Polygon>
</Placemark>

<Placemark id="photoPin_23-15-0000000-2267_1"><name>фото 1</name>
  <styleUrl>#photoPin_yellow</styleUrl>
  <ExtendedData>
    <Data name="cad_number"><value>23:15:0000000:2267</value></Data>
  </ExtendedData>
  <Point><coordinates>37.755,45.021</coordinates></Point>
</Placemark>

<Placemark id="cad_ben_7707083893"><name>Бенефициар</name>
  <styleUrl>#cad_ben_default</styleUrl>
  <ExtendedData>
    <Data name="ben_inn"><value>7707083893</value></Data>
  </ExtendedData>
  <Point><coordinates>37.62,55.75</coordinates></Point>
</Placemark>

</Document></kml>
"""


def test_project_kmz_uses_extended_data_cad(conn):
    s = import_kml(conn, KML_PROJECT, "2026-06-01")
    # 4 placemark: 3 с cad_number в ExtendedData, 1 ben (без линка)
    assert s.geo_created == 4
    rows = conn.execute(
        "SELECT asset_type, asset_id, role FROM asset_geo_link ORDER BY asset_id, role"
    ).fetchall()
    types = {(r[0], r[1], r[2]) for r in rows}
    # cad_zu → asset_type=land; cad_oks → oks; photoPin → object с role=photo
    assert ("land", "23:15:0000000:2267", "primary") in types
    assert ("oks", "23:15:0314001:1594", "primary") in types
    assert ("object", "23:15:0000000:2267", "photo") in types


def test_project_kmz_ben_skipped_from_links(conn):
    """cad_ben_* — geo создаётся, но БЕЗ asset_geo_link."""
    import_kml(conn, KML_PROJECT, "2026-06-01")
    ben_geo = conn.execute(
        "SELECT geo_uuid FROM geo_entity WHERE name LIKE 'Бенефициар%'"
    ).fetchone()
    assert ben_geo is not None
    links = conn.execute(
        "SELECT COUNT(*) FROM asset_geo_link WHERE geo_uuid=?", (ben_geo[0],)
    ).fetchone()[0]
    assert links == 0


def test_project_kmz_photopin_uses_photo_role(conn):
    """photoPin_* → asset_geo_link с role='photo', не 'primary'."""
    import_kml(conn, KML_PROJECT, "2026-06-01")
    photo_links = conn.execute(
        "SELECT asset_id, role FROM asset_geo_link WHERE role='photo'"
    ).fetchall()
    assert photo_links == [("23:15:0000000:2267", "photo")]


def test_extended_data_priority_over_regex(conn):
    """ExtendedData.cad_number перебивает regex из description."""
    kml = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark>
  <name/>
  <description><![CDATA[Не тот кадастр: 11:11:1111111:1111]]></description>
  <ExtendedData><Data name="cad_number"><value>22:22:2222222:2222</value></Data></ExtendedData>
  <Polygon><outerBoundaryIs><LinearRing><coordinates>
    37,45 38,45 37.5,46 37,45
  </coordinates></LinearRing></outerBoundaryIs></Polygon>
</Placemark></Document></kml>"""
    import_kml(conn, kml, "2026-06-01")
    row = conn.execute(
        "SELECT asset_id FROM asset_geo_link WHERE role='primary'"
    ).fetchone()
    assert row[0] == "22:22:2222222:2222"


def test_prefix_routing_works_without_extended_data(conn):
    """Префикс выбирает asset_type даже без ExtendedData."""
    kml = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document><Placemark id="cad_room_99-99-9999999-99">
  <name/>
  <description><![CDATA[99:99:9999999:99 комната]]></description>
  <styleUrl>#cad_room_default</styleUrl>
  <Polygon><outerBoundaryIs><LinearRing><coordinates>
    37,45 38,45 37.5,46 37,45
  </coordinates></LinearRing></outerBoundaryIs></Polygon>
</Placemark></Document></kml>"""
    import_kml(conn, kml, "2026-06-01")
    row = conn.execute(
        "SELECT asset_type, asset_id FROM asset_geo_link WHERE role='primary'"
    ).fetchone()
    assert row == ("room", "99:99:9999999:99")


def test_yandex_kml_still_works_without_extended_data(conn):
    """Регресс: старый Yandex-формат (без ExtendedData, без префиксов) работает."""
    s = import_kml(conn, KML_SAMPLE, "2026-06-01")
    assert s.primary_links == 2
    # asset_type — дефолтный 'object'
    types = {r[0] for r in conn.execute(
        "SELECT DISTINCT asset_type FROM asset_geo_link WHERE role='primary'"
    ).fetchall()}
    assert types == {"object"}


# ─────────────────────────────────────────────────────────────────────────────
#  Stub objects — авто-создание записей в `objects` для cad'ов из KML
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def conn_with_objects(tmp_path: Path) -> sqlite3.Connection:
    """БД с минимальным §1 (objects) + §7 — как в реальном init_db_cli."""
    c = sqlite3.connect(tmp_path / "geo_with_objects.sqlite")
    c.execute("PRAGMA foreign_keys = ON")
    c.executescript("""
        CREATE TABLE objects (
            cad_number TEXT PRIMARY KEY, object_type TEXT NOT NULL,
            address TEXT, area REAL, category TEXT, permitted_use TEXT,
            purpose TEXT, floors INTEGER
        );
    """)
    c.executescript(MIGRATION_0003.read_text(encoding="utf-8"))
    yield c
    c.close()


def test_stub_objects_created_by_default(conn_with_objects):
    """default create_stub_objects=True → cad'ы из KML появляются в objects."""
    s = import_kml(conn_with_objects, KML_SAMPLE, "2026-06-01")
    assert s.stub_objects_created == 3   # :2267 (primary), :623 (primary), :40 (reference)
    rows = conn_with_objects.execute(
        "SELECT cad_number, object_type, purpose FROM objects ORDER BY cad_number"
    ).fetchall()
    assert ("23:15:0000000:2267", "land", "kmz-stub") in rows
    assert ("23:15:0314001:40", "land", "kmz-stub") in rows
    assert ("23:15:0314001:623", "land", "kmz-stub") in rows


def test_stub_objects_disabled_by_flag(conn_with_objects):
    s = import_kml(conn_with_objects, KML_SAMPLE, "2026-06-01",
                   create_stub_objects=False)
    assert s.stub_objects_created == 0
    cnt = conn_with_objects.execute("SELECT COUNT(*) FROM objects").fetchone()[0]
    assert cnt == 0


def test_stub_does_not_overwrite_existing_object(conn_with_objects):
    """Если в objects уже есть полноценная запись — stub НЕ перезаписывает."""
    conn_with_objects.execute(
        "INSERT INTO objects(cad_number, object_type, purpose, area) "
        "VALUES ('23:15:0000000:2267', 'building', 'настоящий объект', 1234.5)"
    )
    s = import_kml(conn_with_objects, KML_SAMPLE, "2026-06-01")
    # :623 и :40 — stubs (новые), :2267 уже был, не stub
    assert s.stub_objects_created == 2
    row = conn_with_objects.execute(
        "SELECT object_type, purpose, area FROM objects WHERE cad_number='23:15:0000000:2267'"
    ).fetchone()
    assert row == ("building", "настоящий объект", 1234.5)


def test_stub_object_type_guessed_from_prefix(conn_with_objects):
    s = import_kml(conn_with_objects, KML_PROJECT, "2026-06-01")
    rows = dict(conn_with_objects.execute(
        "SELECT cad_number, object_type FROM objects"
    ).fetchall())
    # cad_zu_ → land, cad_oks_ → building
    assert rows["23:15:0000000:2267"] == "land"
    assert rows["23:15:0314001:1594"] == "building"


def test_no_objects_table_skips_stub_creation_silently(conn):
    """Sandbox-БД только с §7 (без objects) — stub silently skip."""
    s = import_kml(conn, KML_SAMPLE, "2026-06-01")
    assert s.stub_objects_created == 0
    # geo и линки всё равно созданы
    assert s.primary_links == 2


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
