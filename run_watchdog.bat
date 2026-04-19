@echo off
chcp 65001 >nul
:: ============================================================
::  EkceloFoto — watchdog + EXIF loc.path + SQLite
::
::  НАСТРОЙТЕ ЭТИ ДВЕ СТРОКИ:
set PHOTO_ROOT=C:\Photos
set DB_PATH=C:\Photos\index.db
:: ============================================================

echo Запускаем watchdog для: %PHOTO_ROOT%
echo База данных:            %DB_PATH%
echo.
echo При первом запуске — полное сканирование (mtime сохраняется).
echo Ctrl+C для остановки.
echo.

python scripts\watchdog_exif.py ^
    --root "%PHOTO_ROOT%" ^
    --db   "%DB_PATH%"   ^
    --log  INFO

pause
