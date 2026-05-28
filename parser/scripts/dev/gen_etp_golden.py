"""Генератор golden-файлов для test_text_render. Запуск из repo root."""
import json
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, '.')

from parser.exporters.etp import build_lot_context, render_lot_description


def setup_db() -> sqlite3.Connection:
    conn = sqlite3.connect(':memory:')
    conn.execute('PRAGMA foreign_keys=ON')
    conn.executescript("""
CREATE TABLE objects(cad_number TEXT PRIMARY KEY, object_type TEXT NOT NULL, address TEXT, area REAL, category TEXT, permitted_use TEXT, purpose TEXT, floors INTEGER);
CREATE TABLE entity_registry(inn TEXT PRIMARY KEY, name_full TEXT NOT NULL, name_short TEXT, ogrn TEXT, entity_type TEXT);
CREATE TABLE rights(id INTEGER PRIMARY KEY AUTOINCREMENT, cad_number TEXT NOT NULL REFERENCES objects(cad_number), right_type TEXT NOT NULL, right_holder_inn TEXT REFERENCES entity_registry(inn), share_numerator INTEGER, share_denominator INTEGER, registration_number TEXT, registration_date TEXT, source_extract_id INTEGER);
CREATE TABLE object_restrictions(id INTEGER PRIMARY KEY AUTOINCREMENT, cad_number TEXT NOT NULL REFERENCES objects(cad_number), restrict_type TEXT, description TEXT, registry_number TEXT, valid_from TEXT, valid_to TEXT, basis_doc TEXT);
""")
    conn.executescript(Path('schema/migrations/0001_etp_profile.sql').read_text(encoding='utf-8'))
    for cad, ot, addr, area, purp, floor in [
        ('61:44:0050706:31', 'room', 'г. Ростов-на-Дону, ул. Б.Садовая, 111, пом. VII', 125.4, 'офис', 3),
        ('61:44:0050706:42', 'room', 'г. Ростов-на-Дону, ул. Промышленная, 5', 380.0, 'склад', 1),
        ('61:44:0050706:7',  'land', 'Ростовская обл., с. Иваново, уч. 7', 5000.0, None, None),
    ]:
        conn.execute('INSERT INTO objects(cad_number,object_type,address,area,purpose,floors) VALUES(?,?,?,?,?,?)', (cad, ot, addr, area, purp, floor))
    conn.execute("INSERT INTO entity_registry(inn,name_full,entity_type) VALUES('7708078840','Российская Федерация','Гос')")
    conn.execute("INSERT INTO rights(cad_number,right_type,right_holder_inn,registration_number,registration_date) VALUES('61:44:0050706:31','собственность','7708078840','61-61/044-77/001/001/2015-123','2015-06-10')")
    conn.execute("INSERT INTO object_restrictions(cad_number,restrict_type,description,valid_from,valid_to) VALUES('61:44:0050706:42','ипотека','в пользу банка X','2024-01-15',NULL)")
    fx = json.loads(Path('parser/tests/fixtures/etp/object_etp_profile_sample.json').read_text(encoding='utf-8'))
    for p in fx['object_etp_profile']:
        conn.execute('INSERT INTO object_etp_profile(cad_number,location_extra,building_extra,layout,legal_extra,risks,extras,source,confidence,updated_at) VALUES(?,?,?,?,?,?,?,?,?,?)',
                     (p['cad_number'],
                      json.dumps(p['location_extra'], ensure_ascii=False) if p.get('location_extra') else None,
                      json.dumps(p['building_extra'], ensure_ascii=False) if p.get('building_extra') else None,
                      json.dumps(p['layout'], ensure_ascii=False) if p.get('layout') else None,
                      json.dumps(p['legal_extra'], ensure_ascii=False) if p.get('legal_extra') else None,
                      json.dumps(p['risks'], ensure_ascii=False) if p.get('risks') else None,
                      json.dumps(p['extras'], ensure_ascii=False) if p.get('extras') else None,
                      p['source'], p['confidence'], p['updated_at']))
    for lot in fx['lots']:
        conn.execute('INSERT INTO lots(lot_id,name,platform_targets,procedure_type,deal_type,primary_cad_number,notes_md,created_at) VALUES(?,?,?,?,?,?,?,?)',
                     (lot['lot_id'], lot['name'], json.dumps(lot['platform_targets'], ensure_ascii=False), lot['procedure_type'], lot['deal_type'], lot['primary_cad_number'], lot.get('notes_md'), lot['created_at']))
    for it in fx['lot_items']:
        conn.execute('INSERT INTO lot_items(lot_id,cad_number,role,ord) VALUES(?,?,?,?)', (it['lot_id'], it['cad_number'], it['role'], it['ord']))
    conn.commit()
    return conn


def main():
    out_dir = Path('parser/tests/golden/etp')
    out_dir.mkdir(parents=True, exist_ok=True)
    conn = setup_db()

    # 3 платформы × 2 mode для case A (lot:pirushin:001, primary cad :31 — office)
    for plat in ['torgi.gov.ru', 'roseltorg.ru', 'sberbank-ast.ru']:
        for mode in ['short', 'full']:
            ctx = build_lot_context(conn, 'lot:pirushin:001',
                                    platform=plat, platform_mode=mode,
                                    target_cad_number='61:44:0050706:31')
            text = render_lot_description(ctx)
            name = f"caseA_office_{plat.replace('.','_')}_{mode}.txt"
            (out_dir / name).write_text(text, encoding='utf-8')
            print(f"wrote {name} ({len(text)} chars)")

    # +1 golden: case C (land :7) на torgi.gov.ru short — отдельная схема для участков
    ctx = build_lot_context(conn, 'lot:pirushin:001',
                            platform='torgi.gov.ru', platform_mode='short',
                            target_cad_number='61:44:0050706:7')
    text = render_lot_description(ctx)
    (out_dir / 'caseC_land_torgi_gov_ru_short.txt').write_text(text, encoding='utf-8')
    print(f"wrote caseC_land_torgi_gov_ru_short.txt ({len(text)} chars)")

    # +1 golden: case B (storage :42) на sberbank-ast.ru full — банкротство-ветвь
    ctx = build_lot_context(conn, 'lot:sosna-rocha:042',
                            platform='sberbank-ast.ru', platform_mode='full')
    text = render_lot_description(ctx)
    (out_dir / 'caseB_storage_sberbank_ast_ru_full.txt').write_text(text, encoding='utf-8')
    print(f"wrote caseB_storage_sberbank_ast_ru_full.txt ({len(text)} chars)")


if __name__ == '__main__':
    main()
