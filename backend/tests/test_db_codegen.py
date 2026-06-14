"""P0.1.3 — codegen Pydantic-моделей из C2-контракта."""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

import pytest

from backend.app.services import db_codegen
from backend.app.services.db_contract import load_contract


_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODELS_PATH = _REPO_ROOT / "backend" / "app" / "services" / "db_models.py"


def test_generate_returns_non_empty_source() -> None:
    src = db_codegen.generate()
    assert "class ObjectsRow" in src
    assert "class EntityRegistryRow" in src
    assert "class ObjectEtpProfileRow" in src
    assert "CONTRACT_SHA256" in src


def test_generated_models_match_committed_file() -> None:
    """CI sync-guard: db_models.py = текущий вывод db_codegen.generate().

    Если кто-то изменил contracts/db/schema.json, но забыл перегенерировать
    db_models.py — этот тест падает с подсказкой:
        python -m backend.app.services.db_codegen -o backend/app/services/db_models.py
    """
    expected = db_codegen.generate()
    actual = _MODELS_PATH.read_text(encoding="utf-8")
    if expected != actual:
        pytest.fail(
            "db_models.py отстаёт от contracts/db/schema.json. "
            "Перегенерируйте: python -m backend.app.services.db_codegen "
            "-o backend/app/services/db_models.py"
        )


def test_generated_models_have_all_contract_tables() -> None:
    src = db_codegen.generate()
    for tname in load_contract()["tables"]:
        cls_name = "".join(p.capitalize() for p in tname.split("_")) + "Row"
        assert f"class {cls_name}" in src, f"нет класса для {tname}"


def test_table_to_model_map_complete() -> None:
    from backend.app.services.db_models import TABLE_TO_MODEL
    contract_tables = set(load_contract()["tables"])
    assert set(TABLE_TO_MODEL) == contract_tables


def test_models_validate_real_row() -> None:
    from backend.app.services.db_models import ObjectsRow
    obj = ObjectsRow.model_validate({
        "cad_number": "61:44:0050706:31",
        "object_type": "room",
        "address": "Ростов",
        "area": 125.4,
        "category": None, "permitted_use": None, "purpose": None,
        "floors": 5, "updated_at": "2026-06-08 10:00:00",
    })
    assert obj.cad_number == "61:44:0050706:31"
    assert obj.area == 125.4
    assert obj.floors == 5


def test_models_reject_missing_required_field() -> None:
    from backend.app.services.db_models import ObjectsRow
    with pytest.raises(Exception):  # ValidationError
        ObjectsRow.model_validate({"cad_number": "x"})  # без object_type (required)


def test_models_allow_extra_fields() -> None:
    """Forward-compat: лишнее в row не ломает (как и в validate_db)."""
    from backend.app.services.db_models import ObjectsRow
    obj = ObjectsRow.model_validate({
        "cad_number": "x", "object_type": "room",
        "future_field": "hello",
    })
    assert obj.cad_number == "x"


def test_cli_stdout_mode(capsys) -> None:
    rc = db_codegen.main(["--stdout"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "class ObjectsRow" in out


def test_cli_writes_file(tmp_path: Path) -> None:
    out = tmp_path / "models.py"
    rc = db_codegen.main(["-o", str(out)])
    assert rc == 0
    assert out.is_file()
    assert "class ObjectsRow" in out.read_text()


def test_contract_sha_in_generated_matches_current() -> None:
    """Sha-марка в db_models.py должна совпадать с текущим sha контракта."""
    from backend.app.services import db_models
    src = db_codegen.generate()
    m = re.search(r"CONTRACT_SHA256 = '([0-9a-f]{64})'", src)
    assert m
    assert db_models.CONTRACT_SHA256 == m.group(1)
