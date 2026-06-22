/**
 * api → ViewModel адаптер (C4 REST клиент).
 *
 * Тонкая обёртка над fetch для эндпоинтов:
 *   GET /catalog?q&kind          → CatalogCard[]
 *   GET /objects/{cad}?as_of     → ViewModel
 *   GET /lots/{lot_id}?as_of     → ViewModel (kind=lot)
 *   GET /objects/{cad}/graph     → { nodes, edges }
 *
 * Auth:
 *   - В dev: vite proxy пробрасывает /api/* на бэкенд; cookie ekcelo_token
 *     (cycle 14 M2) идёт автоматически благодаря credentials: "include".
 *   - В prod: ту же стратегию даёт reverse-proxy (nginx).
 *   - 401 → редирект на /auth/login (через onUnauthorized callback).
 */

import type {
  CatalogCard,
  OwnershipGraph,
  ResourceKind,
  ViewModel,
} from "@core/viewmodel";

export interface ApiClientOptions {
  /** База URL backend (без trailing /). По умолчанию пустая — относительные пути под vite proxy. */
  baseUrl?: string;
  /** Колбэк при 401 (например, для редиректа на /auth/login). */
  onUnauthorized?: () => void;
  /** Кастомная fetch-функция (для тестов). */
  fetchImpl?: typeof fetch;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(`${status}: ${detail}`);
    this.name = "ApiError";
  }
}

export interface CatalogFilters {
  q?: string;
  kind?: ResourceKind;
}

export class ApiClient {
  private baseUrl: string;
  private fetchImpl: typeof fetch;
  private onUnauthorized?: () => void;

  constructor(opts: ApiClientOptions = {}) {
    this.baseUrl = opts.baseUrl ?? "";
    this.fetchImpl = opts.fetchImpl ?? fetch.bind(globalThis);
    this.onUnauthorized = opts.onUnauthorized;
  }

  async getCatalog(filters: CatalogFilters = {}): Promise<CatalogCard[]> {
    const qs = new URLSearchParams();
    if (filters.q) qs.set("q", filters.q);
    if (filters.kind) qs.set("kind", filters.kind);
    const path = `/catalog${qs.toString() ? `?${qs}` : ""}`;
    return this.json<CatalogCard[]>(path);
  }

  async getObject(cad: string, asOf?: string): Promise<ViewModel> {
    const qs = asOf ? `?as_of=${encodeURIComponent(asOf)}` : "";
    return this.json<ViewModel>(`/objects/${encodeURIComponent(cad)}${qs}`);
  }

  async getLot(lotId: string, asOf?: string): Promise<ViewModel> {
    const qs = asOf ? `?as_of=${encodeURIComponent(asOf)}` : "";
    return this.json<ViewModel>(`/lots/${encodeURIComponent(lotId)}${qs}`);
  }

  async getGraph(cad: string): Promise<OwnershipGraph> {
    return this.json<OwnershipGraph>(
      `/objects/${encodeURIComponent(cad)}/graph`,
    );
  }

  /** URL для скачивания KMZ (используется как href, не fetch). */
  bundleDownloadUrl(bundleId: string, fmt: "kmz" | "manifest" | "zip" | "db" | "json" = "kmz"): string {
    return `${this.baseUrl}/bundles/${encodeURIComponent(bundleId)}/download?fmt=${fmt}`;
  }

  private async json<T>(path: string): Promise<T> {
    const url = this.baseUrl + this.proxiedPath(path);
    const resp = await this.fetchImpl(url, {
      credentials: "include",
      headers: { Accept: "application/json" },
    });
    if (resp.status === 401) {
      this.onUnauthorized?.();
      throw new ApiError(401, "unauthorized");
    }
    if (!resp.ok) {
      const detail = await this.extractDetail(resp);
      throw new ApiError(resp.status, detail);
    }
    return (await resp.json()) as T;
  }

  private proxiedPath(path: string): string {
    // В dev-режиме vite проксирует /api/* → backend. В prod нгинкс делает то же.
    // Если baseUrl задан явно (TestClient / прямое подключение) — без префикса.
    return this.baseUrl ? path : `/api${path}`;
  }

  private async extractDetail(resp: Response): Promise<string> {
    try {
      const body = (await resp.json()) as { detail?: unknown };
      return typeof body.detail === "string" ? body.detail : resp.statusText;
    } catch {
      return resp.statusText;
    }
  }
}

/** Удобный редирект на /auth/login для 401 handler. */
export function redirectToLogin(): void {
  globalThis.location.assign("/auth/login");
}
