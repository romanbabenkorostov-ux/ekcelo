"""tests/test_smoke_cli.py — end-to-end smoke ЭТП-экспортёра."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from parser.exporters.etp import smoke_cli
from parser.exporters.etp.smoke_cli import main as smoke_main


def test_smoke_happy_path(tmp_path, capsys):
    rc = smoke_main(["--work-dir", str(tmp_path)])
    captured = capsys.readouterr()
    assert rc == 0, f"smoke failed:\nstdout:\n{captured.out}\nstderr:\n{captured.err}"
    # Все [OK] — ни одной [FAIL].
    assert "[FAIL]" not in captured.out
    assert "[FAIL]" not in captured.err


def test_smoke_produces_artifacts(tmp_path):
    smoke_main(["--work-dir", str(tmp_path), "--quiet"])
    lot_dir = tmp_path / "out" / "etp" / "lot_pirushin_001"
    platform_dir = lot_dir / "torgi.gov.ru"
    assert (lot_dir / "lot_appendix.md").read_text(encoding="utf-8").strip()
    assert (platform_dir / "description.short.txt").read_text(encoding="utf-8").strip()
    assert (platform_dir / "description.full.txt").read_text(encoding="utf-8").strip()
    payload = json.loads((platform_dir / "long_description.json").read_text(encoding="utf-8"))
    assert payload  # ctx непустой


def test_smoke_export_json_payload(tmp_path):
    smoke_main(["--work-dir", str(tmp_path), "--quiet"])
    payload_path = tmp_path / "exports" / "etp" / "object_etp_profile.json"
    payload = json.loads(payload_path.read_text(encoding="utf-8"))
    assert payload["$schema_version"] == "1.0"
    assert len(payload["object_etp_profile"]) == 1
    assert len(payload["lots"]) == 1
    assert len(payload["lot_items"]) == 2


def test_smoke_detects_import_failure(tmp_path, monkeypatch, capsys):
    """Подмена импорта — smoke должен поймать и вернуть rc=1 без падения."""
    import importlib
    real_import = importlib.import_module
    target = "parser.exporters.etp.auto_export"

    def fake_import(name, *a, **kw):
        if name == target:
            raise ModuleNotFoundError(f"No module named '{name}'")
        return real_import(name, *a, **kw)

    monkeypatch.setattr(importlib, "import_module", fake_import)
    rc = smoke_main(["--work-dir", str(tmp_path), "--quiet"])
    err = capsys.readouterr().err
    assert rc == 1
    assert target in err
    assert "ModuleNotFoundError" in err


def test_smoke_keep_preserves_workdir(tmp_path):
    """--work-dir подавляет автоудаление; артефакты должны остаться."""
    smoke_main(["--work-dir", str(tmp_path), "--quiet"])
    assert (tmp_path / "smoke.sqlite").exists()
    assert (tmp_path / "out" / "etp" / "lot_pirushin_001").exists()


def test_required_modules_list_matches_package(tmp_path):
    """Список _REQUIRED_MODULES не должен расходиться с фактическим содержимым пакета."""
    pkg_dir = Path(smoke_cli.__file__).parent
    py_files = {f.stem for f in pkg_dir.glob("*.py") if f.stem != "__init__"}
    declared = set()
    for mod in smoke_cli._REQUIRED_MODULES:
        if mod == "parser.exporters.etp":
            continue
        declared.add(mod.rsplit(".", 1)[-1])
    declared.discard("smoke_cli")  # сам себя не проверяем
    py_files.discard("smoke_cli")
    missing = py_files - declared
    assert not missing, f"smoke не покрывает модули: {sorted(missing)}"
