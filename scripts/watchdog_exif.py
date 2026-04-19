# -*- coding: utf-8 -*-
"""
EkceloFoto — watchdog_exif.py  v2.5
=====================================
Мониторит папку с фотографиями (Win10, локальный диск).
При появлении / изменении / перемещении JPG:
  1. Вычисляет loc.path = относительный путь папки от корня (UTF-8, forward-slash)
  2. Дописывает/обновляет блок "loc" в GPP-JSON внутри EXIF UserComment
  3. Сохраняет mtime файла (дата изменения остаётся прежней)
  4. Обновляет запись в SQLite-базе

Запуск:
    python watchdog_exif.py --root "C:\\Photos" --db "C:\\Photos\\index.db"

Разовая индексация (без watchdog):
    python watchdog_exif.py --root "C:\\Photos" --db "C:\\Photos\\index.db" --scan-only

Выравнивание mtime файла с DateTimeOriginal из EXIF:
    python watchdog_exif.py --root "C:\\Photos" --db "C:\\Photos\\index.db" --fix-dates --scan-only

Флаги:
    --no-exif       не перезаписывать EXIF (только индексировать в SQLite)
    --fix-dates     установить mtime файла = DateTimeOriginal из EXIF
    --scan-only     разовое сканирование, без watchdog
    --log DEBUG     подробный лог

Зависимости:
    pip install piexif watchdog
Опционально (для точного ctime на Windows):
    pip install pywin32
"""

import os
import sys
import json
import time
import hashlib
import sqlite3
import logging
import argparse
import shutil
import struct
from datetime import datetime
from pathlib import Path

try:
    import piexif
except ImportError:
    sys.exit("Ошибка: pip install piexif")

try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    sys.exit("Ошибка: pip install watchdog")

# Опциональный модуль для работы с датами создания на Windows
try:
    import win32file, win32con, pywintypes
    HAS_WIN32 = True
except ImportError:
    HAS_WIN32 = False


# ═════════════════════════════════════════════════════════════════════════════
# PATH UTILITIES
# ═════════════════════════════════════════════════════════════════════════════

PHOTO_EXTS = {".jpg", ".jpeg"}


def is_photo(path: Path) -> bool:
    return path.suffix.lower() in PHOTO_EXTS


def fs_to_loc_path(abs_path: Path, root: Path) -> str:
    """
    Вычисляет loc.path: относительный путь *папки* от корня.
    UTF-8, разделитель '/', кириллица и пробелы сохраняются как есть.

    C:\\Photos\\Санаторий1\\Корпус Гамма\\IMG.jpg  →  "Санаторий1/Корпус Гамма"
    C:\\Photos\\IMG.jpg (в корне)                  →  "" (пустая строка)
    """
    try:
        rel = abs_path.parent.relative_to(root)
    except ValueError:
        return ""
    parts = rel.parts
    if not parts:
        return ""
    return "/".join(p.replace("\\", "/") for p in parts)


def node_id(path: str) -> str:
    return hashlib.sha1(path.encode("utf-8")).hexdigest()


def file_id(abs_path: Path) -> str:
    return hashlib.sha1(str(abs_path).encode("utf-8")).hexdigest()


# ═════════════════════════════════════════════════════════════════════════════
# FILE TIMESTAMPS
# Сохраняем atime + mtime; на Windows дополнительно — ctime (если pywin32 есть).
# ═════════════════════════════════════════════════════════════════════════════

