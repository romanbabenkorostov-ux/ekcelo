/**
 * FE-3.1 hotfix: поддержка сырого .kml от Yandex Map Constructor.
 *
 * Отличия от CONTRACT_KMZ:
 *  - файл не ZIP, а сырой XML (.kml) — parseKmlText без распаковки;
 *  - <name/> пустой у полигонов; кадастр сидит в <description> текстом
 *    («Поле 23:15:0000000:2267 · …»), а не в <ExtendedData>.
 * Фикстура — реальный экспорт пользователя (winery «Олимп», 45 placemark'ов).
 */
import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

import {
  kmzToViewModel,
  parseGeoFile,
  parseKmlText,
} from "../src/adapters/kmz";

const YANDEX = readFileSync(
  resolve(process.cwd(), "tests/fixtures/yandex_olimp.kml"),
  "utf8",
);

describe("Yandex Map Constructor .kml (сырой)", () => {
  it("парсит сырой KML без распаковки ZIP", () => {
    const doc = parseKmlText(YANDEX);
    // 45 точек + ~50 полигонов
    expect(doc.placemarks.length).toBeGreaterThan(50);
  });

  it("извлекает cad_number из description (regex)", () => {
    const doc = parseKmlText(YANDEX);
    const zu = doc.placemarks.find((p) => p.cadNumber === "23:15:0000000:2267");
    expect(zu).toBeDefined();
    expect(zu!.geometry?.type).toBe("Polygon");
    // координаты Тамани: lon ~37.7, lat ~45.0
    expect(zu!.center![0]).toBeCloseTo(37.7, 0);
    expect(zu!.center![1]).toBeCloseTo(45.0, 0);
  });

  it("берёт первый кадастр когда в тексте их несколько", () => {
    const doc = parseKmlText(YANDEX);
    // «...лит.И модуль (23:15:0314001:40)» → основной :623, не :40
    const pm = doc.placemarks.find((p) =>
      p.description.includes("Здание хранилища лит.И"),
    );
    expect(pm?.cadNumber).toBe("23:15:0314001:623");
  });

  it("у полигона с пустым <name/> метка берётся из description", () => {
    const doc = parseKmlText(YANDEX);
    const zu = doc.placemarks.find((p) => p.cadNumber === "23:15:0000000:2267");
    // первый сегмент description до «·», без <br/>
    expect(zu!.name).toContain("Поле");
    expect(zu!.name).not.toContain("·");
  });

  it("placemark без кадастра → cadNumber null (не падает)", () => {
    const doc = parseKmlText(YANDEX);
    const noCad = doc.placemarks.find((p) =>
      p.description.includes("Емкостной парк"),
    );
    expect(noCad).toBeDefined();
    expect(noCad!.cadNumber).toBeNull();
  });

  it("собирает ViewModel объекта из Yandex-KML с geo", () => {
    const doc = parseKmlText(YANDEX);
    const vm = kmzToViewModel(doc, "23:15:0000000:2267");
    expect(vm.kind).toBe("object");
    expect(vm.id).toBe("23:15:0000000:2267");
    expect(vm.geo.geometry?.type).toBe("Polygon");
    expect(vm.geo.center).not.toBeNull();
  });
});

describe("parseGeoFile (диспетчер по расширению)", () => {
  it(".kml читается как текст (без распаковки ZIP)", async () => {
    const file = new File([YANDEX], "Олимп.kml", { type: "application/xml" });
    const doc = await parseGeoFile(file);
    expect(doc.placemarks.length).toBeGreaterThan(50);
    expect(
      doc.placemarks.some((p) => p.cadNumber === "23:15:0000000:2267"),
    ).toBe(true);
  });
});
