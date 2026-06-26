"""
golden_path_demo.py — демонстрация «золотого пути» Ekcelo на МОК-данных.

Один прогон проводит лот «винодельческое хозяйство» через весь конвейер:
земля → насаждения → техкарта → погода → оценка → ОС/ЭТП-профиль → лот → бандл.
Печатает результат каждого шага. Не требует сети и тяжёлых зависимостей
(использует land_db / vineyard_perechen / agro_techcard / agro_reports /
weather_open_meteo / etp_merge / lot_assembler / bundle_assembler).

Запуск:
    cd parser
    python scripts/golden_path_demo.py

Мок-данные: `obsidian/Golden-Path-Economist/mock_data/` + фикстуры
`tests/fixtures/agro/` (техкарта виноградника, перечень насаждений).
"""
from __future__ import annotations

import json
import sqlite3
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from egrn_parser import bundle_assembler as BA           # noqa: E402
from egrn_parser import etp_merge as EM                  # noqa: E402
from egrn_parser import lot_assembler as LA              # noqa: E402
from egrn_parser.parsers import agro_reports as AR       # noqa: E402
from egrn_parser.parsers import agro_techcard as TC      # noqa: E402
from egrn_parser.parsers import land_db as LDB           # noqa: E402
from egrn_parser.parsers import vineyard_perechen as VP  # noqa: E402
from egrn_parser.parsers import weather_open_meteo as W  # noqa: E402

FIX = ROOT / "tests" / "fixtures" / "agro"
LAND_CAD = "23:15:0804000:66"           # ЕЗП с виноградниками
BUILD_CAD = "23:15:0804000:200"         # винодельня (ОКС)

# МОК: геометрия ЕЗП (2 обособленных контура) — обычно приходит из NSPD-парсера.
_GEOM = {"type": "MultiPolygon", "coordinates": [
    [[[38.90, 45.00], [38.92, 45.00], [38.92, 45.02], [38.90, 45.02], [38.90, 45.00]]],
    [[[38.95, 45.05], [38.96, 45.05], [38.96, 45.06], [38.95, 45.06], [38.95, 45.05]]]]}


def _hr(title: str) -> None:
    print(f"\n{'─' * 70}\n▶ {title}\n{'─' * 70}")