class FileTimestamps:
    """Захватывает и восстанавливает временны́е метки файла."""

    def __init__(self, path: Path):
        self.path = path
        stat = path.stat()
        self.atime = stat.st_atime
        self.mtime = stat.st_mtime
        # Windows creation time через pywin32
        self._ctime_win = None
        if HAS_WIN32 and sys.platform == "win32":
            try:
                handle = win32file.CreateFile(
                    str(path), win32con.GENERIC_READ,
                    win32con.FILE_SHARE_READ, None,
                    win32con.OPEN_EXISTING, 0, None
                )
                times = win32file.GetFileTime(handle)
                win32file.CloseHandle(handle)
                self._ctime_win = times[0]   # FILETIME creation
            except Exception:
                pass

    def restore(self):
        """Восстанавливает atime, mtime и (если возможно) ctime."""
        try:
            os.utime(str(self.path), (self.atime, self.mtime))
        except OSError:
            pass

        if HAS_WIN32 and sys.platform == "win32" and self._ctime_win is not None:
            try:
                handle = win32file.CreateFile(
                    str(self.path), win32con.GENERIC_WRITE,
                    0, None, win32con.OPEN_EXISTING, 0, None
                )
                win32file.SetFileTime(handle, self._ctime_win, None, None)
                win32file.CloseHandle(handle)
            except Exception:
                pass


# ═════════════════════════════════════════════════════════════════════════════
# EXIF READ / WRITE
# ═════════════════════════════════════════════════════════════════════════════

ASCII_PREFIX = b"ASCII\x00\x00\x00"


def _decode_user_comment(raw: bytes) -> dict | None:
    if not raw:
        return None
    payload = raw[8:] if raw.startswith(ASCII_PREFIX) else raw
    try:
        text = payload.decode("utf-8").strip("\x00").strip()
        return json.loads(text) if text else None
    except (UnicodeDecodeError, json.JSONDecodeError):
        return None


def read_gpp(exif_dict: dict) -> dict:
    raw = exif_dict.get("Exif", {}).get(piexif.ExifIFD.UserComment)
    if not raw:
        return {}
    result = _decode_user_comment(raw)
    return result if isinstance(result, dict) else {}


def write_gpp(exif_dict: dict, gpp: dict):
    text = json.dumps(gpp, ensure_ascii=False, separators=(",", ":"))
    payload = ASCII_PREFIX + text.encode("utf-8")
    exif_dict.setdefault("Exif", {})[piexif.ExifIFD.UserComment] = payload


def update_exif_loc(jpg_path: Path, loc_path: str, source: str = "") -> bool:
    """
    Читает JPEG → обновляет loc.{path, source} в GPP UserComment → пишет обратно.
    Сохраняет ВСЕ остальные EXIF-теги и временны́е метки файла.
    """
    timestamps = FileTimestamps(jpg_path)

    try:
        exif_dict = piexif.load(str(jpg_path))
    except Exception as e:
        log.warning("Не удалось прочитать EXIF %s: %s", jpg_path.name, e)
        exif_dict = {"0th": {}, "Exif": {}, "GPS": {}, "1st": {}}

    gpp = read_gpp(exif_dict)
    gpp.setdefault("app", "gpp")
    gpp["v"] = max(gpp.get("v", 1), 2)

    loc: dict = {"path": loc_path}
    if source:
        loc["source"] = source   # URL или "local" — откуда файл
    gpp["loc"] = loc

    write_gpp(exif_dict, gpp)

    tmp = jpg_path.with_suffix(".~tmp")
    try:
        exif_bytes = piexif.dump(exif_dict)
        piexif.insert(exif_bytes, str(jpg_path), str(tmp))
        shutil.move(str(tmp), str(jpg_path))
    except Exception as e:
        log.error("Ошибка записи EXIF %s: %s", jpg_path.name, e)
        tmp.unlink(missing_ok=True)
        return False
    finally:
        timestamps.restore()   # всегда восстанавливаем временны́е метки

    return True


