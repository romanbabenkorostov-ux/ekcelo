/**
 * Простой текстовый рендер графа владения. FE-2 заменит на интерактивный.
 * Цель FE-1: показать что граф достаётся и матчится по graph_node_id.
 */
import type { OwnershipGraph } from "@core/viewmodel";
import { clear, el } from "@ui/render-utils";

export function renderGraph(
  container: HTMLElement,
  graph: OwnershipGraph,
): void {
  clear(container);
  container.append(el("h2", { text: "Граф владения" }));
  if (graph.nodes.length === 0) {
    container.append(el("p", { class: "empty", text: "Граф пуст" }));
    return;
  }
  const ul = el("ul", { class: "graph-nodes" });
  for (const node of graph.nodes) {
    const outgoing = graph.edges.filter((e) => e.from === node.id);
    const li = el("li");
    li.append(
      el("span", {
        class: `node node-${node.kind}`,
        text: `[${node.kind}] ${node.label}`,
        title: node.id,
      }),
    );
    if (outgoing.length > 0) {
      const sub = el("ul", { class: "graph-edges" });
      for (const e of outgoing) {
        const target = graph.nodes.find((n) => n.id === e.to);
        sub.append(
          el("li", {
            text: `--${e.kind}→ ${target?.label ?? e.to}`,
          }),
        );
      }
      li.append(sub);
    }
    ul.append(li);
  }
  container.append(ul);
}
