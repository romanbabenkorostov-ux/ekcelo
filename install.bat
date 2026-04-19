@echo off
chcp 65001 >nul
echo ============================================
echo  EkceloFoto v2.5 — установка зависимостей
echo ============================================
echo.
python --version >nul 2>&1
if errorlevel 1 (
    echo [ОШИБКА] Python не найден.
    echo Скачайте с https://python.org  (добавьте в PATH при установке)
    pause & exit /b 1
)
python --version
echo.
echo Устанавливаем piexif и watchdog...
pip install -r scripts\requirements.txt
if errorlevel 1 (
    echo [ОШИБКА] Установка не удалась.
    pause & exit /b 1
)
echo.
echo [OK] Готово. Далее:
echo   1. Отредактируйте run_watchdog.bat  — пропишите PHOTO_ROOT и DB_PATH
echo   2. Запустите run_watchdog.bat
echo.
pause
