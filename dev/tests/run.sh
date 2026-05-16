#!/usr/bin/env bash
# EkceloFoto — smoke-тесты. Требует Node.js + Python 3 на PATH.
# Первый запуск качает Playwright и Chromium.
set -e
cd "$(dirname "$0")"
npx --yes playwright install --with-deps chromium
npx --yes playwright test "$@"
