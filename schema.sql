-- EkceloFoto schema.sql v2.5
-- Справочная схема (применяется автоматически watchdog_exif.py при первом запуске)
-- Для ручного просмотра: DB Browser for SQLite → Open → index.db

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA encoding    = "UTF-8";

-- ─────────────────────────────────────────────────────────────────────────────
-- NODES — дерево объектов (папки / подразделения объекта)
-- path  : UTF-8, разделитель "/", кириллица и пробелы хранятся как есть
--         "Санаторий1"
--         "Санаторий1/Корпус Гамма"
--         "Санаторий1/Корпус Гамма/Номера/SNGL2/3307"
-- node_id: sha1(path) — стабильный ключ, не зависит от переименования в ОС
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS nodes (
    node_id    TEXT PRIMARY KEY,
    path       TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name       TEXT NOT NULL,
    parent_id  TEXT REFERENCES nodes(node_id) ON DELETE CASCADE,
    depth      INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT DEFAULT (datetime('now'))
);

-- ─────────────────────────────────────────────────────────────────────────────
-- FILES — индекс JPG-файлов
-- abs_path      : C:\Photos\Санаторий1\...\IMG.jpg  (для открытия на диске)
-- exif_loc_path : значение loc.path внутри EXIF-файла
-- exif_source   : источник ("local" / URL / "gdrive")
-- path_mismatch : 1 — файл перемещён, EXIF устарел
-- date_mismatch : 1 — mtime файла ≠ DateTimeOriginal (>60 сек)
-- ─────────────────────────────────────────────────────────────────────────────
CREATE TABLE IF NOT EXISTS files (
    file_id        TEXT PRIMARY KEY,
    filename       TEXT NOT NULL,
    abs_path       TEXT NOT NULL UNIQUE,
    node_id        TEXT REFERENCES nodes(node_id) ON DELETE SET NULL,
    size_bytes     INTEGER,
    mtime          REAL,
    gps_lat        REAL,
    gps_lon        REAL,
    gps_bearing    REAL,
    date_taken     TEXT,
    exif_loc_path  TEXT,
    exif_source    TEXT,
    path_mismatch  INTEGER DEFAULT 0,
    date_mismatch  INTEGER DEFAULT 0,
    indexed_at     TEXT DEFAULT (datetime('now'))
);

CREATE INDEX IF NOT EXISTS idx_files_node   ON files(node_id);
CREATE INDEX IF NOT EXISTS idx_nodes_parent ON nodes(parent_id);
CREATE INDEX IF NOT EXISTS idx_nodes_path   ON nodes(path COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_files_mtime  ON files(mtime);
CREATE INDEX IF NOT EXISTS idx_files_gps    ON files(gps_lat, gps_lon) WHERE gps_lat IS NOT NULL;

-- ─────────────────────────────────────────────────────────────────────────────
-- ПОЛЕЗНЫЕ ЗАПРОСЫ
-- ─────────────────────────────────────────────────────────────────────────────

-- Дерево объектов:
-- SELECT depth, path, name FROM nodes ORDER BY path;

-- Все фото в корпусе:
-- SELECT f.filename, f.gps_lat, f.gps_lon, f.date_taken
-- FROM files f JOIN nodes n ON f.node_id = n.node_id
-- WHERE n.path LIKE 'Санаторий1/Корпус Гамма%';

-- Расхождение пути:
-- SELECT filename, abs_path, exif_loc_path FROM files WHERE path_mismatch = 1;

-- Расхождение даты (исправить: watchdog --fix-dates):
-- SELECT filename, abs_path, date_taken FROM files WHERE date_mismatch = 1;

-- Статистика GPS по объектам:
-- SELECT n.path,
--        COUNT(f.file_id)               AS files,
--        SUM(f.gps_lat IS NOT NULL)     AS with_gps,
--        SUM(f.path_mismatch)           AS path_mis,
--        SUM(f.date_mismatch)           AS date_mis
-- FROM nodes n LEFT JOIN files f ON n.node_id = f.node_id
-- GROUP BY n.node_id ORDER BY n.path;
