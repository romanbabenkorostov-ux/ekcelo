@echo off
REM EkceloFoto - smoke-тесты (Windows). Требует Node.js + Python 3 на PATH.
cd /d "%~dp0"
call npx --yes playwright install --with-deps chromium
call npx --yes playwright test %*