def fix_file_date(jpg_path: Path) -> bool:
    """
    Устанавливает mtime файла = DateTimeOriginal из EXIF.
    Используется с флагом --fix-dates.
    """
    try:
        exif_dict = piexif.load(str(jpg_path))
    except Exception:
        return False

    exif = exif_dict.get("Exif", {})
    raw = exif.get(piexif.ExifIFD.DateTimeOriginal)
    if not raw:
        return False

    date_str = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else str(raw)
    # Формат EXIF: "2024:05:15 10:23:44"
    m = __import__("re").match(r"(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})", date_str)
    if not m:
        return False

    dt = datetime(int(m[1]), int(m[2]), int(m[3]), int(m[4]), int(m[5]), int(m[6]))
    ts = dt.timestamp()

    stat = jpg_path.stat()
    try:
        os.utime(str(jpg_path), (stat.st_atime, ts))
        log.info("  mtime → %s", dt.strftime("%d.%m.%Y %H:%M:%S"))
        return True
    except OSError as e:
        log.warning("  os.utime failed: %s", e)
        return False


def read_exif_for_db(jpg_path: Path) -> dict:
    result = {
        "gps_lat": None, "gps_lon": None, "gps_bearing": None,
        "date_taken": None, "exif_loc_path": None, "exif_source": None,
    }
    try:
        exif_dict = piexif.load(str(jpg_path))
        gps = exif_dict.get("GPS", {})
        lat_v = gps.get(piexif.GPSIFD.GPSLatitude)
        lat_r = gps.get(piexif.GPSIFD.GPSLatitudeRef)
        lon_v = gps.get(piexif.GPSIFD.GPSLongitude)
        lon_r = gps.get(piexif.GPSIFD.GPSLongitudeRef)
        bearing = gps.get(piexif.GPSIFD.GPSImgDirection)

        if lat_v and lat_r:
            result["gps_lat"] = _dms_to_dec(lat_v, lat_r)
        if lon_v and lon_r:
            result["gps_lon"] = _dms_to_dec(lon_v, lon_r)
        if bearing:
            n, d = bearing
            result["gps_bearing"] = n / d if d else None

        exif = exif_dict.get("Exif", {})
        raw_date = exif.get(piexif.ExifIFD.DateTimeOriginal)
        if raw_date:
            result["date_taken"] = (
                raw_date.decode("utf-8", errors="replace")
                if isinstance(raw_date, bytes) else str(raw_date)
            )

        gpp = read_gpp(exif_dict)
        if gpp and "loc" in gpp:
            result["exif_loc_path"] = gpp["loc"].get("path") or ""
            result["exif_source"]   = gpp["loc"].get("source") or ""

    except Exception as e:
        log.debug("EXIF read error %s: %s", jpg_path.name, e)

    return result


def _dms_to_dec(dms, ref) -> float | None:
    try:
        d = dms[0][0] / dms[0][1]
        m = dms[1][0] / dms[1][1]
        s = dms[2][0] / dms[2][1]
        dec = d + m / 60 + s / 3600
        r = ref.decode() if isinstance(ref, bytes) else str(ref)
        return -dec if r in ("S", "W") else dec
    except Exception:
        return None


# ═════════════════════════════════════════════════════════════════════════════
# SQLite
# ═════════════════════════════════════════════════════════════════════════════

SCHEMA_SQL = """
PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA encoding = "UTF-8";

CREATE TABLE IF NOT EXISTS nodes (
    node_id    TEXT PRIMARY KEY,
    path       TEXT NOT NULL UNIQUE COLLATE NOCASE,
    name       TEXT NOT NULL,
    parent_id  TEXT REFERENCES nodes(node_id) ON DELETE CASCADE,
    depth      INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT DEFAULT (datetime('now'))
);

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
CREATE INDEX IF NOT EXISTS idx_files_gps    ON files(gps_lat, gps_lon)
    WHERE gps_lat IS NOT NULL;
"""


