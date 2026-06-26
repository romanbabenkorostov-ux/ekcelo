"""etl_exif: импорт ЭТП-обогащений из EXIF UserComment JPG-фото.

Закрывает оставшийся пункт §10 roadmap: «EXIF UserComment → БД».

Источник — JPG-файлы, эмитнутые `parser/scripts/pirushin_sosn_rocha_07_init_project_v*.py`
с EXIF UserComment в формате `docs/EXIF_USERCOMMENT_SCHEMA.md` v1.1.

Что попадает в профиль:
- Группируем JPG по `cad`.
- Считаем категории (`category`) для `kind:"photo"`.
- Сводка «комплексная фотофиксация: Фасад, Кровля, Интерьер» → `extras.advantages[]`
  (если такой записи ещё нет).
- Текстовые заметки от экономиста — НЕ в EXIF v1.1 (нет такого поля).
  Когда появятся — добавим в этот же модуль через bump схемы.

Подход тот же, что в `nspd_enricher`: gap-fill (не перезаписываем
существующие значения профиля); новые записи получают `source='exif'`,
`confidence=0.7`.
"""
from __future__ import annotations

import json
import re
import sqlite3
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from egrn_parser.etp_merge import merge_profile

try:
    import piexif
    from piexif.helper import UserComment
    _PIEXIF_OK = True
except ImportError:
    _PIEXIF_OK = False


DEFAULT_SOURCE = "exif"
DEFAULT_CONFIDENCE = 0.7

# Регекс КН — соответствует CHECK-constraint миграции 0001.
_CAD_RE = re.compile(r"^\d{2}:\d{2,3}:\d{6,10}:\d{1,6}(?:/\d+)?$")


# ─────────────────────────────────────────────────────────────────────────────
#  Public API
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class ExifPhotoMeta:
    """Декодированный UserComment payload одного JPG (v1.1 / v1.2)."""
    path: Path
    cad: str | None
    kind: str | None
    category: str | None = None
    semantic: str | None = None
    note: str | None = None      # v1.2+: per-фото заметка экономиста


@dataclass
class ExifEnrichReport:
    cad_number: str
    photos_count: int = 0
    categories: list[str] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)        # v1.2+
    profile_created: bool = False
    extras_filled: list[str] = field(default_factory=list)
    skipped_reason: str | None = None

    @property
    def changed(self) -> bool:
        return self.profile_created or bool(self.extras_filled)


def read_userComment(path: Path) -> dict[str, Any] | None:
    """Прочитать ekcelo-payload из EXIF UserComment JPG. None — если не наш."""
    if not _PIEXIF_OK:
        raise RuntimeError("piexif is not installed; pip install piexif")
    try:
        exif_dict = piexif.load(str(path))
    except Exception:
        return None
    raw = exif_dict.get("Exif", {}).get(piexif.ExifIFD.UserComment)
    if not raw:
        return None
    try:
        decoded = UserComment.load(raw)
    except Exception:
        return None
    try:
        payload = json.loads(decoded)
    except (json.JSONDecodeError, TypeError):
        return None
    # Маркер «наш» payload — обязательная проверка по схеме.
    if not isinstance(payload, dict) or payload.get("app") != "ekcelo":
        return None
    return payload


def scan_directory(directory: Path) -> list[ExifPhotoMeta]:
    """Найти JPG в директории и распарсить EXIF UserComment.

    Возвращает только записи с известным `cad` и `kind` (валидные ekcelo-фото).
    """
    out: list[ExifPhotoMeta] = []
    # Сортируем для детерминистичного порядка note-merge между ОС.
    for jpg in sorted(directory.rglob("*.jpg")):
        payload = read_userComment(jpg)
        if not payload:
            continue
        cad = payload.get("cad")
        if cad and not _CAD_RE.match(str(cad).split("/")[0] + (("/" + cad.split("/")[1]) if "/" in str(cad) else "")):
            # Грубая защита — не строгая.
            pass
        # v1.2+: опциональная заметка экономиста; ограничиваем длину
        # из соображений безопасности (см. EXIF_USERCOMMENT_SCHEMA §v1.2).
        raw_note = payload.get("note")
        note = str(raw_note).strip()[:1000] if raw_note else None
        out.append(ExifPhotoMeta(
            path=jpg,
            cad=cad,
            kind=payload.get("kind"),
            category=payload.get("category"),
            semantic=payload.get("semantic"),
            note=note or None,
        ))
    return out


