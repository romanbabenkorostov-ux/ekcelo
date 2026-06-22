/**
 * Карта — тестируем ЧИСТУЮ функцию geometryToLatLngs (без Leaflet/DOM-canvas).
 * Полный рендер renderMap требует Leaflet — проверяется вручную в браузере.
 */
import { describe, expect, it } from "vitest";

import { __test } from "../src/ui/map";

const { geometryToLatLngs } = __test;

describe("geometryToLatLngs", () => {
  it("Polygon → latlngs с переворотом [lon,lat]→[lat,lon]", () => {
    const geom = {
      type: "Polygon",
      coordinates: [
        [
          [39.7088, 47.2186],
          [39.7092, 47.2186],
          [39.7092, 47.2189],
        ],
      ],
    };
    const res = geometryToLatLngs(geom);
    expect(res?.type).toBe("polygon");
    // GeoJSON [lon,lat] → Leaflet [lat,lon]
    expect(res?.latlngs[0]).toEqual([47.2186, 39.7088]);
    expect(res?.latlngs).toHaveLength(3);
  });

  it("Point → одна latlng", () => {
    const geom = { type: "Point", coordinates: [39.709, 47.2187] };
    const res = geometryToLatLngs(geom);
    expect(res?.type).toBe("point");
    expect(res?.latlngs[0]).toEqual([47.2187, 39.709]);
  });

  it("null geometry → null", () => {
    expect(geometryToLatLngs(null)).toBeNull();
    expect(geometryToLatLngs(undefined)).toBeNull();
  });

  it("неизвестный type → null", () => {
    expect(geometryToLatLngs({ type: "LineString", coordinates: [] })).toBeNull();
  });

  it("Polygon без ring → null", () => {
    expect(geometryToLatLngs({ type: "Polygon", coordinates: [] })).toBeNull();
  });
});
