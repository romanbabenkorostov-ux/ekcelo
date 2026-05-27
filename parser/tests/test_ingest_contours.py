"""Unit-tests для `01b_ingest_contours.py` (Step 1 pipeline-contours).

Главные инварианты:
  - Priority-based upgrade: wfs замещает screenshot_cv, но НЕ наоборот.
  - При равных priority берётся свежая версия алгоритма.
  - Реальный v8-output (session_export, snapshot, per-object) распарсивается.
  - Idempotency: повторный запуск ничего не меняет.
"""
import importlib.util
import json
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "01b_ingest_contours.py"
spec = importlib.util.spec_from_file_location("ingest_contours", SCRIPT_PATH)
ingest = importlib.util.module_from_spec(spec)
sys.modules["ingest_contours"] = ingest
spec.loader.exec_module(ingest)


# ─── Хелперы ────────────────────────────────────────────────────────────


def _contour(source, polygons_count=1, alg="v8.5"):
    """Минимальный валидный контур-payload."""
    return {
        "источник": source,
        "тип": "Polygon",
        "полигонов": polygons_count,
        "колец_всего": 1,
        "площадь_заявленная_кв_м": 100.0,
        "площадь_вычисленная_кв_м": 100.0,
        "коэф_коррекции_масштаба": 1.0,
        "центроид": {"lon": 33.0, "lat": 44.0},
        "geojson": {"type": "Polygon",
                    "coordinates": [[[33.0, 44.0], [33.001, 44.0], [33.001, 44.001], [33.0, 44.0]]]},
        "полигоны": [{"outer": [{"dx": 0, "dy": 0}], "holes": []}],
        "локальные_метры": [[{"dx": 0, "dy": 0}]],
        "scale_bar_px": None,
        "scale_bar_m": None,
        "м_на_пиксель": None,
        "алгоритм_версия": alg,
    }


def _session_export(category, cn, contour):
    return {
        "data": {category: {cn: {"Кадастровый номер": cn, "Контур": contour}}},
        "metadata": {"exported_at": "now", "version": "v8.5", "processed_count": 1},
    }


def _snapshot(category, cn, contour):
    return {category: {cn: {"Кадастровый номер": cn, "Контур": contour}}}


def _setup_project(tmp_path):
    project = tmp_path / "project"
    (project / "_data").mkdir(parents=True)
    return project


# ─── Хелперы скрипта ────────────────────────────────────────────────────


def test_normalize_cn_canonical_form():
    assert ingest._normalize_cn("23:50:0301004:25") == "23:50:0301004:25"
    assert ingest._normalize_cn("23:50:0301004:25/9") == "23:50:0301004:25/9"


def test_normalize_cn_mask_to_colons():
    assert ingest._normalize_cn("23_50_0301004_25") == "23:50:0301004:25"
    assert ingest._normalize_cn("23_50_0301004_25-9") == "23:50:0301004:25/9"


def test_normalize_cn_rejects_garbage():
    assert ingest._normalize_cn("") is None
    assert ingest._normalize_cn(None) is None
    assert ingest._normalize_cn("not_a_cn") is None
    assert ingest._normalize_cn("12:34") is None


def test_source_priority_order():
    assert ingest._source_priority({"источник": "wfs"}) > ingest._source_priority({"источник": "pkk"})
    assert ingest._source_priority({"источник": "pkk"}) > ingest._source_priority({"источник": "screenshot_cv"})
    assert ingest._source_priority({"источник": "manual"}) > ingest._source_priority({"источник": "wfs"})
    assert ingest._source_priority({"источник": "unknown_src"}) == 0


def test_alg_version_key():
    assert ingest._alg_version_key({"алгоритм_версия": "v8.5"}) == (8, 5)
    assert ingest._alg_version_key({"алгоритм_версия": "v10.2"}) == (10, 2)
    assert ingest._alg_version_key({}) == (0, 0)


# ─── Upgrade-логика ─────────────────────────────────────────────────────


