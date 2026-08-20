"""Unit-tests для `kml_extract_cadastre_numbers.py`.

Главные инварианты:
  - output_path_for: '+' вставляется перед расширением, тот же каталог.
  - prompt_kml_path: переспрашивает на пустой ввод и несуществующий путь,
    принимает путь в кавычках (частый случай copy-paste из Windows).
  - main(): пишет уникальные КН по одному на строку в выходной файл,
    печатает их же в консоль.
"""
import importlib.util
import sys
from pathlib import Path

import pytest

SCRIPT_PATH = Path(__file__).resolve().parents[1] / "scripts" / "kml_extract_cadastre_numbers.py"
spec = importlib.util.spec_from_file_location("kml_extract_cadastre_numbers", SCRIPT_PATH)
mod = importlib.util.module_from_spec(spec)
sys.modules["kml_extract_cadastre_numbers"] = mod
spec.loader.exec_module(mod)


KML_TEMPLATE = """<?xml version="1.0" encoding="UTF-8"?>
<kml xmlns="http://www.opengis.net/kml/2.2"><Document>
<Placemark><name>Поле A</name><description>Поле 23:15:0000000:2267 · Шардоне</description>
  <Polygon><outerBoundaryIs><LinearRing>
    <coordinates>0,0,0 1,0,0 1,1,0 0,1,0 0,0,0</coordinates>
  </LinearRing></outerBoundaryIs></Polygon>
</Placemark>
<Placemark><name>Поле B</name><description>Поле 23:15:0303000:1130</description>
  <Polygon><outerBoundaryIs><LinearRing>
    <coordinates>2,0,0 3,0,0 3,1,0 2,1,0 2,0,0</coordinates>
  </LinearRing></outerBoundaryIs></Polygon>
</Placemark>
</Document></kml>
"""


@pytest.fixture
def kml_path(tmp_path: Path) -> Path:
    p = tmp_path / "Олимп.kml"
    p.write_text(KML_TEMPLATE, encoding="utf-8")
    return p


def test_output_path_for_inserts_plus_before_extension():
    p = Path("/x/y/Олимп_20-08-2026.kml")
    assert mod.output_path_for(p) == Path("/x/y/Олимп_20-08-2026+.kml")


def test_prompt_kml_path_accepts_valid_path(kml_path):
    answers = iter([str(kml_path)])
    result = mod.prompt_kml_path(lambda _prompt: next(answers))
    assert result == kml_path


def test_prompt_kml_path_strips_quotes(kml_path):
    answers = iter([f'"{kml_path}"'])
    result = mod.prompt_kml_path(lambda _prompt: next(answers))
    assert result == kml_path


def test_prompt_kml_path_reprompts_on_empty_and_missing(kml_path):
    answers = iter(["", str(kml_path.parent / "нет-такого.kml"), str(kml_path)])
    result = mod.prompt_kml_path(lambda _prompt: next(answers))
    assert result == kml_path


def test_main_writes_output_file_with_plus_suffix(kml_path, capsys):
    rc = mod.main(lambda _prompt: str(kml_path))
    assert rc == 0

    out_path = kml_path.with_name("Олимп+.kml")
    assert out_path.exists()
    assert out_path.read_text(encoding="utf-8").splitlines() == [
        "23:15:0000000:2267",
        "23:15:0303000:1130",
    ]

    console = capsys.readouterr().out
    assert "23:15:0000000:2267" in console
    assert "23:15:0303000:1130" in console
    assert str(out_path) in console
