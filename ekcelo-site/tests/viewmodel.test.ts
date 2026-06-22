/**
 * Контракт ViewModel — структурный sanity.
 *
 * Полное соответствие с `contracts/api/viewmodel.schema.json` проверяется
 * через api-adapter integration-тест (test_api_adapter) + бэкенд-тесты
 * `backend/tests/test_viewmodel.py`.
 */
import { describe, expect, it } from "vitest";

import { isViewModel } from "../src/core/viewmodel";

describe("isViewModel", () => {
  it("принимает валидный object ViewModel", () => {
    const vm = {
      kind: "object",
      id: "61:44:0050706:31",
      physical: { object_type: "room", area_m2: 125.4 },
      ownership: { rights: [], beneficiaries: [] },
      geo: {},
      temporal: { extract_date: "2026-05-20" },
    };
    expect(isViewModel(vm)).toBe(true);
  });

  it("принимает валидный lot ViewModel", () => {
    const vm = {
      kind: "lot",
      id: "lot-001",
      physical: {},
      ownership: { rights: [], beneficiaries: [] },
      geo: {},
      temporal: {},
      members: ["61:44:0050706:31"],
    };
    expect(isViewModel(vm)).toBe(true);
  });

  it("отвергает unknown kind", () => {
    expect(
      isViewModel({
        kind: "garbage",
        id: "x",
        physical: {},
        ownership: {},
        geo: {},
        temporal: {},
      }),
    ).toBe(false);
  });

  it("отвергает missing id", () => {
    expect(
      isViewModel({
        kind: "object",
        physical: {},
        ownership: {},
        geo: {},
        temporal: {},
      }),
    ).toBe(false);
  });

  it("отвергает null/undefined/non-object", () => {
    expect(isViewModel(null)).toBe(false);
    expect(isViewModel(undefined)).toBe(false);
    expect(isViewModel("string")).toBe(false);
    expect(isViewModel(42)).toBe(false);
  });
});
