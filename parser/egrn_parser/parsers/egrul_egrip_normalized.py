"""
egrn_parser/parsers/egrul_egrip_normalized.py — единая нормализованная запись
для данных о субъектах (ЕГРЮЛ/ЕГРИП) из ЛЮБОГО источника.

Все адаптеры (ФНС-XML, ФНС-PDF, checko/dadata-JSON) отдают запись одной формы,
чтобы downstream (запись в БД, граф) не знал про источник. Конфликты между
источниками разрешаются приоритетом `source.system` (см. `SOURCE_PRIORITY`).

Форма записи (одна на субъект / на `Документ`):
    {
      "registry": "ЕГРЮЛ" | "ЕГРИП",
      "subject":  {...},          # идентификация + статус + ОКВЭД
      "directors":     [...],     # ЕИО-физлица (ФИО, ИНН, должность)
      "managing_orgs": [...],     # управляющая организация (ОГРН/ИНН/наим)
      "founders":      [...],     # учредители/участники (+ доля %/номинал)
      "predecessors":  [...],     # право-предшественники (реорганизация)
      "successors":    [...],     # право-преемники (реорганизация)
      "source":   {...},          # system / confidence / file / ...
    }
"""

from __future__ import annotations

from typing import Any

# Приоритет источников: официальная ФНС-XML > ФНС-PDF > checko/dadata > LLM.
# Чем меньше индекс — тем выше доверие (используется при gap-fill merge).
SOURCE_PRIORITY: list[str] = [
    "ФНС-ЕГРЮЛ-XML",
    "ФНС-ЕГРИП-XML",
    "ФНС-ЕГРЮЛ-PDF",
    "ФНС-ЕГРИП-PDF",
    "checko",
    "dadata",
    "llm",
]


def empty_record(registry: str) -> dict[str, Any]:
    """Пустая нормализованная запись для реестра ("ЕГРЮЛ"/"ЕГРИП")."""
    return {
        "registry": registry,
        "subject": {},
        "directors": [],
        "managing_orgs": [],
        "founders": [],
        "predecessors": [],
        "successors": [],
        "source": {},
    }


def _rank(system: str) -> int:
    try:
        return SOURCE_PRIORITY.index(system)
    except ValueError:
        return len(SOURCE_PRIORITY)


def merge_records(records: list[dict[str, Any]]) -> dict[str, Any]:
    """Gap-fill нескольких записей об ОДНОМ субъекте по приоритету источника.

    Скалярные поля `subject`: берём значение от самого приоритетного источника,
    у которого оно непустое. Списки связей (`directors`/`founders`/…): берём
    непустой список от самого приоритетного источника (не сливаем поэлементно —
    у разных источников разная гранулярность; поэлементный merge — отдельная
    задача, когда будет БД-слой).
    """
    if not records:
        raise ValueError("merge_records: пустой список")
    ordered = sorted(records, key=lambda r: _rank((r.get("source") or {}).get("system", "")))
    out = empty_record(ordered[0].get("registry") or "")
    out["source"] = {
        "merged_from": [(r.get("source") or {}).get("system") for r in ordered],
    }
    # subject: скаляры gap-fill
    subj: dict[str, Any] = {}
    for r in ordered:
        for k, v in (r.get("subject") or {}).items():
            if k not in subj or subj[k] in (None, "", {}, []):
                if v not in (None, "", {}, []):
                    subj[k] = v
    out["subject"] = subj
    # связи: первый непустой список по приоритету
    for key in ("directors", "managing_orgs", "founders", "predecessors", "successors"):
        for r in ordered:
            if r.get(key):
                out[key] = r[key]
                break
    return out
