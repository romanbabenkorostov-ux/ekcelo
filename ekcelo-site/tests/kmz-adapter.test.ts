/**
 * kmz → ViewModel адаптер. Использует РЕАЛЬНЫЙ sample KMZ от парсера
 * (tests/fixtures/sample.kmz — demo-multi-extract от
 * pirushin_sosn_rocha_08_build_kmz_v2.py).
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import {
  KmzParseError,
  kmzToGraph,
  kmzToViewModel,
  parseKmlText,
  parseKmzBytes,
} from "../src/adapters/kmz";

// happy-dom переопределяет import.meta.url на non-file scheme — берём путь
// относительно cwd (корень ekcelo-site при запуске vitest).
const SAMPLE = new Uint8Array(
  readFileSync(resolve(process.cwd(), "tests/fixtures/sample.kmz")),
);

describe("parseKmzBytes (реальный sample)", () => {
  it("распаковывает doc.kml и парсит placemarks", () => {
    const doc = parseKmzBytes(SAMPLE);
    expect(doc.placemarks.length).toBeGreaterThan(0);
    expect(doc.extractDate).toBe("2026-01-15");
  });

  it("извлекает земельный участок с геометрией", () => {
    const doc = parseKmzBytes(SAMPLE);
    const zu = doc.placemarks.find((p) => p.cadNumber === "61:44:0050706:1");
    expect(zu).toBeDefined();
    expect(zu!.objectType).toBe("zu");
    expect(zu!.geometry?.type).toBe("Polygon");
    expect(zu!.center).not.toBeNull();
    // координаты Ростова: lon ~39.7, lat ~47.2
    expect(zu!.center![0]).toBeCloseTo(39.709, 1);
    expect(zu!.center![1]).toBeCloseTo(47.218, 1);
  });

  it("извлекает ОКС с z_meters_top + extrude", () => {
    const doc = parseKmzBytes(SAMPLE);
    const oks = doc.placemarks.find((p) => p.cadNumber === "61:44:0050706:31" && p.objectType === "oks");
    expect(oks).toBeDefined();
    expect(oks!.zMetersTop).toBe(12.0);
    expect(oks!.extrude).toBe(true);
    expect(oks!.graphNodeId).toBe("61:44:0050706:31");
  });

  it("парсит description в поля (Адрес/Этажность)", () => {
    const doc = parseKmzBytes(SAMPLE);
    const oks = doc.placemarks.find((p) => p.cadNumber === "61:44:0050706:31" && p.objectType === "oks");
    expect(oks!.fields["Адрес"]).toContain("Ростов");
    expect(oks!.fields["Этажность"]).toBe("4");
  });

  it("извлекает parent_cad у помещения", () => {
    const doc = parseKmzBytes(SAMPLE);
    const room = doc.placemarks.find((p) => p.objectType === "room");
    expect(room?.parentCad).toBe("61:44:0050706:31");
  });
});

describe("kmzToViewModel", () => {
  it("собирает ViewModel ОКС идентичной формы", () => {
    const doc = parseKmzBytes(SAMPLE);
    const vm = kmzToViewModel(doc, "61:44:0050706:31");
    expect(vm.kind).toBe("object");
    expect(vm.id).toBe("61:44:0050706:31");
    expect(vm.physical.object_type).toBe("building"); // oks → building
    expect(vm.physical.address).toContain("Ростов");
    expect(vm.physical.floors).toBe(4);
    // geo из KMZ (api не отдаёт до C3.3)
    expect(vm.geo.center).not.toBeNull();
    expect(vm.geo.z_meters_top).toBe(12.0);
    expect(vm.geo.extrude).toBe(true);
    expect(vm.temporal.extract_date).toBe("2026-01-15");
  });

  it("собирает media.photos для объекта", () => {
    const doc = parseKmzBytes(SAMPLE);
    const vm = kmzToViewModel(doc, "61:44:0050706:31");
    expect(vm.media?.photos.length).toBe(3); // IMG_01/02/03
  });

  it("бросает KmzParseError для несуществующего cad", () => {
    const doc = parseKmzBytes(SAMPLE);
    expect(() => kmzToViewModel(doc, "00:00:0000000:00")).toThrow(KmzParseError);
  });
});

describe("kmzToGraph", () => {
  it("строит узлы с graph_node_id = node.id (C1=C4 ключ)", () => {
    const doc = parseKmzBytes(SAMPLE);
    const graph = kmzToGraph(doc);
    const ids = graph.nodes.map((n) => n.id);
    expect(ids).toContain("61:44:0050706:31"); // oks
    expect(ids).toContain("61:44:0050706:1"); // zu
    // фото НЕ узлы графа
    expect(graph.nodes.every((n) => n.kind !== "photo")).toBe(true);
  });

  it("строит ребро part_of (помещение → здание)", () => {
    const doc = parseKmzBytes(SAMPLE);
    const graph = kmzToGraph(doc);
    const partOf = graph.edges.find((e) => e.kind === "part_of");
    expect(partOf).toBeDefined();
    expect(partOf!.to).toBe("61:44:0050706:31");
  });

  it("маппит object_type → graphNode.kind", () => {
    const doc = parseKmzBytes(SAMPLE);
    const graph = kmzToGraph(doc);
    const zu = graph.nodes.find((n) => n.id === "61:44:0050706:1");
    expect(zu?.kind).toBe("land");
    const oks = graph.nodes.find((n) => n.id === "61:44:0050706:31");
    expect(oks?.kind).toBe("building");
  });
});

describe("parseKmlText errors", () => {
  it("KML без Placemark → пустой документ", () => {
    const doc = parseKmlText(
      '<?xml version="1.0"?><kml xmlns="http://www.opengis.net/kml/2.2"><Document></Document></kml>',
    );
    expect(doc.placemarks).toHaveLength(0);
    expect(doc.extractDate).toBeNull();
  });

  it("мусорный ввод не падает фатально (graceful)", () => {
    // Парсер устойчив: либо бросает KmzParseError, либо даёт пустой результат.
    let placemarks = -1;
    try {
      placemarks = parseKmlText("<<not xml").placemarks.length;
    } catch (err) {
      expect(err).toBeInstanceOf(KmzParseError);
      return;
    }
    expect(placemarks).toBe(0);
  });
});

describe("cross-match api↔kmz (DoD SPEC_frontend)", () => {
  it("ViewModel из KMZ имеет ту же core-форму что api", () => {
    const doc = parseKmzBytes(SAMPLE);
    const vm = kmzToViewModel(doc, "61:44:0050706:31");
    // Структурный контракт: 4 характеристики + kind + id, как в api ViewModel.
    for (const key of ["kind", "id", "physical", "ownership", "geo", "temporal"]) {
      expect(vm).toHaveProperty(key);
    }
    // id одинаков, kind одинаков — рисуется одним UI.
    expect(vm.id).toBe("61:44:0050706:31");
    expect(vm.kind).toBe("object");
  });
});
