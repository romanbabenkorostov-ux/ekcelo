#!/usr/bin/env bash
# EkceloFoto — линтинг (advisory; CI этим не гейтит — одностраничник).
# eslint-plugin-html извлекает inline <script> из index.html / v2961.html.
# Первый запуск ставит eslint локально в dev/node_modules (gitignored).
set -e
cd "$(dirname "$0")"
[ -d node_modules/eslint ] || npm install --no-audit --no-fund --silent
npm run --silent lint
echo "lint ok"
