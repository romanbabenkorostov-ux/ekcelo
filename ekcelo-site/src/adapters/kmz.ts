/**
 * kmz → ViewModel адаптер (C1 KMZ → общая ViewModel).
 *
 * KMZ = ZIP-архив с `doc.kml` (+ images/, graph.html, _data/documents.json).
 * Структура doc.kml (CONTRACT_KMZ 2.x):
 *   <Placemark>
 *     <name>cad · address</name>
 *     <description>Кадастровый номер: …; Адрес: …; Этажность: …</description>
 *     <ExtendedData>
 *       <Data name="object_type"><value>zu|oks|room|bu|eq|ben|photo</value></Data>
 *       <Data name="cad_number"><value>…</value></Data>
 *       <Data name="graph_node_id"><value>…</value></Data>     ← = node.id в C4
 *       <Data name="z_meters_top"><value>…</value></Data>
 *       <Data name="parent_cad"><value>…</value></Data>
 *     </ExtendedData>
 *     <Polygon|Point>…<coordinates>lon,lat,z …</coordinates></…>
 *   </Placemark>
 *
 * Этот адаптер даёт ViewModel идентичную форме api-адаптера (DoD SPEC_frontend):
 * один объект, открытый из api и из kmz, рисуется одинаково. KMZ дополнительно
 * несёт geo (координаты), которых api не отдаёт до backend C3.3.
 *
 * Распаковка ZIP — через `fflate` (8KB). Парсинг KML — нативный DOMParser.
 */

import { unzipSync, strFromU8 } from "fflate";

import type {
  GraphEdge,
  GraphNode,
  ViewModel,
} from "@core/viewmodel";

/** object_type из KMZ → graphNode.kind (совместимо с backend graph). */
const KMZ_TYPE_TO_NODE_KIND: Record<string, string> = {
  zu: "land",
  oks: "building",
  room: "room",
  bu: "bu",
  eq: "equipment",
  ben: "beneficiary_legal",
  photo: "doc",
};

/** Распарсенный placemark из doc.kml. */
export interface KmzPlacemark {
  objectType: string;
  cadNumber: string | null;
  graphNodeId: string;
  name: string;
  description: string;
  /** Ключ-значение из description («Адрес: …; Этажность: …»). */
  fields: Record<string, string>;
  /** ExtendedData как map. */
  ext: Record<string, string>;
  /** [lon, lat] первой координаты (центр-приближение). */
  center: [number, number] | null;
  /** GeoJSON-подобная геометрия (Polygon/Point) WGS84. */
  geometry: Record<string, unknown> | null;
  zMetersTop: number | null;
  extrude: boolean;
  parentCad: string | null;
}

export interface KmzDocument {
  placemarks: KmzPlacemark[];
  /** extract_date из <Document><ExtendedData>. */
  extractDate: string | null;
}

export class KmzParseError extends Error {}

// ─────────────────────────────────────────────────────────────────────────────
//  Распаковка + парсинг
// ─────────────────────────────────────────────────────────────────────────────

/** Распаковывает KMZ (bytes) → KmzDocument. */
export function parseKmzBytes(bytes: Uint8Array): KmzDocument {
  const files = unzipSync(bytes);
  const kmlEntry =
    files["doc.kml"] ??
    Object.entries(files).find(([n]) => n.toLowerCase().endsWith(".kml"))?.[1];
  if (!kmlEntry) {
    throw new KmzParseError("в KMZ нет doc.kml");
  }
  return parseKmlText(strFromU8(kmlEntry));
}

/** Распаковывает KMZ из File (browser drag-drop). */
export async function parseKmzFile(file: File): Promise<KmzDocument> {
  const buf = new Uint8Array(await file.arrayBuffer());
  return parseKmzBytes(buf);
}

/** Читает сырой .kml из File (без распаковки — это не ZIP). */
export async function parseKmlFile(file: File): Promise<KmzDocument> {
  return parseKmlText(await file.text());
}

