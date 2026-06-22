/**
 * Карта объекта на Leaflet. Рендерит geo.geometry (Polygon/Point) + center.
 *
 * Geo приходит из kmz-адаптера (координаты) — api не отдаёт до backend C3.3.
 * Если geo пустой — показываем сообщение «геометрия недоступна».
 *
 * Leaflet импортируется динамически чтобы:
 *  - не тянуть его в bundle когда карта не нужна (code-split);
 *  - тесты (happy-dom без canvas) не падали на import.
 *
 * UI-слой: не знает откуда geo (api или kmz) — контракт Geo из core.
 */
import type { Geo } from "@core/viewmodel";
import { clear, el } from "@ui/render-utils";

const OSM_TILES = "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png";
const OSM_ATTR = "© OpenStreetMap contributors";

/** Преобразует geo.geometry в Leaflet-слой. Возвращает null если нет геометрии. */
function geometryToLatLngs(
  geometry: Record<string, unknown> | null | undefined,
): { type: "polygon" | "point"; latlngs: Array<[number, number]> } | null {
  if (!geometry || typeof geometry !== "object") return null;
  const type = geometry["type"];
  const coords = geometry["coordinates"];
  if (type === "Polygon" && Array.isArray(coords)) {
    const ring = (coords as number[][][])[0];
    if (!ring) return null;
    // GeoJSON [lon,lat] → Leaflet [lat,lon]
    return {
      type: "polygon",
      latlngs: ring.map(([lon, lat]) => [lat!, lon!] as [number, number]),
    };
  }
  if (type === "Point" && Array.isArray(coords)) {
    const [lon, lat] = coords as number[];
    if (lon === undefined || lat === undefined) return null;
    return { type: "point", latlngs: [[lat, lon]] };
  }
  return null;
}

/**
 * Рендерит карту в контейнер. Async из-за динамического импорта Leaflet.
 * Безопасно вызывать в средах без полноценного DOM — при ошибке показывает
 * fallback-сообщение.
 */
export async function renderMap(container: HTMLElement, geo: Geo): Promise<void> {
  clear(container);

  const shape = geometryToLatLngs(geo.geometry);
  const center = geo.center;

  if (!shape && !center) {
    container.append(
      el("p", {
        class: "muted",
        text: "Геометрия недоступна (нет geo в источнике; материализация — backend C3.3).",
      }),
    );
    return;
  }

  const mapDiv = el("div", { class: "leaflet-host" });
  mapDiv.style.height = "360px";
  container.append(mapDiv);

  let L: typeof import("leaflet");
  try {
    L = await import("leaflet");
    await import("leaflet/dist/leaflet.css");
  } catch (err) {
    mapDiv.replaceWith(
      el("p", { class: "muted", text: `Карта недоступна: ${(err as Error).message}` }),
    );
    return;
  }

  const map = L.map(mapDiv).setView(
    center ? [center[1], center[0]] : [shape!.latlngs[0]![0], shape!.latlngs[0]![1]],
    17,
  );
  L.tileLayer(OSM_TILES, { attribution: OSM_ATTR, maxZoom: 19 }).addTo(map);

  if (shape?.type === "polygon") {
    const poly = L.polygon(shape.latlngs, { color: "#7f007f", weight: 2, fillOpacity: 0.25 }).addTo(map);
    map.fitBounds(poly.getBounds(), { padding: [24, 24] });
  } else if (shape?.type === "point") {
    L.marker(shape.latlngs[0]!).addTo(map);
  } else if (center) {
    L.marker([center[1], center[0]]).addTo(map);
  }

  // z_meters_top подпись (3D-extrude — будущее; пока текст).
  if (geo.z_meters_top) {
    container.append(
      el("p", {
        class: "muted",
        text: `Высота: ${geo.z_meters_top} м${geo.extrude ? " (extrude)" : ""}`,
      }),
    );
  }
}

/** Экспорт чистой функции для unit-тестов (без Leaflet/DOM). */
export const __test = { geometryToLatLngs };