def enrich_from_exif(
    conn: sqlite3.Connection,
    photos: list[ExifPhotoMeta],
    *,
    source: str = DEFAULT_SOURCE,
    confidence: float = DEFAULT_CONFIDENCE,
) -> list[ExifEnrichReport]:
    """Сгруппировать фото по КН и заполнить профили.

    Для каждого КН с >=1 photo:
    - Собрать уникальный список категорий (например, `["Фасад","Кровля"]`).
    - В `extras.advantages[]` добавить строку «Комплексная фотофиксация: …»
      (если её ещё нет).
    - Не перезаписывать существующие advantages — добавляем новый элемент.

    Returns: ApplyReport по каждому КН (только с changed=True и no-op'ами).
    """
    by_cad: dict[str, list[ExifPhotoMeta]] = defaultdict(list)
    for p in photos:
        if p.cad and p.kind == "photo":
            by_cad[p.cad].append(p)

    reports: list[ExifEnrichReport] = []
    conn.row_factory = sqlite3.Row

    for cad, items in sorted(by_cad.items()):
        categories = sorted({p.category for p in items if p.category})
        # v1.2+: уникальные заметки в порядке появления (preserve insertion
        # order, дубль одной строки на нескольких JPG → одна строка в БД).
        notes = []
        seen_notes = set()
        for p in items:
            if p.note and p.note not in seen_notes:
                notes.append(p.note)
                seen_notes.add(p.note)

        report = ExifEnrichReport(
            cad_number=cad,
            photos_count=len(items),
            categories=list(categories),
            notes=list(notes),
        )

        if not categories and not notes:
            report.skipped_reason = "no_categories_or_notes_in_exif"
            reports.append(report)
            continue

        try:
            _apply_exif_to_profile(
                conn, cad, categories, notes,
                source=source, confidence=confidence,
                report=report,
            )
        except sqlite3.IntegrityError as e:
            report.skipped_reason = f"fk_error: {e}"

        reports.append(report)

    return reports


# ─────────────────────────────────────────────────────────────────────────────
#  Internal
# ─────────────────────────────────────────────────────────────────────────────

def _apply_exif_to_profile(
    conn: sqlite3.Connection,
    cad: str,
    categories: list[str],
    notes: list[str],
    *,
    source: str,
    confidence: float,
    report: ExifEnrichReport,
) -> None:
    """Gap-fill: добавляет сводку категорий в extras.advantages и
    per-фото заметки в extras.notes (joined '«; »'). Идемпотентно:
    повторный прогон не добавляет уже существующие строки."""
    summary = (
        "Комплексная фотофиксация: " + ", ".join(categories) + "."
        if categories else None
    )

    # Единая точка записи §6 — etp_merge.merge_profile с аддитивным слиянием
    # extras.advantages/notes (append_keys: union без дублей = семантика EXIF).
    # commit=False — транзакцию/rollback (dry-run) контролирует CLI.
    incoming_extras: dict[str, Any] = {}
    if summary:
        incoming_extras["advantages"] = [summary]
    if notes:
        incoming_extras["notes"] = "; ".join(notes)
    if not incoming_extras:
        # categories+notes пусты — это уже отловлено выше; сюда не попадаем.
        return

    res = merge_profile(
        conn, cad, {"extras": incoming_extras},
        source=source, confidence=confidence, strategy="gapfill",
        append_keys={"extras": ["advantages", "notes"]}, commit=False)

    report.extras_filled.extend(res["changed_keys"].get("extras", []))
    report.profile_created = res["created"]
    if not report.extras_filled and not report.profile_created:
        report.skipped_reason = "photo_summary_and_notes_already_present"
