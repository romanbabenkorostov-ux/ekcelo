#!/usr/bin/env python3
"""Генератор mini-fixture KMZ для ручного тестирования viewer'а (контракт 2.11.0).

Создаёт минимальный валидный проект (1 ЗУ + 1 здание + 1 квартира + 1 БУ + 1 EQ +
1 бенефициар + 3 фото без EXIF) в указанной папке, прогоняет 04→07→08 logically:
эмитит structure.json, NSPD-кеш, graph.html (минимальный, но с meta-тегом и
listener'ом), graph_node_index.json (sidecar), затем собирает KMZ. Используется
viewer-team для smoke-теста PR-C `viewer/graph-preselect-overlay`.

Использование:
    python3 parser/scripts/dev/make_mini_fixture.py <out_dir>

Результат:
    <out_dir>/_data/structure.json
    <out_dir>/_data/nspd_cache/cache.json
    <out_dir>/_data/graph.html              (мини-граф с meta+listener)
    <out_dir>/_data/graph_node_index.json   (sidecar для 08)
    <out_dir>/kmz-kml/project.kmz           (готовый артефакт для viewer'а)

Содержимое KMZ — 5 классов с непустым `<ExtendedData>/graph_node_id`:
    cad_zu_*    → "61:44:0050706:1"
    cad_oks_*   → "61:44:0050706:31"
    cad_room_*  → "61:44:0050706:119"
    cad_bu_*    → "bu::demo000000000001"
    cad_eq_*    → "eq::eq1"
    cad_ben_*   → "legal::inn::6164098765"
    photoPin_*  → "61:44:0050706:31" (родитель)
"""
from __future__ import annotations
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from pirushin_sosn_rocha_08_build_kmz_v2 import build_kmz  # noqa: E402


STRUCTURE = {
    "enterprise": {"name_short": "Демо-проект", "name": "Демо-проект viewer-теста"},
    "cadastre_objects": [
        {"id": "c1", "cadastral_number": "61:44:0050706:1",
         "object_type": "Земельный участок",
         "address": "г. Ростов-на-Дону, ул. Б.Садовая, 111"},
        {"id": "c2", "cadastral_number": "61:44:0050706:31",
         "object_type": "Здание",
         "address": "г. Ростов-на-Дону, ул. Б.Садовая, 111"},
        {"id": "c3", "cadastral_number": "61:44:0050706:119",
         "object_type": "Квартира",
         "address": "г. Ростов-на-Дону, ул. Б.Садовая, 111, кв. 12",
         "parent_cad": "61:44:0050706:31", "_floor_index": 3},
    ],
    "business_units": [
        {"id": "bu1", "name": "Демо-филиал",
         "address": "г. Ростов-на-Дону, ул. Б.Садовая, 111",
         "inns": ["6164012345"],
         "cadastre_ids": ["c1", "c2", "c3"],
         "equipment_ids": ["eq1"],
         "owners": [
             {"inn": "6164098765", "ogrn": "1026103098765",
              "name": "ООО Демо-Бенефициар",
              "address": "г. Ростов-на-Дону, пр. Будённовский, 1",
              "share": "100%"}
         ]}
    ],
    "equipment": [
        {"id": "eq1", "name": "Демо-котёл",
         "inv_number_hint": "004113", "account": "01.04",
         "balance_value": "184500",
         "links": {"cadastre_id": "c2", "level_ids": [{"level_index": 1}]}},
    ],
}

CACHE = {"objects": {
    "61:44:0050706:1": {"info": {
        "geometry": {"type": "Polygon", "coordinates": [
            [[39.7088, 47.2186], [39.7092, 47.2186],
             [39.7092, 47.2189], [39.7088, 47.2189], [39.7088, 47.2186]]
        ]},
    }},
    "61:44:0050706:31": {"info": {
        "geometry": {"type": "Polygon", "coordinates": [
            [[39.7089, 47.2187], [39.7091, 47.2187],
             [39.7091, 47.2188], [39.7089, 47.2188], [39.7089, 47.2187]]
        ]},
        "Количество этажей": "4",
    }},
    "61:44:0050706:119": {"info": {
        "geometry": {"type": "Point", "coordinates": [39.7090, 47.21875]},
    }},
}}

