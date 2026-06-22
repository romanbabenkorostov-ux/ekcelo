/**
 * UI рендеры. Структурные проверки через happy-dom.
 *
 * Не проверяем CSS — только что DOM собран правильно по ViewModel.
 */
import { describe, expect, it, vi } from "vitest";

import type { CatalogCard, OwnershipGraph, ViewModel } from "../src/core/viewmodel";
import { renderCatalog } from "../src/ui/catalog";
import { renderGraph } from "../src/ui/graph";
import { renderObjectCard } from "../src/ui/object-card";

function container(): HTMLElement {
  const div = document.createElement("div");
  document.body.append(div);
  return div;
}

function makeViewModel(): ViewModel {
  return {
    kind: "object",
    id: "61:44:0050706:31",
    physical: {
      object_type: "room",
      address: "Ростов, Пушкина 1",
      area_m2: 125.4,
      floors: 5,
    },
    ownership: {
      rights: [
        {
          right_type: "собственность",
          right_holder_inn: "7707083893",
          share: "1/2",
          registration_date: "2024-05-10",
        },
      ],
      beneficiaries: [
        { inn: "7707083893", name_full: "ООО Тест Полное", name_short: "ООО Тест" },
      ],
    },
    geo: {},
    temporal: { extract_date: "2026-05-20" },
  };
}

describe("renderCatalog", () => {
  it("рисует пустой каталог", () => {
    const c = container();
    renderCatalog(c, [], { onSelect: () => {} });
    expect(c.querySelector(".empty")).toBeTruthy();
  });

  it("рисует карточки + клик вызывает callback", () => {
    const c = container();
    const cards: CatalogCard[] = [
      { kind: "object", id: "61:44:0050706:31", title: "Пушкина 1", address: "Ростов" },
      { kind: "lot", id: "lot-001", title: "Лот №1" },
    ];
    const onSelect = vi.fn();
    renderCatalog(c, cards, { onSelect });
    const items = c.querySelectorAll(".catalog-item");
    expect(items).toHaveLength(2);
    const title = c.querySelector<HTMLButtonElement>(".catalog-title");
    title?.click();
    expect(onSelect).toHaveBeenCalledWith(cards[0]);
  });

  it("очищает контейнер при повторном рендере", () => {
    const c = container();
    renderCatalog(c, [{ kind: "object", id: "a", title: "A" }], { onSelect: () => {} });
    renderCatalog(c, [{ kind: "object", id: "b", title: "B" }], { onSelect: () => {} });
    expect(c.querySelectorAll(".catalog-item")).toHaveLength(1);
    expect(c.querySelector(".catalog-title")?.textContent).toBe("B");
  });

  it("XSS защищён — title как textContent, не innerHTML", () => {
    const c = container();
    renderCatalog(
      c,
      [{ kind: "object", id: "<x>", title: "<script>alert(1)</script>" }],
      { onSelect: () => {} },
    );
    expect(c.querySelector("script")).toBeNull();
    expect(c.querySelector(".catalog-title")?.textContent).toContain("<script>");
  });
});

describe("renderObjectCard", () => {
  it("рисует 4 характеристики", () => {
    const c = container();
    renderObjectCard(c, makeViewModel());
    expect(c.querySelector(".char-physical")).toBeTruthy();
    expect(c.querySelector(".char-ownership")).toBeTruthy();
    expect(c.querySelector(".char-geo")).toBeTruthy();
    expect(c.querySelector(".char-temporal")).toBeTruthy();
  });

  it("показывает area + address + floors", () => {
    const c = container();
    renderObjectCard(c, makeViewModel());
    const text = c.textContent ?? "";
    expect(text).toContain("125,4");
    expect(text).toContain("Ростов, Пушкина 1");
    expect(text).toContain("5");
  });

  it("резолвит бенефициара по ИНН в правах", () => {
    const c = container();
    renderObjectCard(c, makeViewModel());
    expect(c.querySelector(".char-ownership")?.textContent).toContain("ООО Тест");
  });

  it("показывает members для lot", () => {
    const c = container();
    const lot: ViewModel = {
      ...makeViewModel(),
      kind: "lot",
      id: "lot-001",
      members: ["61:44:0050706:31", "61:44:0050706:99"],
    };
    renderObjectCard(c, lot);
    expect(c.querySelector(".char-members")).toBeTruthy();
    expect(c.querySelectorAll(".members li")).toHaveLength(2);
  });

  it("геометрия пустая → muted-сообщение", () => {
    const c = container();
    renderObjectCard(c, makeViewModel());
    expect(c.querySelector(".char-geo .muted")).toBeTruthy();
  });
});

describe("renderGraph", () => {
  it("рисует nodes + edges", () => {
    const c = container();
    const graph: OwnershipGraph = {
      nodes: [
        { id: "61:44:0050706:31", kind: "room", label: "Пушкина" },
        { id: "right:1", kind: "right", label: "собственность" },
        { id: "inn:7707083893", kind: "beneficiary_legal", label: "ООО Тест" },
      ],
      edges: [
        { from: "61:44:0050706:31", to: "right:1", kind: "has_right" },
        { from: "right:1", to: "inn:7707083893", kind: "held_by" },
      ],
    };
    renderGraph(c, graph);
    expect(c.querySelectorAll(".graph-nodes > li")).toHaveLength(3);
    expect(c.textContent).toContain("--has_right→");
    expect(c.textContent).toContain("--held_by→");
  });

  it("пустой граф", () => {
    const c = container();
    renderGraph(c, { nodes: [], edges: [] });
    expect(c.querySelector(".empty")).toBeTruthy();
  });
});
