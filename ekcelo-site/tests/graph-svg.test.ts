/**
 * Интерактивный SVG-граф — структурные проверки через happy-dom.
 */
import { describe, expect, it, vi } from "vitest";

import type { OwnershipGraph } from "../src/core/viewmodel";
import { renderGraphSvg } from "../src/ui/graph-svg";

function container(): HTMLElement {
  const div = document.createElement("div");
  document.body.append(div);
  return div;
}

function sampleGraph(): OwnershipGraph {
  return {
    nodes: [
      { id: "61:44:0050706:31", kind: "building", label: "Здание" },
      { id: "right:1", kind: "right", label: "собственность" },
      { id: "inn:7707083893", kind: "beneficiary_legal", label: "ООО Тест" },
    ],
    edges: [
      { from: "61:44:0050706:31", to: "right:1", kind: "has_right" },
      { from: "right:1", to: "inn:7707083893", kind: "held_by" },
    ],
  };
}

describe("renderGraphSvg", () => {
  it("рисует SVG с узлами и рёбрами", () => {
    const c = container();
    renderGraphSvg(c, sampleGraph());
    const svg = c.querySelector("svg.graph-svg");
    expect(svg).toBeTruthy();
    expect(c.querySelectorAll(".gnode")).toHaveLength(3);
    expect(c.querySelectorAll(".edge")).toHaveLength(2);
  });

  it("узлы несут data-id (graph_node_id)", () => {
    const c = container();
    renderGraphSvg(c, sampleGraph());
    const ids = Array.from(c.querySelectorAll(".gnode")).map((n) =>
      n.getAttribute("data-id"),
    );
    expect(ids).toContain("61:44:0050706:31");
    expect(ids).toContain("inn:7707083893");
  });

  it("пустой граф → сообщение", () => {
    const c = container();
    renderGraphSvg(c, { nodes: [], edges: [] });
    expect(c.querySelector(".empty")).toBeTruthy();
    expect(c.querySelector("svg")).toBeNull();
  });

  it("граф без рёбер → подпись, без svg (геометрия Yandex-KML)", () => {
    const c = container();
    renderGraphSvg(c, {
      nodes: [
        { id: "a", kind: "doc", label: "A" },
        { id: "b", kind: "doc", label: "B" },
      ],
      edges: [],
    });
    expect(c.querySelector(".empty")).toBeTruthy();
    expect(c.querySelector("svg")).toBeNull();
  });

  it("клик по узлу вызывает onNodeClick", () => {
    const c = container();
    const onNodeClick = vi.fn();
    renderGraphSvg(c, sampleGraph(), { onNodeClick });
    const node = c.querySelector<SVGGElement>(".gnode");
    node?.dispatchEvent(new Event("click"));
    expect(onNodeClick).toHaveBeenCalled();
  });

  it("узел building получает класс gnode-building", () => {
    const c = container();
    renderGraphSvg(c, sampleGraph());
    expect(c.querySelector(".gnode-building")).toBeTruthy();
    expect(c.querySelector(".gnode-right")).toBeTruthy();
    expect(c.querySelector(".gnode-beneficiary_legal")).toBeTruthy();
  });

  it("игнорирует рёбра к несуществующим узлам", () => {
    const c = container();
    renderGraphSvg(c, {
      nodes: [{ id: "a", kind: "building", label: "A" }],
      edges: [{ from: "a", to: "ghost", kind: "x" }],
    });
    // ребро к ghost не рисуется (ghost нет в nodes)
    expect(c.querySelectorAll(".edge")).toHaveLength(0);
  });

  it("узлы фокусируемы (tabindex) для a11y", () => {
    const c = container();
    renderGraphSvg(c, sampleGraph());
    const node = c.querySelector(".gnode");
    expect(node?.getAttribute("tabindex")).toBe("0");
  });
});