def test_should_upgrade_new_record():
    do, reason = ingest._should_upgrade(None, _contour("wfs"))
    assert do is True
    assert reason == "new"


def test_should_upgrade_wfs_overrides_cv():
    existing = _contour("screenshot_cv")
    new = _contour("wfs")
    do, _ = ingest._should_upgrade(existing, new)
    assert do is True


def test_should_NOT_downgrade_wfs_to_cv():
    existing = _contour("wfs")
    new = _contour("screenshot_cv")
    do, _ = ingest._should_upgrade(existing, new)
    assert do is False


def test_should_upgrade_on_alg_version_at_same_priority():
    existing = _contour("wfs", alg="v8.4")
    new = _contour("wfs", alg="v8.5")
    do, _ = ingest._should_upgrade(existing, new)
    assert do is True


def test_should_NOT_upgrade_at_tied_priority_and_alg():
    existing = _contour("wfs", alg="v8.5")
    new = _contour("wfs", alg="v8.5")
    do, _ = ingest._should_upgrade(existing, new)
    assert do is False


# ─── Парсинг v8-output форматов ──────────────────────────────────────────


def test_iter_contour_records_session_export():
    data = _session_export("Земельные участки", "23:50:0301004:25", _contour("wfs"))
    recs = list(ingest._iter_contour_records(data))
    assert len(recs) == 1
    cn, payload, label = recs[0]
    assert cn == "23:50:0301004:25"
    assert payload["источник"] == "wfs"
    assert label.startswith("session_export:")


def test_iter_contour_records_snapshot():
    data = _snapshot("Здания", "23:50:0301004:112", _contour("screenshot_cv"))
    recs = list(ingest._iter_contour_records(data))
    assert len(recs) == 1
    cn, payload, label = recs[0]
    assert cn == "23:50:0301004:112"
    assert label.startswith("snapshot:")


def test_iter_contour_records_per_object_format():
    """Per-object файл от v8: {<cn>: info} — top-level ключ это сам КН.
    Регрессионный тест: до Fix 2 _iter_contour пропускал такие файлы вчистую."""
    data = {"23:50:0301004:25": {"Кадастровый номер": "23:50:0301004:25",
                                  "Контур": _contour("wfs")}}
    recs = list(ingest._iter_contour_records(data))
    assert len(recs) == 1
    cn, payload, label = recs[0]
    assert cn == "23:50:0301004:25"
    assert payload["источник"] == "wfs"
    assert label == "per_object"


def test_iter_contour_skips_without_contour_key():
    data = {"data": {"Здания": {"23:50:0301004:25": {"Кадастровый номер": "23:50:0301004:25"}}},
            "metadata": {}}
    assert list(ingest._iter_contour_records(data)) == []


def test_iter_contour_handles_empty_data():
    assert list(ingest._iter_contour_records({})) == []
    assert list(ingest._iter_contour_records({"data": {}, "metadata": {}})) == []


# ─── End-to-end через CLI ───────────────────────────────────────────────


def test_e2e_single_session_export(tmp_path, monkeypatch, capsys):
    project = _setup_project(tmp_path)
    (project / "session_export_20260525.json").write_text(
        json.dumps(_session_export("Земельные участки", "23:50:0301004:25", _contour("wfs"))),
        encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["01b_ingest_contours.py", "--project", str(project)])
    rc = ingest.main()
    assert rc == 0

    sidecar = project / "_data" / "contours.json"
    assert sidecar.exists()
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    assert data["schema_version"] == "1.0"
    assert "23:50:0301004:25" in data["objects"]
    o = data["objects"]["23:50:0301004:25"]
    assert o["источник"] == "wfs"
    assert "_ingested_at" in o
    assert "_source_file" in o


