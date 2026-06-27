# 2026-06-09 — Шаблоны входных данных для экономиста + план фронтенда

## Файлы-шаблоны (проверены парсерами) — `Golden-Path-Economist/templates/`
Для каждого типа входных данных — заполняемый шаблон + файл-описание:
| Шаблон | Формат | Описание | Парсер |
|---|---|---|---|
| `nspd_geometriya_TEMPLATE.json` | JSON | `nspd_geometriya.ОПИСАНИЕ.md` | land_ingest → land_contours |
| `perechen_nasazhdeniy_TEMPLATE.txt` | текст | `perechen_nasazhdeniy.ОПИСАНИЕ.md` | vineyard_perechen |
| `tehkarta_vinogradnik_TEMPLATE.xlsx` | Excel | `tehkarta_vinogradnik.ОПИСАНИЕ.md` | agro_techcard |
| `osv_tehnika_TEMPLATE.xlsx` | Excel | `osv_tehnika.ОПИСАНИЕ.md` | osv_assets → fixed_asset |
| `etp_pravki_TEMPLATE.yaml` | YAML | `etp_pravki.ОПИСАНИЕ.md` | etl_osv → object_etp_profile |
| `lot_TEMPLATE.yaml` | YAML | `lot.ОПИСАНИЕ.md` | etl_osv / bundle --lot-id |
+ индекс `ИНДЕКС_ШАБЛОНОВ.md`.

**Проверка загрузки (требование 1):** Excel-шаблоны прогнаны парсерами —
ОСВ: 3 ОС (1 ОКС на 01.08); техкарта: виноград, 4 операции + 2 пестицида/1 удобрение.
Текст/YAML/JSON — совместимы с загрузчиками.

## Интеграция в золотой путь
В `Golden-Path-Economist/README.md` добавлена секция «📂 Шаблоны для загрузки +
описания» со ссылками на каждый шаблон и его описание.

## План фронтенда — `Architecture/frontend-plan.md`
- **Удобство без фронтенда сейчас:** папка проекта = шаблоны; прогон демо; Bundle;
  Obsidian как панель. **Фаза 0:** CLI `ingest-project --dir` (обёртка-загрузчик папки).
- **Варианты фронтенда:** (1) Веб FastAPI, (2) Obsidian-нативный, (3) Десктоп,
  (4) только CLI+Excel. Фазовый план: Загрузка → Просмотр → Сборка пакета → Карта.
- Ожидается выбор заказчика (задан вопрос).

## Файлы
- `obsidian/Golden-Path-Economist/templates/*` (6 шаблонов + 6 описаний + индекс)
- `obsidian/Golden-Path-Economist/README.md` (секция шаблонов)
- `obsidian/Architecture/frontend-plan.md` (новый)