/**
 * Универсальный вход для drag-drop: .kml читается как текст, .kmz
 * распаковывается. Различаем по расширению (а не по сигнатуре) — File из
 * браузера несёт имя; .kml — это XML, .kmz — ZIP с doc.kml.
 */
export async function parseGeoFile(file: File): Promise<KmzDocument> {
  return file.name.toLowerCase().endsWith(".kml")
    ? parseKmlFile(file)
    : parseKmzFile(file);
}

/**
 * Tag lookup устойчивый к окружению:
 * - браузер (XML): `getElementsByTagName` матчит qualifiedName = localName
 *   (default xmlns без префикса);
 * - happy-dom (тест): case-insensitive, tagName в UPPERCASE.
 */
function tags(root: Element | Document, tag: string): Element[] {
  return Array.from(root.getElementsByTagName(tag));
}

/** Первый прямой потомок с данным tag (case-insensitive — для обоих сред). */
function childTag(parent: Element, tag: string): Element | null {
  const upper = tag.toUpperCase();
  for (const child of Array.from(parent.children)) {
    if (child.tagName.toUpperCase() === upper) return child;
  }
  // happy-dom обрывает .children после CDATA-соседа (<name/><description>
  // <![CDATA[…]]>… у Yandex KML) — fallback на scoped getElementsByTagName.
  // KML не вкладывает name/description/value, поэтому первый = искомый.
  return parent.getElementsByTagName(tag)[0] ?? null;
}

/** Парсит doc.kml текст → KmzDocument. */
export function parseKmlText(kml: string): KmzDocument {
  const doc = new DOMParser().parseFromString(normalizeKml(kml), "application/xml");
  const parseError = doc.getElementsByTagName("parsererror")[0];
  if (parseError) {
    throw new KmzParseError(`невалидный KML: ${parseError.textContent ?? ""}`);
  }

  // extract_date — на doc-уровне <Document><ExtendedData>. happy-dom давится
  // namespaced atom:author и обрывает .children, поэтому ищем Data[name=
  // extract_date] глобально (он уникален — placemarks несут object_type/
  // cad_number, но не extract_date).
  const extractDate = findDataValue(doc, "extract_date");

  const placemarks: KmzPlacemark[] = [];
  for (const pm of tags(doc, "Placemark")) {
    placemarks.push(parsePlacemark(pm));
  }
  return { placemarks, extractDate };
}

/** Кадастровый номер РФ: «23:15:0314001:617». Первое вхождение = основной. */
const CAD_RE = /\d+:\d+:\d+:\d+/;

/**
 * Разворачивает пустые self-closing `<name/>` / `<description/>` в парные теги.
 * Yandex Map Constructor пишет `<name/>` у полигонов; happy-dom (HTML-режим
 * парсера) не самозакрывает их и ошибочно вкладывает соседей (styleUrl,
 * Polygon) внутрь, ломая структуру. Реальный браузерный DOMParser в режиме
 * application/xml корректен и без этого — правка безвредна (CDATA не трогаем).
 */
function normalizeKml(kml: string): string {
  return kml.replace(/<(name|description)\s*\/>/gi, "<$1></$1>");
}

function parsePlacemark(pm: Element): KmzPlacemark {
  const ext = readExtendedData(childTag(pm, "ExtendedData"));
  const rawName = cdataText(childTag(pm, "name"));
  const description = cdataText(childTag(pm, "description"));
  const fields = parseDescription(description);

  const { center, geometry, extrude } = parseGeometry(pm);
  const zTop = ext.z_meters_top ? Number(ext.z_meters_top) : null;

  // cad_number: сначала ExtendedData (CONTRACT_KMZ), иначе — regex из текста
  // (Yandex Map Constructor кладёт кадастр в <description>/<name>, не в ExtData).
  const cadNumber =
    ext.cad_number ??
    CAD_RE.exec(description)?.[0] ??
    CAD_RE.exec(rawName)?.[0] ??
    null;

  // name: у Yandex-полигонов <name/> пустой — берём метку из description.
  const name = rawName || descriptionLabel(description);

  return {
    objectType: ext.object_type ?? "",
    cadNumber,
    graphNodeId: ext.graph_node_id ?? cadNumber ?? name,
    name,
    description,
    fields,
    ext,
    center,
    geometry,
    zMetersTop: Number.isFinite(zTop) ? zTop : null,
    extrude,
    parentCad: ext.parent_cad ?? null,
  };
}

