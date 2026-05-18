"""
egrn_parser/merge/cad_resolver.py — интерактивное сопоставление частичных
кадастровых номеров из ОСВ с объектами в БД.

Пример: ОСВ содержит «:119» (только хвост). Функция находит в БД объекты
с таким хвостом (напр. 90:25:020102:119) и предлагает пользователю выбрать.
"""

from __future__ import annotations

import logging
import re
import sys
from pathlib import Path
from typing import Optional

from egrn_parser.db.connection import get_connection
from egrn_parser.utils.colored_output import cp, print_ok, print_warn, print_info, Colors

log = logging.getLogger(__name__)


def find_cad_candidates(db_path: Path | str, fragment: str) -> list[dict]:
    """
    Найти в БД объекты, кадастровый номер которых заканчивается на фрагмент.

    fragment: строка вида ':119' или просто '119'.
    """
    db_path = Path(db_path)
    tail = fragment.lstrip(":")  # '119'
    # Паттерн: номер заканчивается на :<tail>
    pattern = f"%:{tail}"

    results: list[dict] = []
    try:
        with get_connection(db_path, readonly=True) as conn:
            # Поиск в ЗУ
            land_rows = conn.execute(
                "SELECT cad_number, 'land' AS object_class, address, area "
                "FROM land_objects WHERE cad_number LIKE ?",
                (pattern,),
            ).fetchall()
            for r in land_rows:
                results.append(dict(r))

            # Поиск в ОКС
            bldg_rows = conn.execute(
                "SELECT cad_number, object_type AS object_class, address, area "
                "FROM building_objects WHERE cad_number LIKE ?",
                (pattern,),
            ).fetchall()
            for r in bldg_rows:
                results.append(dict(r))
    except Exception as e:
        log.warning("Ошибка поиска фрагмента %s: %s", fragment, e)

    return results


def resolve_cad_fragments_interactive(
    db_path: Path | str,
    accessories: list[dict],
    policy: str = "ask",
) -> list[dict]:
    """
    Интерактивно сопоставить принадлежности с частичными кадастровыми номерами
    с объектами в БД.

    Модифицирует accessories на месте: проставляет re_cad_number при подтверждении.
    Возвращает список принадлежностей с обновлёнными re_cad_number.
    """
    has_tty = sys.stdin.isatty()
    fragments_needing_resolution = [
        acc for acc in accessories
        if acc.get("cad_number_fragment") and not acc.get("re_cad_number")
    ]

    if not fragments_needing_resolution:
        return accessories

    print_info(f"\nНайдено {len(fragments_needing_resolution)} объектов с частичными кадастровыми номерами.")
    print_info("Ищем совпадения в базе данных...\n")

    # Сгруппировать по фрагменту — чтобы спрашивать один раз на фрагмент
    fragment_decisions: dict[str, Optional[str]] = {}  # fragment → выбранный cad или None

    for acc in fragments_needing_resolution:
        fragment = acc["cad_number_fragment"]

        if fragment in fragment_decisions:
            # Уже решили для этого фрагмента
            chosen = fragment_decisions[fragment]
            if chosen:
                acc["re_cad_number"] = chosen
                acc["cad_number_fragment"] = None
            continue

        candidates = find_cad_candidates(db_path, fragment)

        # Вывод
        cp(f"\n{'─'*65}", Colors.BOLD)
        cp(f"  Частичный кадастровый номер: {fragment}", Colors.CYAN)
        cp(f"  Объект из ОСВ: «{acc.get('item_name', '')[:60]}»", Colors.CYAN)

        if not candidates:
            print_warn(f"  В БД нет объектов с хвостом {fragment}")
            print_info("  → сопоставление пропущено (re_cad_number=NULL)")
            fragment_decisions[fragment] = None
            continue

        # Показать кандидатов
        cp(f"\n  Найдено в БД ({len(candidates)}):", Colors.GREEN)
        for i, c in enumerate(candidates, 1):
            label = c.get("address") or ""
            area  = f", {c['area']} м²" if c.get("area") else ""
            cp(f"    [{i}] {c['cad_number']}  ({c['object_class']}{area}  {label[:40]})", Colors.GREEN)
        cp(f"    [s] пропустить (оставить NULL)", Colors.YELLOW)
        if len(candidates) == 1:
            cp(f"    [Enter] выбрать [{candidates[0]['cad_number']}]", Colors.BOLD)

        # Авто-выбор при policy != ask или нет TTY
        if policy != "ask" or not has_tty:
            if len(candidates) == 1:
                chosen = candidates[0]["cad_number"]
                print_ok(f"  Авто-выбор: {chosen}")
            else:
                chosen = None
                print_warn(f"  Авто-выбор невозможен (несколько кандидатов) — пропуск")
            fragment_decisions[fragment] = chosen
            if chosen:
                acc["re_cad_number"] = chosen
                acc["cad_number_fragment"] = None
            continue

        # Интерактивный выбор
        while True:
            try:
                ans = input("\n  Выбор: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                ans = "s"

            if ans in ("s", "skip", ""):
                if ans == "" and len(candidates) == 1:
                    chosen = candidates[0]["cad_number"]
                    break
                chosen = None
                break

            if ans.isdigit() and 1 <= int(ans) <= len(candidates):
                chosen = candidates[int(ans) - 1]["cad_number"]
                break

            # Ввели кадастровый номер напрямую
            m = re.match(r"\d{2}:\d{2}:\d{6,7}:\d+", ans)
            if m:
                chosen = m.group(0)
                break

            print_warn(f"  Введите номер кандидата (1-{len(candidates)}), 's' или кадастровый номер")

        fragment_decisions[fragment] = chosen
        if chosen:
            acc["re_cad_number"] = chosen
            acc["cad_number_fragment"] = None
            print_ok(f"  Привязано: {fragment} → {chosen}")
        else:
            print_warn(f"  Пропущено: {fragment}")

    # Применить решения ко всем принадлежностям с тем же фрагментом
    for acc in accessories:
        frag = acc.get("cad_number_fragment")
        if frag and frag in fragment_decisions and fragment_decisions[frag]:
            acc["re_cad_number"] = fragment_decisions[frag]
            acc["cad_number_fragment"] = None

    resolved = sum(1 for acc in accessories if acc.get("re_cad_number") and not acc.get("cad_number_fragment"))
    log.info("cad_resolver: сопоставлено %d принадлежностей", resolved)

    return accessories
