# -*- coding: utf-8 -*-
"""Tests for pirushin_sosn_rocha_07_init_project_v3.

Покрывают:
  • Создание полной Surveycontract/-структуры на пустой папке (--yes).
  • Idempotent walk: повторный запуск не создаёт ничего нового.
  • Fuzzy-match с `--yes` → существующая папка сохраняется (skip).
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

SCRIPT = ROOT / "parser" / "scripts" / "pirushin_sosn_rocha_07_init_project_v3.py"


def _load_module():
    spec = importlib.util.spec_from_file_location("init_v3", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


M = _load_module()


def test_creates_full_structure(tmp_path: Path):
    created = M.init_surveycontract(tmp_path, assume_yes=True)
    sc = tmp_path / "Surveycontract"
    assert sc.is_dir()
    assert (sc / "README.md").exists()
    for child in M.SUBDIRS:
        assert (sc / child).is_dir(), f"missing: {child}"
        assert (sc / child / "README.md").exists(), f"missing README: {child}"
        assert created[child] is True


def test_idempotent_walk(tmp_path: Path):
    M.init_surveycontract(tmp_path, assume_yes=True)
    second = M.init_surveycontract(tmp_path, assume_yes=True)
    # При повторе все подпапки уже существуют → created[*] = False.
    assert all(v is False for v in second.values())


def test_fuzzy_match_skips_existing_with_yes(tmp_path: Path):
    # Типичная опечатка / регистр: 'Sborkii' (лишняя 'i' + другой регистр)
    # вместо канонического 'sborki' — similarity ≥ 0.7.
    sc = tmp_path / "Surveycontract"
    sc.mkdir()
    weird = sc / "Sborkii"
    weird.mkdir()

    M.init_surveycontract(tmp_path, assume_yes=True)

    # В --yes режиме fuzzy-match выбирает «пропустить»: эталонная папка
    # `sborki` НЕ создаётся (используется существующая `Sborkii`).
    assert weird.is_dir()
    assert not (sc / "sborki").exists()