/** Короткая метка из description: текст до первого «·», без `<br/>`. */
function descriptionLabel(desc: string): string {
  return (desc.split("·")[0] ?? "")
    .replace(/<br\s*\/?>/gi, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** Глобально ищет первое `<Data name="key"><value>…</value></Data>`. */
function findDataValue(doc: Document, key: string): string | null {
  for (const data of tags(doc, "Data")) {
    if (data.getAttribute("name") === key) {
      const v = childTag(data, "value")?.textContent?.trim();
      if (v) return v;
    }
  }
  return null;
}

function readExtendedData(node: Element | null): Record<string, string> {
  const out: Record<string, string> = {};
  if (!node) return out;
  for (const data of Array.from(node.children)) {
    if (data.tagName.toUpperCase() !== "DATA") continue;
    const key = data.getAttribute("name");
    const value = childTag(data, "value")?.textContent ?? "";
    if (key) out[key] = value.trim();
  }
  return out;
}

/** Парсит «Ключ: значение; Ключ2: значение2» из description. */
function parseDescription(desc: string): Record<string, string> {
  const out: Record<string, string> = {};
  for (const part of desc.split(";")) {
    const idx = part.indexOf(":");
    if (idx === -1) continue;
    const key = part.slice(0, idx).trim();
    const value = part.slice(idx + 1).trim();
    if (key) out[key] = value;
  }
  return out;
}

interface GeometryResult {
  center: [number, number] | null;
  geometry: Record<string, unknown> | null;
  extrude: boolean;
}

function parseGeometry(pm: Element): GeometryResult {
  const extrude = tags(pm, "extrude")[0]?.textContent?.trim() === "1";
  const coordsEl = tags(pm, "coordinates")[0];
  if (!coordsEl?.textContent) {
    return { center: null, geometry: null, extrude };
  }
  const tuples = coordsEl.textContent
    .trim()
    .split(/\s+/)
    .map((t) => t.split(",").map(Number))
    .filter((arr) => arr.length >= 2 && Number.isFinite(arr[0]) && Number.isFinite(arr[1]));

  if (tuples.length === 0) {
    return { center: null, geometry: null, extrude };
  }

  const isPolygon = tags(pm, "Polygon").length > 0;
  if (isPolygon) {
    const ring = tuples.map((t) => [t[0]!, t[1]!] as [number, number]);
    const center = centroid(ring);
    return {
      center,
      geometry: { type: "Polygon", coordinates: [ring] },
      extrude,
    };
  }
  // Point
  const first = tuples[0]!;
  const center: [number, number] = [first[0]!, first[1]!];
  return {
    center,
    geometry: { type: "Point", coordinates: center },
    extrude,
  };
}

function centroid(ring: Array<[number, number]>): [number, number] {
  let sx = 0;
  let sy = 0;
  for (const [x, y] of ring) {
    sx += x;
    sy += y;
  }
  return [sx / ring.length, sy / ring.length];
}

/**
 * Текст из узла, включая CDATA. В браузере CDATA — nodeType 4 (включается в
 * textContent). В happy-dom CDATA парсится как comment (nodeType 8), поэтому
 * собираем текст из text(3)/cdata(4)/comment(8) child-узлов вручную.
 */
function cdataText(node: Element | null): string {
  if (!node) return "";
  // Сначала собираем ТОЛЬКО прямые text(3)/cdata(4)/comment(8) узлы. Это важно
  // для happy-dom: при `<description><![CDATA[…]]></description>` со следующими
  // соседями (styleUrl/Polygon) парсер ошибочно вкладывает их в description, и
  // node.textContent вернул бы их текст (styleUrl+координаты). Берём данные
  // CDATA напрямую, элементы-потомки игнорируем.
  let acc = "";
  for (const child of Array.from(node.childNodes)) {
    const t = child.nodeType;
    if (t === 3 || t === 4 || t === 8) {
      acc += (child as { data?: string }).data ?? child.textContent ?? "";
    }
  }
  if (acc.trim()) return acc.trim();
  // Реальный браузер без CDATA: обычный текст.
  return node.textContent?.trim() ?? "";
}

// ─────────────────────────────────────────────────────────────────────────────
//  KmzDocument → ViewModel
// ─────────────────────────────────────────────────────────────────────────────

/**
 * Собирает ViewModel объекта из KMZ-документа. Форма идентична api-адаптеру.
 *
 * @param doc распарсенный KMZ
 * @param cad cad_number целевого объекта
 */
export function kmzToViewModel(doc: KmzDocument, cad: string): ViewModel {
  const target = doc.placemarks.find(
    (p) => p.cadNumber === cad && p.objectType !== "photo",
  );
  if (!target) {
    throw new KmzParseError(`объект ${cad} не найден в KMZ`);
  }

  return {
    kind: "object",
    id: cad,
    physical: {
      object_type: mapObjectType(target.objectType),
      address: target.fields["Адрес"] ?? null,
      area_m2: null, // KMZ не несёт площадь — придёт из api
      floors: parseFloors(target),
      etp: null,
    },
    ownership: {
      // KMZ-граф содержит бенефициаров; rights детально — из api.
      rights: [],
      beneficiaries: [],
      graph: kmzToGraph(doc),
    },
    geo: {
      center: target.center,
      geometry: target.geometry,
      z_meters_top: target.zMetersTop,
      extrude: target.extrude,
    },
    temporal: {
      extract_date: doc.extractDate,
      as_of_date: null,
    },
    media: {
      photos: doc.placemarks
        .filter((p) => p.objectType === "photo" && p.cadNumber === cad)
        .map((p) => ({ name: p.name, center: p.center })),
      documents: [],
    },
  };
}

/** Строит граф владения из KMZ placemarks. node.id = graph_node_id (= C4). */
export function kmzToGraph(doc: KmzDocument): { nodes: GraphNode[]; edges: GraphEdge[] } {
  const nodes: GraphNode[] = [];
  const edges: GraphEdge[] = [];
  const seen = new Set<string>();

  for (const pm of doc.placemarks) {
    if (pm.objectType === "photo") continue;
    if (seen.has(pm.graphNodeId)) continue;
    seen.add(pm.graphNodeId);
    nodes.push({
      id: pm.graphNodeId,
      kind: KMZ_TYPE_TO_NODE_KIND[pm.objectType] ?? "doc",
      label: pm.name.split("·")[0]?.trim() || pm.graphNodeId,
    });
  }

  // Рёбра: parent_cad (room→building), bu_id (eq→bu).
  for (const pm of doc.placemarks) {
    if (pm.parentCad) {
      edges.push({ from: pm.graphNodeId, to: pm.parentCad, kind: "part_of" });
    }
    const buId = pm.ext["bu_id"];
    if (buId && pm.objectType === "eq") {
      const bu = doc.placemarks.find((x) => x.ext["bu_id"] === buId && x.objectType === "bu");
      if (bu) edges.push({ from: pm.graphNodeId, to: bu.graphNodeId, kind: "belongs_to" });
    }
  }
  return { nodes, edges };
}

function mapObjectType(kmzType: string): string {
  const map: Record<string, string> = {
    zu: "land",
    oks: "building",
    room: "room",
  };
  return map[kmzType] ?? kmzType;
}

function parseFloors(pm: KmzPlacemark): number | null {
  const fromExt = pm.ext["floors_above"];
  if (fromExt) {
    const n = Number(fromExt);
    if (Number.isFinite(n)) return n;
  }
  const fromDesc = pm.fields["Этажность"];
  if (fromDesc) {
    const n = Number(fromDesc);
    if (Number.isFinite(n)) return n;
  }
  return null;
}
