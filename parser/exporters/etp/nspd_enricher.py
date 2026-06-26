"""nspd_enricher: дополняет object_etp_profile данными из NSPD.

Цель — закрыть оставшиеся §10 SPEC гэпы:
- `building.building_type` ← `wall_material` из NSPD.
- `building.year_built`   ← `year_built` (или `year_used` как fallback).
- `legal.use_type_permitted` ← `permitted_uses` (если ЕГРН пуст).

Подход:
- Этот модуль НЕ ходит в HTTP. Он принимает уже разобранные NSPD-данные
  (от `parser/scripts/01_parsing_nspd_v8.py` или его наследников).
- При мерже в `object_etp_profile.building_extra` / `.legal_extra`
  **никогда не перезаписывает существующие значения** — только заполняет
  пустые. Ручной ввод экономиста (osv/manual) остаётся в приоритете.
- При создании новой записи в `object_etp_profile` ставит
  `source='nspd', confidence=0.8` (среднее доверие).

См. `obsidian/Architecture/etl-osv.md` и `obsidian/Architecture/etp-exporter.md`.
"""
from __future__ import annotations

import json
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from egrn_parser.etp_merge import merge_profile

# Маска per-object имени файла (01b): `23_50_0301004_25` / `23_50_0301004_25-9`.
_CAD_MASK_RE = re.compile(r"^\d{1,2}_\d{1,2}_\d{1,7}_\d+(?:-\d+)?$")


def _unmask_cad(stem: str) -> str:
    """Имя файла-маска `61_44_0050706_31` → КН `61:44:0050706:31` (если совпадает
    с маской; иначе без изменений — стемы с `:` уже валидны). Кросс-платформенно:
    Windows запрещает `:` в именах файлов, поэтому per-object файлы — в маске."""
    if _CAD_MASK_RE.match(stem):
        return stem.replace("_", ":", 3).replace("-", "/", 1)
    return stem


DEFAULT_SOURCE = "nspd"
DEFAULT_CONFIDENCE = 0.8


# ─────────────────────────────────────────────────────────────────────────────
#  Нормализация NSPD-полей
# ─────────────────────────────────────────────────────────────────────────────

# Карта материала стен NSPD → читабельная строка для шаблона.
_WALL_MATERIAL_MAP = {
    "кирпич": "кирпичное",
    "кирпичные": "кирпичное",
    "панель": "панельное",
    "панельные": "панельное",
    "монолит": "монолитное",
    "монолитные": "монолитное",
    "бетон": "бетонное",
    "бетонные": "бетонное",
    "блочные": "блочное",
    "блок": "блочное",
    "дерево": "деревянное",
    "деревянные": "деревянное",
    "смешанные": "смешанное",
}


def normalize_wall_material(value: Any) -> str | None:
    """`кирпич` → `кирпичное`. None / неизвестное → None."""
    if not value:
        return None
    s = str(value).strip().lower()
    if not s:
        return None
    if s in _WALL_MATERIAL_MAP:
        return _WALL_MATERIAL_MAP[s]
    # Подстрочное совпадение: «Кирпичные стены» → «кирпичное»
    for key, mapped in _WALL_MATERIAL_MAP.items():
        if key in s:
            return mapped
    # Иначе — возвращаем как есть (например, экзотический материал).
    return str(value).strip()


def normalize_year(value: Any) -> int | None:
    """`"1975"` или `1975` → 1975. Невалидное → None."""
    if value is None:
        return None
    try:
        n = int(str(value).strip())
    except (TypeError, ValueError):
        return None
    return n if 1700 <= n <= 2100 else None


def normalize_permitted_uses(value: Any) -> str | None:
    """`["A", "B"]` или `"A; B"` → `"A; B"`. None/empty → None."""
    if value is None or value == "":
        return None
    if isinstance(value, list):
        items = [str(x).strip() for x in value if str(x).strip()]
        return "; ".join(items) if items else None
    return str(value).strip() or None


# ─────────────────────────────────────────────────────────────────────────────
#  Merge в БД
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class EnrichReport:
    cad_number: str
    profile_created: bool = False
    building_extra_filled: list[str] = None   # type: ignore[assignment]
    legal_extra_filled: list[str] = None      # type: ignore[assignment]
    skipped_reason: str | None = None

    def __post_init__(self):
        if self.building_extra_filled is None:
            self.building_extra_filled = []
        if self.legal_extra_filled is None:
            self.legal_extra_filled = []

    @property
    def changed(self) -> bool:
        return self.profile_created or bool(self.building_extra_filled) or bool(self.legal_extra_filled)


