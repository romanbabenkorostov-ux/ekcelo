/**
 * ViewModel — каноническая форма объекта/лота (C4).
 *
 * Зеркало `contracts/api/viewmodel.schema.json` (backend monorepo). Зеркало
 * проверяется тестом `tests/viewmodel-contract.test.ts` (parsing).
 *
 * Четыре характеристики EKCELO (см. SPEC_frontend.md):
 *   physical   — что это (object_type, address, area, floors, ETP §6)
 *   ownership  — чьё (rights, beneficiaries, graph узлы/рёбра)
 *   geo        — где (center, geometry WGS84, z_meters_top)
 *   temporal   — когда (extract_date, as_of_date)
 *
 * Этой формой UI рисует одинаково из обоих адаптеров (api→ViewModel и
 * kmz→ViewModel) — принцип «полного REST-рендеринга».
 */

export type ResourceKind = "object" | "lot";

export interface Physical {
  object_type?: string | null;
  address?: string | null;
  area_m2?: number | null;
  floors?: number | null;
  /** ЭТП §6: parsed JSON блок (layout/risks/source/confidence). */
  etp?: Record<string, unknown> | null;
}

export interface RightItem {
  right_type: string;
  right_holder_inn?: string | null;
  /** Дробь num/den (например "1/2"). */
  share?: string | null;
  registration_number?: string | null;
  registration_date?: string | null;
}

export interface Beneficiary {
  inn: string;
  name_full: string;
  name_short?: string | null;
  entity_type?: string | null;
}

/** Узел графа владения. id = graph_node_id из C1-контракта. */
export interface GraphNode {
  id: string;
  kind: string;
  label: string;
}

export interface GraphEdge {
  from: string;
  to: string;
  kind: string;
}

export interface OwnershipGraph {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface Ownership {
  rights: RightItem[];
  beneficiaries: Beneficiary[];
  /** В ViewModel (C4) граф может быть null — отдельный endpoint /graph. */
  graph?: OwnershipGraph | null;
}

export interface Geo {
  /** [lon, lat] WGS84. */
  center?: [number, number] | null;
  /** GeoJSON-подобная геометрия. */
  geometry?: Record<string, unknown> | null;
  z_meters_top?: number | null;
  extrude?: boolean;
}

export interface Temporal {
  extract_date?: string | null;
  as_of_date?: string | null;
}

export interface Media {
  photos: Array<Record<string, unknown>>;
  documents: Array<Record<string, unknown>>;
}

export interface ViewModel {
  kind: ResourceKind;
  /** cad_number для object, lot_id для lot. */
  id: string;
  physical: Physical;
  ownership: Ownership;
  geo: Geo;
  temporal: Temporal;
  media?: Media | null;
  /** Для kind=lot: cad_number входящих объектов. */
  members?: string[] | null;
}

/** Карточка из /catalog (C4 openapi.yaml::CatalogCard). */
export interface CatalogCard {
  kind: ResourceKind;
  id: string;
  title: string;
  address?: string | null;
  extract_date?: string | null;
  thumb_url?: string | null;
}

/** Опц. структурный sanity check ViewModel (для тестов и runtime-валидации). */
export function isViewModel(value: unknown): value is ViewModel {
  if (!value || typeof value !== "object") return false;
  const v = value as Record<string, unknown>;
  return (
    (v.kind === "object" || v.kind === "lot") &&
    typeof v.id === "string" &&
    typeof v.physical === "object" &&
    typeof v.ownership === "object" &&
    typeof v.geo === "object" &&
    typeof v.temporal === "object"
  );
}

// ─────────────────────────────────────────────────────────────────────────────
//  Гранты (C6 RBAC) — для UI делегирования/шеринга (FE-3)
// ─────────────────────────────────────────────────────────────────────────────

export type GrantAction =
  | "input" | "edit" | "view" | "export" | "delegate" | "share";

export type GrantResourceType = "lot" | "object" | "bundle";

/** Грант из GET /grants/me (C6 backend GrantResponse). */
export interface Grant {
  grant_id: string;
  subject_sub: string;
  action: string;
  resource_type: string;
  resource_id: string;
  granted_by: string;
  revocable: boolean;
  expires_at?: string | null;
}

/** Тело POST /grants. */
export interface GrantCreate {
  subject_sub: string;
  action: GrantAction;
  resource_type: GrantResourceType;
  resource_id: string;
  expires_at?: string | null;
}
