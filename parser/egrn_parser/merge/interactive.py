"""
egrn_parser/merge/interactive.py — интерактивный diff-диалог (ТЗ раздел 7.6 / 13.3).
"""

from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from egrn_parser.merge.differ import format_diff_report

log = logging.getLogger(__name__)


def ask_diff_action(
    cad_number: str,
    name: str,
    changed: dict,
    decisions_log_path: Optional[Path] = None,
    policy: str = "ask",
) -> str:
    """
    Показать diff и спросить пользователя о действии.

    Возвращает одно из: 'replace', 'enrich', 'new', 'skip'.
    При policy != 'ask' — возвращает policy немедленно без диалога.
    """
    if policy != "ask":
        _log_decision(decisions_log_path, cad_number, changed, policy, auto=True)
        return policy

    # Проверить наличие TTY
    if not sys.stdin.isatty():
        log.warning(
            "Нет TTY для интерактивного diff объекта %s — применяется политика replace", cad_number
        )
        _log_decision(decisions_log_path, cad_number, changed, "replace", auto=True)
        return "replace"

    print(format_diff_report(cad_number, name, changed))
    print("\nДействие?")
    print("  [r] заменить (replace)")
    print("  [e] обогатить (enrich, объединить)")
    print("  [n] создать новый объект (new)")
    print("  [s] оставить как есть (skip)")
    print("  [d] показать полный diff")
    print("  [q] прервать")

    action_map = {
        "r": "replace", "replace": "replace",
        "e": "enrich",  "enrich":  "enrich",
        "n": "new",      "new":    "new",
        "s": "skip",     "skip":   "skip",
        "q": "quit",     "quit":   "quit",
    }

    while True:
        try:
            ans = input("\nВыбор [r/e/n/s/д/q]: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            return "skip"

        if ans in ("d", "д"):
            print(json.dumps(changed, ensure_ascii=False, indent=2, default=str))
            continue

        # Русские псевдонимы
        rus_map = {"з": "replace", "о": "enrich", "н": "new", "с": "skip", "п": "quit"}
        ans = rus_map.get(ans, ans)

        action = action_map.get(ans)
        if action == "quit":
            raise KeyboardInterrupt("Прервано пользователем")
        if action:
            _log_decision(decisions_log_path, cad_number, changed, action, auto=False)
            return action

        print("Введите r/з (заменить), e/о (обогатить), n (новый), s/с (пропуск), д (diff), q (выход)")


def _log_decision(
    log_path: Optional[Path],
    cad_number: str,
    changed: dict,
    action: str,
    auto: bool,
) -> None:
    """Записать решение в interactive_decisions.jsonl."""
    if log_path is None:
        return
    record = {
        "ts":         datetime.now(timezone.utc).isoformat(),
        "cad_number": cad_number,
        "action":     action,
        "auto":       auto,
        "changed_fields": list(changed.keys()),
    }
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except Exception as e:
        log.warning("Не удалось записать решение в лог: %s", e)

def ask_enrich_fields(
    cad_number: str,
    changed: dict,
    decisions_log_path=None,
    policy: str = "ask",
) -> dict:
    """
    Интерактивный диалог обогащения: по каждому изменённому полю задаётся
    отдельный вопрос. Показывает прогресс «X из Y».

    Возвращает dict {field: "accept"|"skip"} — какие поля принять из новой выписки.
    """
    if policy != "ask" or not changed:
        # В авто-режиме: принять всё что лучше (новое не пустое, старое пустое)
        return {field: "accept" if new_val is not None and old_val is None else "skip"
                for field, (old_val, new_val) in changed.items()}

    has_tty = sys.stdin.isatty()
    if not has_tty:
        return {field: "accept" if new_val is not None and old_val is None else "skip"
                for field, (old_val, new_val) in changed.items()}

    decisions = {}
    total = len(changed)
    items = list(changed.items())

    for idx, (field, (old_val, new_val)) in enumerate(items, 1):
        print(f"\n  [{idx}/{total}] Поле: {field}")
        print(f"    В БД:          {str(old_val)[:60] if old_val is not None else '—'}")
        print(f"    В выписке:     {str(new_val)[:60] if new_val is not None else '—'}")

        # Авто-подсказка: если в БД пусто — рекомендуем принять
        if old_val is None and new_val is not None:
            print("    → Рекомендация: принять (в БД пусто)")
        elif old_val is not None and new_val is not None:
            print("    → Значения различаются")
        elif old_val is not None and new_val is None:
            print("    → Рекомендация: пропустить (в выписке отсутствует)")

        while True:
            try:
                ans = input("    Принять из выписки? [Д/н]: ").strip().lower()
            except (EOFError, KeyboardInterrupt):
                ans = "н"

            if ans in ("", "д", "y", "yes", "д"):
                decisions[field] = "accept"
                break
            elif ans in ("н", "n", "no", "нет"):
                decisions[field] = "skip"
                break
            else:
                print("    Введите Д или н")

    if decisions_log_path:
        _log_decision(decisions_log_path, cad_number, changed,
                      f"enrich_fields:{sum(1 for v in decisions.values() if v=='accept')}/{total}", False)
    return decisions