def merge_nspd_into_profile(
    conn: sqlite3.Connection,
    cad_number: str,
    nspd_data: dict[str, Any],
    *,
    source: str = DEFAULT_SOURCE,
    confidence: float = DEFAULT_CONFIDENCE,
) -> EnrichReport:
    """Заполнить пустые поля профиля КН из NSPD-данных (gap-fill).

    Args:
        conn: соединение с БД.
        cad_number: ключ объекта.
        nspd_data: словарь с уже нормализованными NSPD-полями.
            Ожидаемые ключи (все опциональные):
              - `wall_material` (любой регистр/число склонения) → building_type
              - `year_built` или `year_used` → year_built
              - `permitted_uses` (list или string) → use_type_permitted
        source: значение `object_etp_profile.source` при создании записи.
        confidence: значение `confidence` при создании записи.

    Returns:
        EnrichReport с перечнем заполненных полей. Не модифицирует существующие
        значения, ставит только пропуски (None).

    Raises:
        sqlite3.IntegrityError: если cad_number отсутствует в `objects` (FK).
    """
    report = EnrichReport(cad_number=cad_number)
    conn.row_factory = sqlite3.Row

    building_type = normalize_wall_material(nspd_data.get("wall_material"))
    year_built = normalize_year(
        nspd_data.get("year_built") or nspd_data.get("year_used")
    )
    permitted_uses = normalize_permitted_uses(nspd_data.get("permitted_uses"))

    if not any([building_type, year_built, permitted_uses]):
        report.skipped_reason = "no_actionable_nspd_fields"
        return report

    # Единая точка записи §6 — etp_merge.merge_profile (gap-fill: NSPD не затирает
    # ручной ввод osv/manual). report заполняется из changed_keys по колонкам.
    building_extra: dict[str, Any] = {}
    if building_type:
        building_extra["building_type"] = building_type
    if year_built is not None:
        building_extra["year_built"] = year_built
    legal_extra = {"use_type_permitted": permitted_uses} if permitted_uses else {}

    res = merge_profile(
        conn, cad_number,
        {"building_extra": building_extra, "legal_extra": legal_extra},
        source=source, confidence=confidence, strategy="gapfill", commit=False)

    report.building_extra_filled = res["changed_keys"].get("building_extra", [])
    report.legal_extra_filled = res["changed_keys"].get("legal_extra", [])
    report.profile_created = res["created"]
    if not report.changed:
        report.skipped_reason = "all_fields_already_filled"
    return report


def enrich_from_directory(
    conn: sqlite3.Connection,
    directory: str | Path,
    *,
    source: str = DEFAULT_SOURCE,
    confidence: float = DEFAULT_CONFIDENCE,
) -> list[EnrichReport]:
    """Прогон по директории с NSPD JSON (по одному файлу на КН).

    Ожидаемое имя файла: `<cad_number>.json` (или с любым префиксом, в файле
    обязательно поле `cad_number` либо ключи NSPD напрямую).

    Args:
        directory: путь к каталогу с JSON-файлами от NSPD.
        source / confidence: как в merge_nspd_into_profile.

    Returns:
        Список ApplyReport по каждому файлу.
    """
    directory = Path(directory)
    reports: list[EnrichReport] = []
    for path in sorted(directory.glob("*.json")):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue
        # Файл может содержать массив объектов или один объект. fallback-КН — из
        # имени файла (маска `_`→`:` для кросс-платформенности, см. _unmask_cad).
        records = _extract_records(data, fallback_cad=_unmask_cad(path.stem))
        for cad, payload in records:
            try:
                reports.append(
                    merge_nspd_into_profile(conn, cad, payload,
                                            source=source, confidence=confidence)
                )
            except sqlite3.IntegrityError as e:
                reports.append(EnrichReport(cad_number=cad, skipped_reason=f"fk_error: {e}"))
    return reports


# ─────────────────────────────────────────────────────────────────────────────
#  Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _extract_records(data: Any, fallback_cad: str) -> Iterable[tuple[str, dict]]:
    """Извлечь пары (cad_number, payload) из NSPD JSON.

    Поддерживаемые формы:
    - {"cad_number": "...", ...} → одна пара.
    - {"objects": [{"cad_number": ..., ...}, ...]} → много пар.
    - [{"cad_number": ..., ...}, ...] → много пар.
    - {NSPD-поля без cad_number} → одна пара с cad=fallback_cad (имя файла).
    """
    if isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                cad = item.get("cad_number") or fallback_cad
                yield cad, item
        return
    if isinstance(data, dict):
        if "objects" in data and isinstance(data["objects"], list):
            for item in data["objects"]:
                if isinstance(item, dict):
                    cad = item.get("cad_number") or fallback_cad
                    yield cad, item
            return
        cad = data.get("cad_number") or fallback_cad
        yield cad, data