def test_e2e_idempotent_no_change_on_rerun(tmp_path, monkeypatch):
    project = _setup_project(tmp_path)
    (project / "session_export_20260525.json").write_text(
        json.dumps(_session_export("Земельные участки", "23:50:0301004:25", _contour("wfs"))),
        encoding="utf-8")

    monkeypatch.setattr(sys, "argv", ["01b", "--project", str(project)])
    ingest.main()
    sidecar = project / "_data" / "contours.json"
    data1 = json.loads(sidecar.read_text(encoding="utf-8"))
    t1 = data1["objects"]["23:50:0301004:25"]["_ingested_at"]

    # Повторный запуск — то же содержимое, _ingested_at объекта НЕ меняется (не upgrade)
    ingest.main()
    data2 = json.loads(sidecar.read_text(encoding="utf-8"))
    t2 = data2["objects"]["23:50:0301004:25"]["_ingested_at"]
    assert t1 == t2, "идемпотентный повторный запуск не должен менять _ingested_at объекта"


def test_e2e_upgrade_cv_to_wfs(tmp_path, monkeypatch):
    project = _setup_project(tmp_path)
    # Первый прогон — только CV-результат (например, NSPD-503)
    (project / "session_export_old.json").write_text(
        json.dumps(_session_export("Земельные участки", "23:50:0301004:25",
                                    _contour("screenshot_cv"))),
        encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["01b", "--project", str(project)])
    ingest.main()
    sidecar = project / "_data" / "contours.json"
    assert json.loads(sidecar.read_text(encoding="utf-8")) \
        ["objects"]["23:50:0301004:25"]["источник"] == "screenshot_cv"

    # Второй прогон — теперь WFS получилось получить
    (project / "session_export_new.json").write_text(
        json.dumps(_session_export("Земельные участки", "23:50:0301004:25",
                                    _contour("wfs"))),
        encoding="utf-8")
    ingest.main()
    assert json.loads(sidecar.read_text(encoding="utf-8")) \
        ["objects"]["23:50:0301004:25"]["источник"] == "wfs"


def test_e2e_does_NOT_downgrade_wfs_to_cv(tmp_path, monkeypatch):
    project = _setup_project(tmp_path)
    # Сначала хороший WFS
    (project / "session_export_good.json").write_text(
        json.dumps(_session_export("Земельные участки", "23:50:0301004:25", _contour("wfs"))),
        encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["01b", "--project", str(project)])
    ingest.main()
    sidecar = project / "_data" / "contours.json"

    # Потом — повторный запуск, теперь только CV. WFS должен остаться.
    (project / "session_export_bad.json").write_text(
        json.dumps(_session_export("Земельные участки", "23:50:0301004:25",
                                    _contour("screenshot_cv"))),
        encoding="utf-8")
    ingest.main()
    assert json.loads(sidecar.read_text(encoding="utf-8")) \
        ["objects"]["23:50:0301004:25"]["источник"] == "wfs"


def test_e2e_reset_flag(tmp_path, monkeypatch):
    project = _setup_project(tmp_path)
    (project / "session_export_20260525.json").write_text(
        json.dumps(_session_export("Земельные участки", "23:50:0301004:25", _contour("wfs"))),
        encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["01b", "--project", str(project)])
    ingest.main()
    sidecar = project / "_data" / "contours.json"
    assert "23:50:0301004:25" in json.loads(sidecar.read_text(encoding="utf-8"))["objects"]

    # Удаляем session_export, запускаем с --reset → contours.json пустой
    (project / "session_export_20260525.json").unlink()
    monkeypatch.setattr(sys, "argv", ["01b", "--project", str(project), "--reset"])
    ingest.main()
    assert json.loads(sidecar.read_text(encoding="utf-8"))["objects"] == {}


def test_e2e_creates_empty_skeleton_when_no_sources(tmp_path, monkeypatch):
    project = _setup_project(tmp_path)
    monkeypatch.setattr(sys, "argv", ["01b", "--project", str(project)])
    rc = ingest.main()
    assert rc == 0
    sidecar = project / "_data" / "contours.json"
    assert sidecar.exists()
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    assert data["objects"] == {}
    assert data["schema_version"] == "1.0"


