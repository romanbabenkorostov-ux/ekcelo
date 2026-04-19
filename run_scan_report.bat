@echo off
chcp 65001 >nul
:: ============================================================
::  EkceloFoto — разовое сканирование + HTML-отчёт
::
::  НАСТРОЙТЕ:
set PHOTO_ROOT=C:\Photos
set DB_PATH=C:\Photos\index.db
set REPORT_PATH=C:\Photos\report.html
::
::  Добавьте --fix-dates чтобы выровнять mtime файлов по EXIF DateTimeOriginal
:: ============================================================

echo Сканируем: %PHOTO_ROOT%
echo БД:        %DB_PATH%
echo.

python scripts\watchdog_exif.py ^
    --root      "%PHOTO_ROOT%" ^
    --db        "%DB_PATH%"   ^
    --scan-only ^
    --log       INFO

echo.
echo Генерируем HTML-отчёт...
python scripts\report_html.py ^
    --db  "%DB_PATH%"   ^
    --out "%REPORT_PATH%"

echo.
echo Открываем отчёт...
start "" "%REPORT_PATH%"
pause
