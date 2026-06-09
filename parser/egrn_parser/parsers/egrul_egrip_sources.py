"""
egrn_parser/parsers/egrul_egrip_sources.py — адаптеры внешних JSON-источников
данных о субъектах (checko.ru / dadata.ru) → та же нормализованная запись.

Два слоя, разделены намеренно:
  • МАППЕРЫ `from_checko_json` / `from_dadata_json` — чистые функции
    (raw JSON → запись), без сети; тестируются на синтетике.
  • КЛИЕНТ `fetch_by_inn` — опциональный HTTP-запрос по ИНН; читает ключи из
    окружения / `.env`. Без ключа НЕ ходит в сеть, а возвращает понятную ошибку.

Где взять ключи (см. также `parser/.env.example`):
  CHECKO_API_KEY  — https://checko.ru (личный кабинет → API)
  DADATA_API_KEY  + DADATA_SECRET_KEY — https://dadata.ru (профиль → API-ключи)

Файл `.env` кладётся в `parser/.env` (НЕ коммитится, см. `.gitignore`).
Приоритет источников при слиянии — в `egrul_egrip_normalized.SOURCE_PRIORITY`
(официальная ФНС-XML/PDF выше checko/dadata).
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, Optional

from egrn_parser.parsers._common import parse_number
from egrn_parser.parsers.egrul_egrip_normalized import empty_record

log = logging.getLogger(__name__)

# Корень parser/ — для поиска .env.
_PARSER_ROOT = Path(__file__).resolve().parents[2]


def _digits(s: Any) -> Optional[str]:
    if s is None:
        return None
    d = "".join(ch for ch in str(s) if ch.isdigit())
    return d or None


def _fio_from_name(name: Optional[str]) -> Optional[dict]:
    """'ИВАНОВ ИВАН ИВАНОВИЧ' → {last, first, middle}."""
    if not name:
        return None
    parts = str(name).split()
    if len(parts) >= 3:
        return {"last": parts[0], "first": parts[1], "middle": " ".join(parts[2:])}
    if len(parts) == 2:
        return {"last": parts[0], "first": parts[1], "middle": None}
    return {"last": name, "first": None, "middle": None}


# ── checko.ru ────────────────────────────────────────────────────────────────
def from_checko_json(raw: dict[str, Any]) -> dict[str, Any]:
    """checko JSON (ответ API или его `data`) → нормализованная запись.

    checko отдаёт кириллические ключи (НаимПолн/ИНН/ОГРН/Руковод/Учред/…),
    юрлицо и ИП различаются наличием ОГРНИП/ФИО.
    """
    data = raw.get("data") if isinstance(raw.get("data"), dict) else raw

    ogrnip = _digits(data.get("ОГРНИП"))
    is_ip = bool(ogrnip) or data.get("Тип") == "ИП"
    registry = "ЕГРИП" if is_ip else "ЕГРЮЛ"
    rec = empty_record(registry)
    rec["source"] = {"system": "checko", "confidence": 0.9}

    status = data.get("Статус") or {}
    okved = data.get("ОКВЭД") or {}
    # checko: имя ОКВЭД приходит под ключом «Наим» (реже «Наименование»).
    okved_main = {
        "code": okved.get("Код"),
        "name": okved.get("Наим") or okved.get("Наименование") or okved.get("Название"),
    } if okved else None

    if is_ip:
        rec["subject"] = {
            "kind": "person",
            "ogrnip": ogrnip,
            "inn": _digits(data.get("ИНН")),
            "fio": _fio_from_name(data.get("ФИО") or data.get("НаимПолн")),
            "status": {"name": status.get("Наим") or status.get("Наименование")} if status else None,
            "okved_main": okved_main,
        }
        return {"format": {"registry": registry, "source": "checko"}, "records": [rec]}

    rec["subject"] = {
        "kind": "org",
        "ogrn": _digits(data.get("ОГРН")),
        "inn": _digits(data.get("ИНН")),
        "kpp": _digits(data.get("КПП")),
        "name_full": data.get("НаимПолн"),
        "name_short": data.get("НаимСокр"),
        "status": {"name": status.get("Наим") or status.get("Наименование")} if status else None,
        "okved_main": okved_main,
    }
    # Руководители (ЕИО). checko может отдать список или один объект.
    rukovod = data.get("Руковод") or data.get("Руководитель") or []
    if isinstance(rukovod, dict):
        rukovod = [rukovod]
    for d in rukovod:
        rec["directors"].append({
            "fio": _fio_from_name(d.get("ФИО") or d.get("НаимПолн")),
            "inn": _digits(d.get("ИНН")),
            "post": d.get("НаимДолжн") or d.get("Должн") or d.get("Должность"),
        })
    # Учредители: РосОрг (юрлица) + ФЛ (физлица)
    uchr = data.get("Учред") or {}
    for fr in uchr.get("РосОрг") or []:
        rec["founders"].append({
            "kind": "legal",
            "ogrn": _digits(fr.get("ОГРН")),
            "inn": _digits(fr.get("ИНН")),
            "name": fr.get("НаимПолн"),
            "share_percent": (fr.get("Доля") or {}).get("Процент"),
            "share_nominal": (fr.get("Доля") or {}).get("Номинал"),
        })
    for fr in uchr.get("ФЛ") or []:
        rec["founders"].append({
            "kind": "person",
            "fio": _fio_from_name(fr.get("ФИО") or fr.get("НаимПолн")),
            "inn": _digits(fr.get("ИНН")),
            "share_percent": (fr.get("Доля") or {}).get("Процент"),
            "share_nominal": (fr.get("Доля") or {}).get("Номинал"),
        })
    return {"format": {"registry": registry, "source": "checko"}, "records": [rec]}


# ── dadata.ru ────────────────────────────────────────────────────────────────
def from_dadata_json(raw: dict[str, Any]) -> dict[str, Any]:
    """dadata JSON (`suggestion` или весь ответ `findById`) → нормализ. запись.

    dadata отдаёт латинские ключи (inn/ogrn/kpp/name/management/founders/…).
    """
    # Принять и полный ответ {suggestions:[{data}]}, и сам data
    if "suggestions" in raw:
        sugg = (raw.get("suggestions") or [{}])[0]
        data = sugg.get("data") or {}
    elif "data" in raw:
        data = raw.get("data") or {}
    else:
        data = raw

    is_ip = (data.get("type") == "INDIVIDUAL") or bool(data.get("ogrn") and data.get("fio"))
    registry = "ЕГРИП" if is_ip else "ЕГРЮЛ"
    rec = empty_record(registry)
    rec["source"] = {"system": "dadata", "confidence": 0.85}

    name = data.get("name") or {}
    okveds = data.get("okveds") or []
    okved_main = None
    for o in okveds:
        if o.get("main"):
            okved_main = {"code": o.get("code"), "name": o.get("name")}
            break
    state = data.get("state") or {}

    if is_ip:
        fio = data.get("fio") or {}
        rec["subject"] = {
            "kind": "person",
            "ogrnip": _digits(data.get("ogrn")),
            "inn": _digits(data.get("inn")),
            "fio": {"last": fio.get("surname"), "first": fio.get("name"),
                    "middle": fio.get("patronymic")} if fio else _fio_from_name(name.get("full")),
            "status": {"name": state.get("status")} if state else None,
            "okved_main": okved_main,
        }
        return {"format": {"registry": registry, "source": "dadata"}, "records": [rec]}

    mgmt = data.get("management") or {}
    rec["subject"] = {
        "kind": "org",
        "ogrn": _digits(data.get("ogrn")),
        "inn": _digits(data.get("inn")),
        "kpp": _digits(data.get("kpp")),
        "name_full": name.get("full_with_opf") or name.get("full"),
        "name_short": name.get("short_with_opf") or name.get("short"),
        "status": {"name": state.get("status")} if state else None,
        "okved_main": okved_main,
    }
    if mgmt:
        rec["directors"].append({
            "fio": _fio_from_name(mgmt.get("name")),
            "inn": None,
            "post": mgmt.get("post"),
        })
    for fr in data.get("founders") or []:
        if fr.get("type") == "PHYSICAL" or fr.get("fio"):
            rec["founders"].append({
                "kind": "person",
                "fio": _fio_from_name(fr.get("fio") or fr.get("name")),
                "inn": _digits(fr.get("inn")),
                "share_percent": (fr.get("share") or {}).get("value"),
            })
        else:
            rec["founders"].append({
                "kind": "legal",
                "ogrn": _digits(fr.get("ogrn")),
                "inn": _digits(fr.get("inn")),
                "name": fr.get("name"),
                "share_percent": (fr.get("share") or {}).get("value"),
            })
    return {"format": {"registry": registry, "source": "dadata"}, "records": [rec]}


# ── .env / клиент по ИНН (опционально, нужен ключ) ───────────────────────────
def load_env(env_path: Optional[Path] = None) -> dict[str, str]:
    """Прочитать `parser/.env` (KEY=VALUE) в os.environ, не перетирая заданное.

    Без python-dotenv — простой парсер. Возвращает прочитанные пары.
    """
    env_path = env_path or (_PARSER_ROOT / ".env")
    found: dict[str, str] = {}
    if not env_path.is_file():
        return found
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip().strip('"').strip("'")
        found[k] = v
        os.environ.setdefault(k, v)
    return found


def fetch_by_inn(inn: str, *, vendor: str = "checko", timeout: int = 20) -> dict[str, Any]:
    """Запросить данные о субъекте по ИНН из checko/dadata и нормализовать.

    Требует ключ в окружении/`.env`:
      vendor='checko' → CHECKO_API_KEY
      vendor='dadata' → DADATA_API_KEY (+ DADATA_SECRET_KEY)
    Без ключа бросает RuntimeError (в сеть НЕ ходим). Нужен `requests`.
    """
    load_env()
    inn = _digits(inn) or ""
    if not inn:
        raise ValueError("fetch_by_inn: пустой/некорректный ИНН")

    if vendor == "checko":
        key = os.environ.get("CHECKO_API_KEY")
        if not key:
            raise RuntimeError(
                "CHECKO_API_KEY не задан — положи ключ в parser/.env "
                "(см. parser/.env.example). Без ключа checko недоступен.")
        import requests  # noqa: PLC0415
        resp = requests.get(
            "https://api.checko.ru/v2/company",
            params={"key": key, "inn": inn}, timeout=timeout)
        resp.raise_for_status()
        return from_checko_json(resp.json())

    if vendor == "dadata":
        key = os.environ.get("DADATA_API_KEY")
        if not key:
            raise RuntimeError(
                "DADATA_API_KEY не задан — положи ключ в parser/.env "
                "(см. parser/.env.example). Без ключа dadata недоступен.")
        import requests  # noqa: PLC0415
        resp = requests.post(
            "https://suggestions.dadata.ru/suggestions/api/4_1/rs/findById/party",
            headers={"Authorization": f"Token {key}", "Content-Type": "application/json"},
            data=json.dumps({"query": inn}), timeout=timeout)
        resp.raise_for_status()
        return from_dadata_json(resp.json())

    raise ValueError(f"fetch_by_inn: неизвестный vendor '{vendor}' (checko|dadata)")