# Минимальный самодостаточный graph.html с meta-тегом и listener'ом
# (соответствует контракту 2.11.0 §5/§6, без CDN, без allow-same-origin).
GRAPH_HTML = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<meta name="ekcelo-graph-protocol" content="1">
<title>Демо-граф связей</title>
<style>body{font:14px sans-serif;padding:1em;background:#1a1a1d;color:#eee}
.node{padding:.5em;margin:.3em;border:1px solid #555;border-radius:4px;background:#222}
.node.selected{background:#0a3;border-color:#0f0}
.empty{color:#888;font-style:italic}</style>
</head>
<body>
<h1>Демо-граф (mini-fixture)</h1>
<p class="empty">Этот файл — упрощённая заглушка для viewer-теста. Реальный
граф эмитит <code>04_nspd_graph_v14.py</code> с vis-network внутри.</p>
<div id="nodes">
  <div class="node" data-id="61:44:0050706:1">ЗУ 61:44:0050706:1</div>
  <div class="node" data-id="61:44:0050706:31">Здание 61:44:0050706:31</div>
  <div class="node" data-id="61:44:0050706:119">Квартира 61:44:0050706:119</div>
  <div class="node" data-id="bu::demo000000000001">БУ Демо-филиал</div>
  <div class="node" data-id="eq::eq1">EQ Демо-котёл</div>
  <div class="node" data-id="legal::inn::6164098765">Бенефициар ИНН 6164098765</div>
</div>
<script>
// ekcelo-graph-protocol v1 (mini-fixture stub): postMessage + location.hash
(function(){
  function apply(id){
    if (!id) return;
    document.querySelectorAll('.node.selected').forEach(n => n.classList.remove('selected'));
    var el = document.querySelector('.node[data-id="' + id.replace(/"/g, '\\\\"') + '"]');
    if (el) { el.classList.add('selected'); el.scrollIntoView({behavior:'smooth', block:'center'}); }
  }
  try {
    var m = (location.hash || '').match(/(?:^#|&)node=([^&]+)/);
    if (m) apply(decodeURIComponent(m[1]));
  } catch(e) {}
  window.addEventListener('message', function(ev){
    var d = ev && ev.data;
    if (!d || d.type !== 'ekcelo.graph.select') return;
    apply(String(d.nodeId || ''));
  });
})();
</script>
</body>
</html>
"""

# Sidecar (id'ы для cross-link 08↔07)
GRAPH_INDEX = {
    "schema": 1,
    "by_cad_number": {
        "61:44:0050706:1":   "61:44:0050706:1",
        "61:44:0050706:31":  "61:44:0050706:31",
        "61:44:0050706:119": "61:44:0050706:119",
    },
    "by_bu_name":   {"Демо-филиал":        "bu::demo000000000001"},
    "by_eq_id":     {"eq1":                "eq::eq1"},
    "by_ben_inn":   {"6164098765":         "legal::inn::6164098765"},
    "by_ben_ogrn":  {"1026103098765":      "legal::inn::6164098765"},
    "by_ben_name":  {"ООО Демо-Бенефициар": "legal::inn::6164098765"},
}


def build(out_dir: Path) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "_data").mkdir(exist_ok=True)
    (out_dir / "_data" / "nspd_cache").mkdir(exist_ok=True)
    (out_dir / "Документы_JPG").mkdir(exist_ok=True)
    (out_dir / "Фотографии").mkdir(exist_ok=True)

    (out_dir / "_data" / "structure.json").write_text(
        json.dumps(STRUCTURE, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "_data" / "nspd_cache" / "cache.json").write_text(
        json.dumps(CACHE, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "_data" / "graph.html").write_text(GRAPH_HTML, encoding="utf-8")
    (out_dir / "_data" / "graph_node_index.json").write_text(
        json.dumps(GRAPH_INDEX, ensure_ascii=False, indent=2), encoding="utf-8")

    # 3 фото без EXIF — для photoPin_* (spiral вокруг центроида здания)
    fake_jpg = (
        b"\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01"
        b"\x00\x01\x00\x00\xff\xdb\x00C\x00" + b"\x08" * 64 + b"\xff\xd9"
    )
    photo_dir = (out_dir / "Фотографии" / "Недвижимость" / "Строения"
                 / "61_44_0050706_31" / "Фасад")
    photo_dir.mkdir(parents=True, exist_ok=True)
    for name in ("IMG_01.jpg", "IMG_02.jpg", "IMG_03.jpg"):
        (photo_dir / name).write_bytes(fake_jpg)

    return build_kmz(out_dir)


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    out_dir = Path(sys.argv[1]).expanduser().resolve()
    if out_dir.exists() and any(out_dir.iterdir()):
        print(f"[!] {out_dir} не пуста — отказываюсь перетирать. "
              "Удалите вручную или укажите пустую/несуществующую папку.",
              file=sys.stderr)
        return 1
    kmz = build(out_dir)
    print(f"[+] mini-fixture готова: {kmz}")
    print(f"    Откройте в viewer (drag&drop), убедитесь что у маркеров КН/БУ/EQ/БЕН")
    print(f"    в `<ExtendedData>` есть `graph_node_id`, и кнопка 🕸 работает.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
