#!/usr/bin/env python3
"""Обратное направление: KMZ, написанный VineInvent (export_photos_kmz.
export_kmz / collect + write_kmz), читается EkceloFotoMakeInvent
(techno.kmz_profile_b.read_kmz). Закрывает круг вместе с
cross_repo_kmz_roundtrip.py (MakeInvent -> VineInvent)."""
import sys
import sqlite3
import tempfile
from pathlib import Path

MAKEINVENT = Path("/home/user/EkceloFotoMakeInvent")
VINEINVENT = Path("/home/user/VineInvent")

sys.path.insert(0, str(VINEINVENT))
sys.path.insert(0, str(VINEINVENT / "etl"))
import export_photos_kmz as vi_kmz  # noqa: E402
from core import photo_store as ps  # noqa: E402
from core import config as vi_config  # noqa: E402
import migrate  # noqa: E402
from uuid7 import gen_uuid7  # noqa: E402

sys.path.insert(0, str(MAKEINVENT))
from techno import kmz_profile_b as mi  # noqa: E402

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)

    # --- 1. VineInvent пишет KMZ --------------------------------------------
    db_dir = tmp / "db"
    db_dir.mkdir()
    migrate.DB_DIR = db_dir
    vi_config.DB_DIR = db_dir
    vi_config.PHOTOS_DIR = tmp / "photos"
    vi_config.OUT_DIR = tmp / "outputs"
    migrate.migrate(verbose=False)

    conn = sqlite3.connect(db_dir / "assets.db")
    ORG = "019f0000-0000-7000-8000-00000000000a"
    conn.execute("INSERT INTO organizations (org_id,inn,short_name) VALUES (?,?,?)",
                 (ORG, "7701234567", 'ООО «ОЛИМП»'))
    conn.commit()

    asset_uuid = gen_uuid7()
    jpg = tmp / "IMG_1.jpg"
    jpg.write_bytes(b"\xff\xd8\xff\xe0" + b"vineinvent-source-photo")
    stored = ps.store(conn, ORG, jpg, source="folder", taken_at="2026-08-10T09:00:00Z",
                      shot_lat=45.07, shot_lon=37.78, shot_accuracy_m=6.1)
    ps.link(conn, stored.photo_uuid, asset_uuid, "container", role="общий вид")
    conn.commit()

    kmz_path = tmp / "from_vineinvent.kmz"
    vi_kmz.export_kmz(conn, ORG, out_path=kmz_path)
    assert kmz_path.exists()
    print(f"[1] VineInvent.export_kmz -> {kmz_path.name}")

    # --- 2. EkceloFotoMakeInvent читает этот файл ---------------------------
    assets, contours = mi.read_kmz(kmz_path)
    print(f"[2] EkceloFotoMakeInvent.read_kmz -> {len(assets)} asset(s), "
          f"contours={contours}")
    assert len(assets) == 1, assets
    read_asset = assets[0]
    assert read_asset.uuid == asset_uuid, (read_asset.uuid, asset_uuid)
    assert len(read_asset.photos) == 1, read_asset.photos
    photo = read_asset.photos[0]
    assert photo.photo_uuid == stored.photo_uuid
    assert photo.lat == 45.07 and photo.lon == 37.78
    assert photo.accuracy_m == 6.1
    assert photo.captured_at == "2026-08-10T09:00:00Z"
    print(f"[3] Координаты/точность/связь пережили переход VineInvent -> "
          f"EkceloFotoMakeInvent: lat={photo.lat}, accuracy_m={photo.accuracy_m}, "
          f"asset uuid={read_asset.uuid}")

    print("\nOK: VineInvent -> EkceloFotoMakeInvent — обратное направление "
          "кросс-репо round-trip подтверждено. Круг из двух Python-репо "
          "замкнут в обе стороны.")