def init_db(db_path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    conn.executescript(SCHEMA_SQL)
    conn.commit()
    return conn


def ensure_node_path(conn: sqlite3.Connection, path: str):
    if not path:
        return
    parts = path.split("/")
    for i in range(len(parts)):
        sub_path = "/".join(parts[: i + 1])
        name = parts[i]
        parent_path = "/".join(parts[:i]) if i > 0 else None
        pid = node_id(parent_path) if parent_path else None
        conn.execute(
            "INSERT OR IGNORE INTO nodes (node_id, path, name, parent_id, depth) VALUES (?,?,?,?,?)",
            (node_id(sub_path), sub_path, name, pid, i),
        )
    conn.commit()


def _date_mismatch(jpg_path: Path, date_taken: str | None) -> int:
    """1 если mtime файла отличается от DateTimeOriginal более чем на 60 сек."""
    if not date_taken:
        return 0
    import re
    m = re.match(r"(\d{4}):(\d{2}):(\d{2}) (\d{2}):(\d{2}):(\d{2})", date_taken)
    if not m:
        return 0
    try:
        dt = datetime(int(m[1]), int(m[2]), int(m[3]), int(m[4]), int(m[5]), int(m[6]))
        diff = abs(dt.timestamp() - jpg_path.stat().st_mtime)
        return 1 if diff > 60 else 0
    except Exception:
        return 0


def upsert_file(conn: sqlite3.Connection, jpg_path: Path, root: Path):
    fs_path  = fs_to_loc_path(jpg_path, root)
    exif     = read_exif_for_db(jpg_path)
    exif_path = exif.get("exif_loc_path") or ""
    mismatch  = int(bool(exif_path) and fs_path != exif_path)
    date_mis  = _date_mismatch(jpg_path, exif.get("date_taken"))

    if fs_path:
        ensure_node_path(conn, fs_path)

    nid  = node_id(fs_path) if fs_path else None
    stat = jpg_path.stat()

    conn.execute(
        """
        INSERT INTO files (
            file_id, filename, abs_path, node_id,
            size_bytes, mtime, gps_lat, gps_lon, gps_bearing,
            date_taken, exif_loc_path, exif_source,
            path_mismatch, date_mismatch, indexed_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,datetime('now'))
        ON CONFLICT(file_id) DO UPDATE SET
            filename      = excluded.filename,
            abs_path      = excluded.abs_path,
            node_id       = excluded.node_id,
            size_bytes    = excluded.size_bytes,
            mtime         = excluded.mtime,
            gps_lat       = excluded.gps_lat,
            gps_lon       = excluded.gps_lon,
            gps_bearing   = excluded.gps_bearing,
            date_taken    = excluded.date_taken,
            exif_loc_path = excluded.exif_loc_path,
            exif_source   = excluded.exif_source,
            path_mismatch = excluded.path_mismatch,
            date_mismatch = excluded.date_mismatch,
            indexed_at    = datetime('now')
        """,
        (
            file_id(jpg_path), jpg_path.name, str(jpg_path), nid,
            stat.st_size, stat.st_mtime,
            exif["gps_lat"], exif["gps_lon"], exif["gps_bearing"],
            exif["date_taken"], exif["exif_loc_path"], exif["exif_source"],
            mismatch, date_mis,
        ),
    )
    conn.commit()


def remove_file(conn: sqlite3.Connection, abs_path: Path):
    conn.execute("DELETE FROM files WHERE file_id = ?", (file_id(abs_path),))
    conn.commit()


# ═════════════════════════════════════════════════════════════════════════════
# FULL SCAN
# ═════════════════════════════════════════════════════════════════════════════

def full_scan(root: Path, conn: sqlite3.Connection,
              update_exif: bool = True, fix_dates: bool = False):
    jpgs = [p for p in root.rglob("*") if p.is_file() and is_photo(p)]
    total = len(jpgs)
    log.info("Full scan: %d файлов в %s", total, root)

    for i, jpg in enumerate(jpgs, 1):
        loc_path = fs_to_loc_path(jpg, root)

        if update_exif and loc_path:
            ok = update_exif_loc(jpg, loc_path, source="local")
            if not ok:
                log.warning("  EXIF пропущен: %s", jpg.name)

        if fix_dates:
            fixed = fix_file_date(jpg)
            if fixed:
                log.info("  mtime исправлен: %s", jpg.name)

        upsert_file(conn, jpg, root)

        if i % 100 == 0 or i == total:
            log.info("  %d / %d", i, total)

    log.info("Scan завершён.")


# ═════════════════════════════════════════════════════════════════════════════
# WATCHDOG
# ═════════════════════════════════════════════════════════════════════════════

class PhotoHandler(FileSystemEventHandler):
    def __init__(self, root: Path, conn: sqlite3.Connection,
                 update_exif: bool = True, fix_dates: bool = False):
        self.root = root
        self.conn = conn
        self.update_exif = update_exif
        self.fix_dates = fix_dates
        self._debounce: dict[str, float] = {}

    def _debounced(self, path: str) -> bool:
        now = time.monotonic()
        if now - self._debounce.get(path, 0.0) < 1.5:
            return False
        self._debounce[path] = now
        return True

    def _handle(self, abs_path: Path):
        if not abs_path.exists() or not is_photo(abs_path):
            return
        if not self._debounced(str(abs_path)):
            return

        loc_path = fs_to_loc_path(abs_path, self.root)
        log.info("→ %s  [%s]", abs_path.name, loc_path or "<корень>")

        if self.update_exif and loc_path:
            ok = update_exif_loc(abs_path, loc_path, source="local")
            log.info("  EXIF %s", "OK" if ok else "ОШИБКА")

        if self.fix_dates:
            fix_file_date(abs_path)

        upsert_file(self.conn, abs_path, self.root)
        log.info("  БД обновлена")

    def on_created(self, event):
        if not event.is_directory:
            self._handle(Path(event.src_path))

    def on_modified(self, event):
        if not event.is_directory:
            self._handle(Path(event.src_path))

    def on_moved(self, event):
        if not event.is_directory:
            remove_file(self.conn, Path(event.src_path))
            log.info("← перемещён: %s", Path(event.src_path).name)
            self._handle(Path(event.dest_path))

    def on_deleted(self, event):
        if not event.is_directory and is_photo(Path(event.src_path)):
            remove_file(self.conn, Path(event.src_path))
            log.info("← удалён: %s", Path(event.src_path).name)


# ═════════════════════════════════════════════════════════════════════════════
# CLI
# ═════════════════════════════════════════════════════════════════════════════

log = logging.getLogger("ekcelo")


def main():
    parser = argparse.ArgumentParser(
        description="EkceloFoto — watchdog EXIF loc.path + SQLite",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--root",       required=True)
    parser.add_argument("--db",         required=True)
    parser.add_argument("--no-exif",    action="store_true")
    parser.add_argument("--fix-dates",  action="store_true",
                        help="Установить mtime файла = DateTimeOriginal из EXIF")
    parser.add_argument("--scan-only",  action="store_true")
    parser.add_argument("--log",        default="INFO",
                        choices=["DEBUG", "INFO", "WARNING", "ERROR"])
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log),
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
        handlers=[
            logging.StreamHandler(sys.stdout),
            logging.FileHandler("ekcelo_watchdog.log", encoding="utf-8"),
        ],
    )

    root    = Path(args.root).resolve()
    db_path = Path(args.db).resolve()

    if not root.is_dir():
        log.error("Папка не найдена: %s", root)
        sys.exit(1)

    if HAS_WIN32:
        log.info("pywin32: ctime защита активна")
    else:
        log.info("pywin32 не найден — ctime не защищён (pip install pywin32 для полной защиты)")

    conn = init_db(db_path)
    full_scan(root, conn,
              update_exif=not args.no_exif,
              fix_dates=args.fix_dates)

    if args.scan_only:
        conn.close()
        log.info("--scan-only: завершено.")
        return

    handler  = PhotoHandler(root, conn,
                            update_exif=not args.no_exif,
                            fix_dates=args.fix_dates)
    observer = Observer()
    observer.schedule(handler, str(root), recursive=True)
    observer.start()
    log.info("Watchdog запущен. Ctrl+C для остановки.")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        observer.stop()
        observer.join()
        conn.close()
        log.info("Watchdog остановлен.")


if __name__ == "__main__":
    main()