def test_e2e_missing_data_dir_exits_nonzero(tmp_path, monkeypatch):
    """Если `_data/` нет — нужно сначала init_project. ingest падает с RC=1."""
    project = tmp_path / "empty"
    project.mkdir()
    monkeypatch.setattr(sys, "argv", ["01b", "--project", str(project)])
    with pytest.raises(SystemExit) as exc:
        ingest.main()
    assert exc.value.code == 1


def test_e2e_dry_run_does_not_write(tmp_path, monkeypatch):
    project = _setup_project(tmp_path)
    (project / "session_export_20260525.json").write_text(
        json.dumps(_session_export("Земельные участки", "23:50:0301004:25", _contour("wfs"))),
        encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["01b", "--project", str(project), "--dry-run"])
    ingest.main()
    sidecar = project / "_data" / "contours.json"
    assert not sidecar.exists(), "--dry-run не должен создавать sidecar"


def test_e2e_per_object_file_ingests(tmp_path, monkeypatch):
    """Per-object файл от v8 (top-level cn → info) теперь полностью ингестится."""
    project = _setup_project(tmp_path)
    cn = "23:50:0301004:25"
    (project / "23_50_0301004_25.json").write_text(
        json.dumps({cn: {"Кадастровый номер": cn, "Контур": _contour("wfs")}}),
        encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["01b", "--project", str(project)])
    ingest.main()
    data = json.loads((project / "_data" / "contours.json").read_text(encoding="utf-8"))
    assert cn in data["objects"]
    assert data["objects"][cn]["источник"] == "wfs"
    assert data["objects"][cn]["_source_label"] == "per_object"


def test_e2e_schema_version_migrates(tmp_path, monkeypatch):
    """Старый schema_version поднимается до актуального при ingest."""
    project = _setup_project(tmp_path)
    (project / "_data" / "contours.json").write_text(
        json.dumps({"schema_version": "0.9", "ingested_at": "2020-01-01T00:00:00Z",
                    "objects": {}}),
        encoding="utf-8")
    cn = "23:50:0301004:25"
    (project / "session_export_20260525.json").write_text(
        json.dumps(_session_export("Земельные участки", cn, _contour("wfs"))),
        encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["01b", "--project", str(project)])
    ingest.main()
    data = json.loads((project / "_data" / "contours.json").read_text(encoding="utf-8"))
    assert data["schema_version"] == ingest.SCHEMA_VERSION


def test_e2e_byte_level_idempotent(tmp_path, monkeypatch):
    """Повторный запуск без изменений источников не меняет байты contours.json."""
    project = _setup_project(tmp_path)
    (project / "session_export_20260525.json").write_text(
        json.dumps(_session_export("Земельные участки", "23:50:0301004:25", _contour("wfs"))),
        encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["01b", "--project", str(project)])
    ingest.main()
    sidecar = project / "_data" / "contours.json"
    bytes1 = sidecar.read_bytes()
    ingest.main()
    bytes2 = sidecar.read_bytes()
    assert bytes1 == bytes2, "no-op ingest не должен менять байты sidecar"


def test_find_source_files_per_object_filter_rejects_garbage(tmp_path):
    """`__per_object__` строго фильтрует через PER_OBJECT_NAME_RE.
    Регрессия: до Fix 3 любой `foo_bar_baz_qux.json` подхватывался."""
    project = _setup_project(tmp_path)
    (project / "23_50_0301004_25.json").write_text("{}", encoding="utf-8")
    (project / "foo_bar_baz_qux.json").write_text("{}", encoding="utf-8")
    (project / "documents.json").write_text("{}", encoding="utf-8")
    files = ingest.find_source_files(project, ["__per_object__"])
    names = {f.name for f in files}
    assert "23_50_0301004_25.json" in names
    assert "foo_bar_baz_qux.json" not in names
    assert "documents.json" not in names


