from db.connection import get_connection
import os

def inspect_db():
    possible_paths = [
        'db.sqlite',
        'egrn.db',
        'database.sqlite',
        '../db.sqlite',
        'data/db.sqlite',
        'db/egrn_parser.sqlite'
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            print(f"✅ Найден файл: {path} ({os.path.getsize(path)/1024:.1f} KB)")
            try:
                with get_connection(path) as conn:
                    cur = conn.cursor()
                    cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
                    tables = cur.fetchall()
                    print(f"   Таблиц внутри: {len(tables)}")
                    for (t,) in tables:
                        print(f"     • {t}")
            except Exception as e:
                print(f"   Ошибка при чтении: {e}")
            print("-" * 60)
    
    # Пробуем подключение без параметра
    print("\nПробуем подключение по умолчанию...")
    try:
        with get_connection() as conn:
            cur = conn.cursor()
            cur.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name;")
            tables = cur.fetchall()
            print(f"Таблиц по умолчанию: {len(tables)}")
    except Exception as e:
        print(f"Ошибка: {e}")

if __name__ == "__main__":
    inspect_db()