# 2026-05-27 — Token-система v1

## Суть
URL-shortener для произвольных публичных ссылок. Клиент получает
`https://ekcelo.ru/?t=<token>` → редирект на исходный URL.

## Архитектура
**Stateless self-contained**: токен = `base64url(UTF-8(url))` без padding.
Никакого реестра, состояния, шифрования. encode/decode зеркальны
в Python и JS.

## Файлы
- `viewer/tokens.js` — ES-модуль, источник истины алгоритма.
- `viewer/token-gate.html` — entry-страница (копируется в `ekcelo-site`).
- `viewer/admin-encode.html` — admin-генератор (URL → токен).
- `tools/ekcelo_tokens.py` — CLI: `encode`/`decode`/`url`.
- `tests/test_ekcelo_tokens.py` — pytest (18 кейсов).
- `tests/test_tokens_js.mjs` — Node-харнес, сверка JS↔Python через
  `tests/fixtures/token_roundtrip.json`.

## Защита
- **Шифрования нет** — это публично-восстановимая ссылка.
- **Защиты от подбора нет и не нужна** — нет секретного списка;
  атакующий и сам может сгенерировать любую короткую ссылку.
- **Защита от мусора на входе**: разрешены только `http://` и
  `https://` URL; токен валидируется по base64url-алфавиту и UTF-8.

## Эксплуатация
```
python3 tools/ekcelo_tokens.py url "https://disk.yandex.ru/d/GLA8p8oHpnv9NA"
# https://ekcelo.ru/?t=aHR0cHM6Ly9kaXNrLnlhbmRleC5ydS9kL0dMQThwOG9IcG52OU5B
```
Или открыть `viewer/admin-encode.html` локально / на GitHub Pages —
ввести URL, скопировать готовую короткую ссылку.

## Поставка `ekcelo-site`
ZIP с `viewer/token-gate.html` под именем `index.html`. CORS не нужен
(`tokens.js` грузится с GitHub Pages с `Access-Control-Allow-Origin: *`).
Не кешировать `tokens.js` агрессивно — алгоритм может перейти на v2.

## v2 на будущее
Если понадобится сжатие (DEFLATE) — токен v2 префиксуется символом
вне base64url-алфавита (например `~`); токены без префикса = v1.
Совместимость без миграции.

## Тесты
```
python3 -m pytest tests/test_ekcelo_tokens.py -v   # 18 passed
node tests/test_tokens_js.mjs                       # OK (5+4)
```
