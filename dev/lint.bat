@echo off
REM EkceloFoto - линтинг (Windows, advisory). Требует Node.js на PATH.
cd /d "%~dp0"
if not exist node_modules\eslint call npm install --no-audit --no-fund --silent
call npm run --silent lint
if %ERRORLEVEL% NEQ 0 exit /b %ERRORLEVEL%
echo lint ok