def main() -> int:
    work = Path(tempfile.mkdtemp(prefix="ekcelo_golden_"))
    db_path = work / "db.sqlite"
    conn = sqlite3.connect(db_path)

    # ── Подготовка БД: ЕГРН-объекты (§1) + агро-слой (0005) + оценка (0009/0010) ──
    conn.executescript("""
        CREATE TABLE objects(cad_number TEXT PRIMARY KEY, object_type TEXT, updated_at TEXT);
        CREATE TABLE lots(lot_id TEXT PRIMARY KEY, name TEXT NOT NULL, primary_cad_number TEXT, created_at TEXT);
        CREATE TABLE lot_items(lot_id TEXT, cad_number TEXT, role TEXT, ord INTEGER, PRIMARY KEY(lot_id,cad_number));
        CREATE TABLE object_etp_profile(cad_number TEXT PRIMARY KEY, location_extra TEXT,
            building_extra TEXT, layout TEXT, legal_extra TEXT, risks TEXT, extras TEXT,
            source TEXT NOT NULL, confidence REAL NOT NULL, updated_at TEXT);
    """)
    conn.executemany("INSERT INTO objects VALUES(?,?,?)", [
        (LAND_CAD, "land", "2024-01-10"), (BUILD_CAD, "building", "2024-01-10")])
    mig_dir = next(d for d in (ROOT / "schema" / "migrations",
                               ROOT.parent / "schema" / "migrations") if d.exists())
    conn.executescript((mig_dir / "0005_agro_layer.sql").read_text(encoding="utf-8"))
    conn.commit()

    # ── ШАГ 1. Земля: контуры ЕЗП из геометрии (NSPD) ────────────────────────────
    _hr("ШАГ 1. Земля — контуры участка из геометрии (ЗУ/ЕЗП/МКУ)")
    # ЕЗП известен по выписке (дочерние КН), геометрия НЕ должна понизить его до МКУ:
    LDB.upsert_land_extract(conn, {"cad_number": LAND_CAD, "layout": "ЕЗП",
                                   "children": ["23:15:0804000:67", "23:15:0804000:68"]})
    res = LDB.upsert_geometry_contours(conn, LAND_CAD, _GEOM, name="Единое землепользование")
    print(f"  Тип участка: {res['layout']}  (геометрия не понизила ЕЗП → МКУ — это была реальная проблема)")
    print(f"  Контуров в БД: {conn.execute('SELECT COUNT(*) FROM land_contours').fetchone()[0]}")

    # ── ШАГ 2. Насаждения: перечень из залогового документа ──────────────────────
    _hr("ШАГ 2. Виноградники — перечень насаждений (залоговый документ)")
    text = (FIX / "vineyard_perechen_sample.txt").read_text(encoding="utf-8")
    pres = VP.ingest_plantings(conn, text, land_cad_by_pledge={66: LAND_CAD})
    print(f"  Насаждений распознано: {pres['plantings']} (сорт/год высадки/кусты/фед.реестр)")
    for r in conn.execute("SELECT parcel_code, area_ha FROM agro_parcel"):
        print(f"    {r[0]} — {r[1]} га")

    # ── ШАГ 3. Техкарта виноградника (смета операций + СЗР) ──────────────────────
    _hr("ШАГ 3. Техкарта виноградника — операции ухода + средства защиты")
    tcard = FIX / "vineyard_techcard_sample.xlsx"
    if tcard.exists():
        ing = TC.ingest(conn, tcard, parcel_code="виноградник-смета")
        print(f"  Операций+веществ записано: {ing['written']['events']} (площадь {ing['meta'].get('area_ha')} га)")
    else:
        print("  (фикстура техкарты не найдена — пропуск)")

    # ── ШАГ 4. Погода: накопленные условия с года посадки (Open-Meteo, офлайн) ───
    _hr("ШАГ 4. Накопленная погода по геоточке (с момента посадки)")
    pid = conn.execute("SELECT parcel_id, centroid_lon, centroid_lat FROM agro_parcel "
                       "LEFT JOIN (SELECT parent_cad, AVG(centroid_lon) centroid_lon, AVG(centroid_lat) centroid_lat "
                       "FROM land_contours GROUP BY parent_cad) lc ON lc.parent_cad=agro_parcel.land_cad "
                       "WHERE land_cad=? LIMIT 1", (LAND_CAD,)).fetchone()
    # МОК накопленной погоды (в реале — accumulated_since_planting по сети):
    W.store_accumulated(conn, {"lat": pid[2], "lon": pid[1], "start": "2022-01-01",
                               "end": "2024-12-31", "n_days": 1095, "gdd": 5400.0,
                               "precip_mm": 1500.0, "radiation_mj": 18500.0}, parcel_id=pid[0])
    print("  Накоплено (мок): GDD=5400, осадки=1500 мм, радиация=18500 МДж/м² за 3 сезона")
    print("  (реальный прогон — accumulated_since_planting по сети Open-Meteo)")

    # ── ШАГ 5. Оценочная вьюха: контур × насаждение × уход × погода ──────────────
    _hr("ШАГ 5. Оценочный профиль виноградника (всё вместе)")
    for v in AR.vineyard_valuation(conn):
        print(f"  {v['parcel_code']}: сорт={v['variety']} возраст={v['vine_age_years']}л "
              f"площадь={v['area_ha']}га кустов={v['vines_count']} "
              f"уход={v['n_care_operations']}оп/{v['n_treatments']}обр GDD={v['accum_gdd']}")

    # ── ШАГ 6. ЭТП-профиль объекта: gap-fill из разных источников ────────────────
    _hr("ШАГ 6. ЭТП-профиль винодельни — слияние источников (manual > osv > nspd)")
    EM.merge_profile(conn, BUILD_CAD, {"building_extra": {"wear_degree": 30}},
                     source="manual", confidence=0.95)              # ручной ввод экономиста
    EM.merge_profile(conn, BUILD_CAD, {"building_extra": {"wear_degree": 60, "building_type": "кирпичное"}},
                     source="nspd", confidence=0.8)                 # NSPD — НЕ затирает manual
    be = json.loads(conn.execute("SELECT building_extra FROM object_etp_profile WHERE cad_number=?",
                                 (BUILD_CAD,)).fetchone()[0])
    print(f"  Износ={be['wear_degree']} (ручной ввод сохранён), материал={be.get('building_type')} (дополнено NSPD)")
    print(f"  ЭТП-слой присутствует: {EM.etp_layer_present(conn)}")

    # ── ШАГ 7. Лот: детерминированный отбор состава ──────────────────────────────
    _hr("ШАГ 7. Сборка лота (земля + винодельня)")
    frag = LA.assemble_lot(conn, "lot-vineyard-001", "Винодельческое хозяйство",
                           include={"cads": [LAND_CAD, BUILD_CAD]}, as_of="2024-12-31",
                           primary_cad=LAND_CAD)
    print(f"  Лот {frag['lot_id']}: члены={frag['members']}")

    # ── ШАГ 8. Бандл: каталог обмена + manifest ──────────────────────────────────
    _hr("ШАГ 8. Сборка Bundle (единица обмена с бэкендом)")
    kmz = work / "project.kmz"; kmz.write_bytes(b"KMZ-stub (stage 08 output)")
    conn.commit(); conn.close()
    out = work / "bundle"
    m = BA.assemble_bundle(out, kmz=kmz, db=db_path, kind="lot",
                           objects=frag["members"], lot=frag, etp_layer_present=True,
                           generated_at="2024-12-31T12:00:00+00:00")
    print(f"  Bundle: {out}")
    print(f"  Файлов в manifest: {len(m['files'])}; целостность: "
          f"{'OK' if not BA.verify_bundle(out) else 'НАРУШЕНА'}")

    print(f"\n{'═' * 70}\n✅ Золотой путь пройден. Рабочая папка: {work}\n{'═' * 70}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