def test_strip_payload_removes_internal_fields():
    """Защита от случайного попадания debug-полей в sidecar."""
    payload = _contour("wfs")
    payload["превью_png_b64"] = "garbage" * 1000  # такого уже нет в v8.5, но защищаем
    payload["random_internal"] = "x"
    stripped = ingest._strip_payload(payload)
    assert "превью_png_b64" not in stripped
    assert "random_internal" not in stripped
    assert stripped["источник"] == "wfs"
    assert "geojson" in stripped


# ─── Sanity-check площади (defense-in-depth) ────────────────────────────


def test_payload_area_sane_accepts_normal():
    ok, _ = ingest._payload_area_sane(_contour("wfs"))
    assert ok is True


def test_payload_area_sane_rejects_giant_area():
    """computed > 1e10 м² (типично: extent квартала вместо контура)."""
    bad = _contour("network_capture")
    bad["площадь_вычисленная_кв_м"] = 1.4e15
    ok, why = ingest._payload_area_sane(bad)
    assert ok is False
    assert "1e+10" in why or "10" in why


def test_payload_area_sane_rejects_ratio_too_high():
    """parsed=100, computed=20000 → ratio=200 → reject."""
    bad = _contour("network_capture")
    bad["площадь_заявленная_кв_м"] = 100.0
    bad["площадь_вычисленная_кв_м"] = 20_000.0
    ok, _ = ingest._payload_area_sane(bad)
    assert ok is False


def test_payload_area_sane_rejects_ratio_too_low():
    """parsed=100, computed=0.5 → ratio=0.005 → reject."""
    bad = _contour("wfs")
    bad["площадь_заявленная_кв_м"] = 100.0
    bad["площадь_вычисленная_кв_м"] = 0.5
    ok, _ = ingest._payload_area_sane(bad)
    assert ok is False


def test_payload_area_sane_no_parsed_only_giant_check():
    """Если parsed=None — работает только верхний потолок 1e10."""
    p = _contour("wfs")
    p["площадь_заявленная_кв_м"] = None
    p["площадь_вычисленная_кв_м"] = 5e9
    ok, _ = ingest._payload_area_sane(p)
    assert ok is True  # ниже потолка


def test_e2e_insane_network_capture_skipped(tmp_path, monkeypatch, capsys):
    """Network_capture с extent квартала (computed=1.4e15) пропускается, sidecar пуст."""
    project = _setup_project(tmp_path)
    bad = _contour("network_capture")
    bad["площадь_вычисленная_кв_м"] = 1.4e15
    (project / "session_export_garbage.json").write_text(
        json.dumps(_session_export("Земельные участки", "23:50:0301004:25", bad)),
        encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["01b", "--project", str(project)])
    ingest.main()
    sidecar = project / "_data" / "contours.json"
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    assert "23:50:0301004:25" not in data["objects"], "мусорный network_capture должен быть отвергнут"
    out = capsys.readouterr().out
    assert "insane area" in out


def test_e2e_insane_does_not_overwrite_good(tmp_path, monkeypatch):
    """Хороший WFS в sidecar НЕ затирается последующим insane network_capture."""
    project = _setup_project(tmp_path)
    (project / "session_export_good.json").write_text(
        json.dumps(_session_export("Земельные участки", "23:50:0301004:25", _contour("wfs"))),
        encoding="utf-8")
    monkeypatch.setattr(sys, "argv", ["01b", "--project", str(project)])
    ingest.main()
    sidecar = project / "_data" / "contours.json"
    good = json.loads(sidecar.read_text(encoding="utf-8"))["objects"]["23:50:0301004:25"]
    assert good["источник"] == "wfs"

    bad = _contour("network_capture")  # priority 600 < wfs 800 в любом случае
    bad["площадь_вычисленная_кв_м"] = 1.4e15
    (project / "session_export_bad.json").write_text(
        json.dumps(_session_export("Земельные участки", "23:50:0301004:25", bad)),
        encoding="utf-8")
    ingest.main()
    after = json.loads(sidecar.read_text(encoding="utf-8"))["objects"]["23:50:0301004:25"]
    assert after["источник"] == "wfs"
    assert after["площадь_вычисленная_кв_м"] == 100.0
