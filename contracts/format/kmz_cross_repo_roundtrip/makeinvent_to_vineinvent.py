#!/usr/bin/env python3
"""Реальная кросс-репозиторная проверка: KMZ, написанный
EkceloFotoMakeInvent (techno.kmz_profile_b.write_kmz), скармливается
VineInvent (export_photos_kmz.import_kmz) — не юнит-тест внутри одного
репозитория, а настоящий обход "выход одного компонента -> вход другого"
по методу, которым просил проверить пользователь.

Не часть тестового набора ни одного из репозиториев (два несвязанных
git-дерева, импортировать оба сразу можно только через sys.path-трюк
вроде этого) - разовый скрипт верификации для HANDOFF/карты тестирования.
"""
import sys
import sqlite3
import tempfile
from pathlib import Path

MAKEINVENT = Path("/home/user/EkceloFotoMakeInvent")
VINEINVENT = Path("/home/user/VineInvent")

sys.path.insert(0, str(MAKEINVENT))
from techno import kmz_profile_b as mi  # noqa: E402

sys.path.insert(0, str(VINEINVENT))
sys.path.insert(0, str(VINEINVENT / "etl"))
import export_photos_kmz as vi_kmz  # noqa: E402
from core import photo_store as ps  # noqa: E402
from core import config as vi_config  # noqa: E402
import migrate  # noqa: E402
from uuid7 import gen_uuid7  # noqa: E402

with tempfile.TemporaryDirectory() as tmp:
    tmp = Path(tmp)

    # --- 1. EkceloFotoMakeInvent пишет KMZ ---------------------------------
    asset_uuid = gen_uuid7()
    photo_uuid = gen_uuid7()
    photo_bytes = b"\xff\xd8\xff\xe0" + b"fake-jpeg-for-roundtrip-check"

    asset = mi.AssetRecord(
        uuid=asset_uuid, inv_no="0736", name="Ферментатор WF15/564",
        status="Используется", tech="Розлив", group_1="Винцех",
        photos=[mi.PhotoRecord(
            photo_uuid=photo_uuid, file_name="photo.jpg", data=photo_bytes,
            captured_at="2026-08-01T10:00:00Z", accuracy_m=4.2,
            lat=44.9011, lon=37.3011,
        )],
    )
    kmz_path = tmp / "from_makeinvent.kmz"
    write_stats = mi.write_kmz([asset], kmz_path)
    assert kmz_path.exists(), "EkceloFotoMakeInvent не создал файл"
    print(f"[1] EkceloFotoMakeInvent.write_kmz -> {kmz_path.name}, "
          f"{write_stats}")

    # --- 2. VineInvent читает этот файл -------------------------------------
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

    import_stats = vi_kmz.import_kmz(conn, kmz_path, org_id=ORG)
    print(f"[2] VineInvent.import_kmz -> {import_stats}")
    assert import_stats["items"] == 1
    assert import_stats["new_items"] == 1
    assert import_stats["links"] == 1

    row = conn.execute(
        "SELECT org_id, shot_lat, shot_lon, shot_accuracy_m, taken_at "
        "FROM photos WHERE photo_uuid=?", (photo_uuid,)).fetchone()
    assert row == (ORG, 44.9011, 37.3011, 4.2, "2026-08-01T10:00:00Z"), row
    link = conn.execute(
        "SELECT target_uuid, target_kind FROM photo_links WHERE photo_uuid=?",
        (photo_uuid,)).fetchone()
    assert link == (asset_uuid, "asset"), link
    print(f"[3] Точность/координаты/связь пережили переход между "
          f"репозиториями без потерь: lat={row[1]}, accuracy_m={row[3]}, "
          f"linked target={link[0]}")

    print("\nOK: EkceloFotoMakeInvent -> VineInvent — реальный кросс-репо "
          "round-trip подтверждён (не юнит-тест внутри одного дерева).")
