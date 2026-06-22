/**
 * api→ViewModel адаптер — клиент C4 эндпоинтов.
 *
 * Тесты используют моки fetch вместо живого бэкенда. Контракт-эквивалентность
 * с реальным API проверяется отдельным integration-тестом (FE-2+).
 */
import { describe, expect, it, vi } from "vitest";

import { ApiClient, ApiError } from "../src/adapters/api";

function mockFetch(
  responseFactory: () => { status: number; body: unknown },
): typeof fetch {
  return vi.fn(async (_input: RequestInfo | URL, _init?: RequestInit) => {
    const { status, body } = responseFactory();
    return new Response(JSON.stringify(body), {
      status,
      headers: { "Content-Type": "application/json" },
    });
  }) as unknown as typeof fetch;
}

describe("ApiClient.getCatalog", () => {
  it("парсит ответ /catalog", async () => {
    const cards = [
      { kind: "object", id: "61:44:0050706:31", title: "Пушкина 1" },
      { kind: "lot", id: "lot-001", title: "Лот №1" },
    ];
    const api = new ApiClient({
      baseUrl: "http://test",
      fetchImpl: mockFetch(() => ({ status: 200, body: cards })),
    });
    const got = await api.getCatalog();
    expect(got).toHaveLength(2);
    expect(got[0]?.kind).toBe("object");
    expect(got[1]?.id).toBe("lot-001");
  });

  it("прокидывает фильтр q", async () => {
    const fetchMock = vi.fn(async (url) => {
      expect(String(url)).toContain("/catalog?q=%D0%9F%D1%83%D1%88");
      return new Response(JSON.stringify([]), { status: 200 });
    });
    const api = new ApiClient({ baseUrl: "http://test", fetchImpl: fetchMock as unknown as typeof fetch });
    await api.getCatalog({ q: "Пуш" });
    expect(fetchMock).toHaveBeenCalled();
  });

  it("прокидывает фильтр kind", async () => {
    const fetchMock = vi.fn(async (url) => {
      expect(String(url)).toContain("kind=object");
      return new Response(JSON.stringify([]), { status: 200 });
    });
    const api = new ApiClient({ baseUrl: "http://test", fetchImpl: fetchMock as unknown as typeof fetch });
    await api.getCatalog({ kind: "object" });
  });
});

describe("ApiClient.getObject", () => {
  it("парсит ViewModel", async () => {
    const vm = {
      kind: "object", id: "61:44:0050706:31",
      physical: { object_type: "room" },
      ownership: { rights: [], beneficiaries: [] },
      geo: {}, temporal: {},
    };
    const api = new ApiClient({
      baseUrl: "http://test",
      fetchImpl: mockFetch(() => ({ status: 200, body: vm })),
    });
    const got = await api.getObject("61:44:0050706:31");
    expect(got.id).toBe("61:44:0050706:31");
    expect(got.physical.object_type).toBe("room");
  });

  it("кодирует as_of в query", async () => {
    const fetchMock = vi.fn(async (url) => {
      expect(String(url)).toContain("as_of=2026-01-01");
      return new Response(JSON.stringify({
        kind: "object", id: "x", physical: {},
        ownership: { rights: [], beneficiaries: [] }, geo: {}, temporal: {},
      }), { status: 200 });
    });
    const api = new ApiClient({ baseUrl: "http://test", fetchImpl: fetchMock as unknown as typeof fetch });
    await api.getObject("x", "2026-01-01");
  });
});

describe("ApiClient.getGraph", () => {
  it("парсит nodes+edges", async () => {
    const api = new ApiClient({
      baseUrl: "http://test",
      fetchImpl: mockFetch(() => ({
        status: 200,
        body: {
          nodes: [{ id: "n1", kind: "right", label: "x" }],
          edges: [{ from: "n1", to: "n2", kind: "held_by" }],
        },
      })),
    });
    const got = await api.getGraph("61:44:0050706:31");
    expect(got.nodes).toHaveLength(1);
    expect(got.edges).toHaveLength(1);
  });
});

describe("ApiClient error handling", () => {
  it("401 → onUnauthorized + ApiError", async () => {
    const onUnauthorized = vi.fn();
    const api = new ApiClient({
      baseUrl: "http://test",
      onUnauthorized,
      fetchImpl: mockFetch(() => ({ status: 401, body: { detail: "no token" } })),
    });
    await expect(api.getCatalog()).rejects.toBeInstanceOf(ApiError);
    expect(onUnauthorized).toHaveBeenCalled();
  });

  it("403 → ApiError со status 403", async () => {
    const api = new ApiClient({
      baseUrl: "http://test",
      fetchImpl: mockFetch(() => ({ status: 403, body: { detail: "forbidden" } })),
    });
    try {
      await api.getObject("x");
      expect.fail("должна быть ошибка");
    } catch (err) {
      expect(err).toBeInstanceOf(ApiError);
      expect((err as ApiError).status).toBe(403);
      expect((err as ApiError).detail).toBe("forbidden");
    }
  });

  it("500 без JSON body → ApiError со statusText", async () => {
    const fetchMock = vi.fn(
      async () => new Response("upstream error", { status: 500, statusText: "Internal Server Error" }),
    );
    const api = new ApiClient({ baseUrl: "http://test", fetchImpl: fetchMock as unknown as typeof fetch });
    try {
      await api.getCatalog();
      expect.fail("должна быть ошибка");
    } catch (err) {
      expect((err as ApiError).status).toBe(500);
    }
  });
});

describe("ApiClient.bundleDownloadUrl", () => {
  it("по умолчанию fmt=kmz", () => {
    const api = new ApiClient({ baseUrl: "http://test" });
    expect(api.bundleDownloadUrl("abc")).toBe(
      "http://test/bundles/abc/download?fmt=kmz",
    );
  });

  it("принимает другие fmt", () => {
    const api = new ApiClient({ baseUrl: "http://test" });
    expect(api.bundleDownloadUrl("abc", "zip")).toContain("fmt=zip");
  });
});

describe("ApiClient proxied path (dev/prod)", () => {
  it("без baseUrl → префикс /api для vite proxy", async () => {
    const fetchMock = vi.fn(async (url) => {
      expect(String(url)).toBe("/api/catalog");
      return new Response("[]", { status: 200 });
    });
    const api = new ApiClient({ fetchImpl: fetchMock as unknown as typeof fetch });
    await api.getCatalog();
  });

  it("с baseUrl → без префикса (прямой бэкенд)", async () => {
    const fetchMock = vi.fn(async (url) => {
      expect(String(url)).toBe("http://backend:8000/catalog");
      return new Response("[]", { status: 200 });
    });
    const api = new ApiClient({
      baseUrl: "http://backend:8000",
      fetchImpl: fetchMock as unknown as typeof fetch,
    });
    await api.getCatalog();
  });
});
