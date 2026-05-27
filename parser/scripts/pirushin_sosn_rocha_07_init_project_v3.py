#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""pirushin_sosn_rocha_07_init_project_v3.py

Узкоспециализированный инициализатор папки `Surveycontract/` в проекте
Ekcelo — для договорного направления (сюрвей/оценка).

В отличие от v2 (GOLDEN_PATH-болванка проекта объекта), v3 НЕ трогает
основную структуру проекта и НЕ дублирует логику классификации
PDF/DOC/EXIF. Скрипт идемпотентен: повторный запуск на готовой папке —
no-op; на полу-готовой — достраивает только недостающее.

Создаёт:

    <project>/Surveycontract/
        README.md
        sborki/          — JSON-конфигурации сборок (output assembler-а: 13_)
        tz1-content/     — output 10 (ТЗ-1)
        body/            — output 11 (тело договора)
        tz2-calculation/ — output 12 (Приложение №2)
        rekvizity/       — снапшоты реквизитов сторон
        upd/             — УПД-XML + результаты валидации
        gotovo/          — финальные сборки

Перед созданием каждой подпапки v3 проверяет, нет ли рядом папки
с «похожим» именем (например «sborka», «sборки», «сборки», «Sборки»).
Если найдена кандидат с similarity ≥ 0.7 — пользователь решает что
делать через интерактивный prompt.

Использование:
    python pirushin_sosn_rocha_07_init_project_v3.py [--project <path>]

Без `--project` спрашивает путь интерактивно.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from parser.utils.folder_match import best_match


# ─── Эталон Surveycontract/ ────────────────────────────────────────────────

SURVEYCONTRACT = "Surveycontract"

SUBDIRS: dict[str, str] = {
    "sborki": (
        "Конфигурации сборок договоров (output скрипта 13_assemble_contract). "
        "Каждый файл — JSON со списком выбранных компонентов из tz1-content/, "
        "body/, tz2-calculation/ и (опц.) upd/."
    ),
    "tz1-content": (
        "Output скрипта 10_make_tz1 — Техническое задание №1 (Приложение №1). "
        "Файлы: TZ1<datetime>.md / .docx."
    ),
    "body": (
        "Output скрипта 11_make_contract_body — тело договора. "
        "Файлы: Contract_<номер>_<datetime>.md / .docx."
    ),
    "tz2-calculation": (
        "Output скрипта 12_make_contract_appendix2 — Приложение №2 "
        "(календарный план, перечень источников, чеклист услуг = калькуляция). "
        "Файлы: Appendix2_<номер>_<datetime>.md / .docx."
    ),
    "rekvizity": (
        "Локальные снапшоты реквизитов сторон договора (output parser.rekvizity.cli). "
        "Каждый snapshot фиксирует версию реквизитов на момент подписания. "
        "Источники: .doc/.pdf-выписки ЕГРЮЛ/ЕГРИП/банков (например ВТБ)."
    ),
    "upd": (
        "Универсальные передаточные документы (УПД-XML) + результаты валидации "
        "по XSD ФНС (parser/schema/xsd/upd/)."
    ),
    "gotovo": (
        "Финальные сборки договоров: <номер>_<дата>_v<N>_<datetime>.{docx,md,json} "
        "(output 13_assemble_contract). Версии (допсоглашения) хранятся плоско."
    ),
}

ROOT_README = """# Surveycontract/

Папка договорного направления Ekcelo (сюрвей/оценка). Создаётся
скриптом `pirushin_sosn_rocha_07_init_project_v3.py`.

## Поток данных

```
   10 (tz1-content/)
   11 (body/)              ─┐
   12 (tz2-calculation/)    ├─→ 13 (sborki/, gotovo/)
   rekvizity/              ─┘     │
                                  └─→ upd/ (опц.)
```

## Подпапки

{children}

См. также:
  • `parser/scripts/pirushin_sosn_rocha_13_assemble_contract_v1.py` — assembler
  • `parser/rekvizity/` — парсер реквизитов
  • `parser/upd/` — валидатор УПД
  • `parser/schema/xsd/upd/` — XSD ФНС
"""


# ─── ANSI ─────────────────────────────────────────────────────────────────


class C:
    R = "\033[31m"
    G = "\033[32m"
    Y = "\033[33m"
    B = "\033[36m"
    O = "\033[0m"  # noqa: E741


def cp(msg: str, col: str = "") -> None:
    print(f"{col}{msg}{C.O}" if col else msg)


# ─── Логика ────────────────────────────────────────────────────────────────


def _readme_for(child: str, descr: str) -> str:
    return (
        f"# Surveycontract/{child}/\n\n"
        f"{descr}\n\n"
        f"Создано: pirushin_sosn_rocha_07_init_project_v3.py.\n"
    )


