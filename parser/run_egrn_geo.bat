@echo off
rem Запуск окна разбора выписок ЕГРН (контуры, KML, эссе).
rem Перед первым запуском: pip install -e .[gui]
cd /d "%~dp0"
python -m gui.egrn_geo_app
pause
