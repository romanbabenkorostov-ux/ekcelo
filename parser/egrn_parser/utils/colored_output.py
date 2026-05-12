"""
egrn_parser/utils/colored_output.py — цветной вывод в консоль.
Windows 10 совместимо. Перенесено из pirushin_sosn_rocha_*.
"""

from __future__ import annotations

import sys


class Colors:
    GREEN   = "\033[92m"
    RED     = "\033[91m"
    YELLOW  = "\033[93m"
    CYAN    = "\033[96m"
    MAGENTA = "\033[95m"
    BOLD    = "\033[1m"
    RESET   = "\033[0m"

    OK      = GREEN
    WARN    = YELLOW
    ERR     = RED
    INFO    = CYAN


def cp(text: str = "", color: str = Colors.RESET, file=None) -> None:
    """Вывести цветной текст. file=sys.stderr для ошибок."""
    out = file or sys.stdout
    print(f"{color}{text}{Colors.RESET}", file=out)


def print_ok(text: str)   -> None: cp(f"✓ {text}", Colors.GREEN)
def print_warn(text: str) -> None: cp(f"⚠ {text}", Colors.YELLOW)
def print_err(text: str)  -> None: cp(f"✗ {text}", Colors.RED, file=sys.stderr)
def print_info(text: str) -> None: cp(f"  {text}", Colors.CYAN)
def print_head(text: str) -> None: cp(f"\n{'═'*70}\n  {text}\n{'═'*70}", Colors.BOLD)
def print_sep(text: str = "") -> None:
    if text:
        cp(f"{'─'*70}\n{text}", Colors.BOLD)
    else:
        cp("─" * 70, Colors.BOLD)