def _resolve_existing_or_new(
    parent: Path, canonical: str, *, assume_yes: bool = False
) -> Path:
    """Если в `parent` уже есть папка с именем `canonical` — возвращает её.
    Если есть «похожая» (similarity ≥ 0.7) — спрашивает пользователя
    [1] пропустить / [2] создать рядом / [3] переименовать.
    Если ничего похожего — возвращает `parent / canonical` (для создания).
    """
    target = parent / canonical
    if target.exists():
        return target

    siblings = [p.name for p in parent.iterdir() if p.is_dir()]
    match = best_match(canonical, siblings, threshold=0.7)
    if match is None:
        return target

    existing_name, score = match
    cp(
        f"\n  ⚠ В {parent} найдена похожая папка:",
        C.Y,
    )
    cp(f"      существующая: «{existing_name}»  (score {score:.2f})", C.Y)
    cp(f"      эталон:       «{canonical}»", C.Y)
    if assume_yes:
        # Non-interactive default — пропускаем (consrvative).
        cp("    [auto: пропустить — сохранить существующую]", C.B)
        return parent / existing_name

    while True:
        cp("    [1] — пропустить (использовать существующую как есть)", C.B)
        cp("    [2] — создать эталонную рядом (будет 2 папки)", C.B)
        cp("    [3] — переименовать существующую в эталон", C.B)
        ans = input("    Выбор: ").strip()
        if ans == "1":
            return parent / existing_name
        if ans == "2":
            return target
        if ans == "3":
            (parent / existing_name).rename(target)
            cp(f"    ✓ Переименовано: {existing_name} → {canonical}", C.G)
            return target
        cp("      ⚠ Ожидается 1/2/3.", C.Y)


def init_surveycontract(
    project: Path, *, assume_yes: bool = False
) -> dict[str, bool]:
    """Создаёт `Surveycontract/` с подпапками. Возвращает per-child
    булевы: True = создано, False = уже было.
    """
    if not project.is_dir():
        raise FileNotFoundError(f"Не папка: {project}")

    sc = _resolve_existing_or_new(project, SURVEYCONTRACT, assume_yes=assume_yes)
    sc.mkdir(parents=True, exist_ok=True)

    created: dict[str, bool] = {}
    for child, descr in SUBDIRS.items():
        sub = _resolve_existing_or_new(sc, child, assume_yes=assume_yes)
        existed = sub.exists()
        sub.mkdir(parents=True, exist_ok=True)
        readme = sub / "README.md"
        if not readme.exists():
            readme.write_text(_readme_for(child, descr), encoding="utf-8")
        created[child] = not existed

    root_readme = sc / "README.md"
    if not root_readme.exists():
        children_md = "\n".join(f"- **{k}/** — {v}" for k, v in SUBDIRS.items())
        root_readme.write_text(
            ROOT_README.format(children=children_md), encoding="utf-8"
        )
    return created


# ─── CLI ──────────────────────────────────────────────────────────────────


def _ask_path(prompt: str) -> Path:
    while True:
        raw = input(f"{prompt}: ").strip().strip('"').strip("'")
        if not raw:
            cp("  ⚠ Путь не может быть пустым.", C.Y)
            continue
        p = Path(raw).expanduser()
        if not p.is_dir():
            cp(f"  ⚠ Не папка: {p}", C.Y)
            continue
        return p


def main() -> int:
    ap = argparse.ArgumentParser(
        description="ekcelo · init Surveycontract/ (договорной direction)",
    )
    ap.add_argument(
        "--project",
        type=Path,
        default=None,
        help="Папка проекта (если не указана — спросит интерактивно)",
    )
    ap.add_argument(
        "--yes",
        action="store_true",
        help="Non-interactive: при fuzzy-match'е выбирать «пропустить» "
        "(использовать существующую).",
    )
    args = ap.parse_args()

    cp("\n══════════════════════════════════════════════", C.B)
    cp("  ekcelo · init Surveycontract/ (v3)", C.B)
    cp("══════════════════════════════════════════════\n", C.B)

    project: Path | None = args.project
    if project is None:
        project = _ask_path("Введите путь к папке проекта")
    if not project.is_dir():
        cp(f"✗ Не папка: {project}", C.R)
        return 1

    # Pre-flight: предупреждаем, если Surveycontract/ уже есть.
    sc = project / SURVEYCONTRACT
    if sc.exists():
        cp(f"⚠ {sc} уже существует.", C.Y)
        if not args.yes:
            cp("  [1] — проверить и достроить недостающее (idempotent walk)", C.B)
            cp("  [Enter] — отмена", C.B)
            ans = input("  Выбор: ").strip()
            if ans != "1":
                cp("✗ Отменено пользователем.", C.Y)
                return 0

    try:
        created = init_surveycontract(project, assume_yes=args.yes)
    except FileNotFoundError as e:
        cp(f"✗ {e}", C.R)
        return 1

    cp("\n✓ Готово:", C.G)
    for child, was_created in created.items():
        mark = "+ создано" if was_created else "= существовало"
        cp(f"    {mark}: Surveycontract/{child}/", C.G if was_created else C.B)
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        cp("\n✗ Прервано пользователем.", C.Y)
        sys.exit(130)
