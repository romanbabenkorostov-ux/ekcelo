/**
 * Интерактивный SVG-граф владения. Без внешних зависимостей.
 *
 * Layout — детерминированный радиальный: object-узлы в центре, right-узлы
 * кольцом, beneficiary-узлы внешним кольцом. Hover подсвечивает связанные
 * рёбра; клик эмитит onNodeClick.
 *
 * Заменяет текстовый renderGraph из FE-1. UI не знает откуда граф (api или kmz).
 */
import type { GraphEdge, GraphNode, OwnershipGraph } from "@core/viewmodel";
import { clear } from "@ui/render-utils";

const SVG_NS = "http://www.w3.org/2000/svg";
const WIDTH = 640;
const HEIGHT = 420;

interface Positioned extends GraphNode {
  x: number;
  y: number;
}

export interface GraphCallbacks {
  onNodeClick?: (node: GraphNode) => void;
}

/** Группировка узлов по «слою» для радиального layout. */
function layerOf(kind: string): number {
  if (kind.startsWith("beneficiary")) return 2;
  if (kind === "right") return 1;
  return 0; // object/land/building/room/bu/equipment — центр
}

export function renderGraphSvg(
  container: HTMLElement,
  graph: OwnershipGraph,
  cb: GraphCallbacks = {},
): void {
  clear(container);
  if (graph.nodes.length === 0) {
    const p = document.createElement("p");
    p.className = "empty";
    p.textContent = "Граф пуст";
    container.append(p);
    return;
  }

  const positioned = layout(graph.nodes);
  const byId = new Map(positioned.map((n) => [n.id, n]));

  const svg = document.createElementNS(SVG_NS, "svg");
  svg.setAttribute("viewBox", `0 0 ${WIDTH} ${HEIGHT}`);
  svg.setAttribute("class", "graph-svg");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label", "Граф владения");

  // Рёбра (под узлами)
  const edgeEls = new Map<GraphEdge, SVGLineElement>();
  for (const e of graph.edges) {
    const from = byId.get(e.from);
    const to = byId.get(e.to);
    if (!from || !to) continue;
    const line = document.createElementNS(SVG_NS, "line");
    line.setAttribute("x1", String(from.x));
    line.setAttribute("y1", String(from.y));
    line.setAttribute("x2", String(to.x));
    line.setAttribute("y2", String(to.y));
    line.setAttribute("class", `edge edge-${e.kind}`);
    line.setAttribute("data-from", e.from);
    line.setAttribute("data-to", e.to);
    svg.append(line);
    edgeEls.set(e, line);
  }

  // Узлы
  for (const node of positioned) {
    const g = document.createElementNS(SVG_NS, "g");
    g.setAttribute("class", `gnode gnode-${node.kind}`);
    g.setAttribute("transform", `translate(${node.x},${node.y})`);
    g.setAttribute("tabindex", "0");
    g.setAttribute("data-id", node.id);

    const circle = document.createElementNS(SVG_NS, "circle");
    circle.setAttribute("r", String(layerOf(node.kind) === 0 ? 18 : 12));
    g.append(circle);

    const title = document.createElementNS(SVG_NS, "title");
    title.textContent = `${node.kind}: ${node.label}\n${node.id}`;
    g.append(title);

    const text = document.createElementNS(SVG_NS, "text");
    text.setAttribute("y", "-22");
    text.setAttribute("text-anchor", "middle");
    text.textContent = truncate(node.label, 22);
    g.append(text);

    // Hover → подсветка инцидентных рёбер
    const highlight = (on: boolean): void => {
      for (const [edge, line] of edgeEls) {
        if (edge.from === node.id || edge.to === node.id) {
          line.classList.toggle("edge-active", on);
        }
      }
      g.classList.toggle("gnode-active", on);
    };
    g.addEventListener("mouseenter", () => highlight(true));
    g.addEventListener("mouseleave", () => highlight(false));
    g.addEventListener("focus", () => highlight(true));
    g.addEventListener("blur", () => highlight(false));
    if (cb.onNodeClick) {
      g.addEventListener("click", () => cb.onNodeClick?.(node));
      g.addEventListener("keydown", (ev) => {
        if (ev.key === "Enter" || ev.key === " ") cb.onNodeClick?.(node);
      });
    }
    svg.append(g);
  }

  container.append(svg);
}

/** Радиальный layout по слоям (детерминированный). */
function layout(nodes: GraphNode[]): Positioned[] {
  const cx = WIDTH / 2;
  const cy = HEIGHT / 2;
  const radii = [0, 120, 200];

  const layers: GraphNode[][] = [[], [], []];
  for (const n of nodes) layers[layerOf(n.kind)]!.push(n);

  const out: Positioned[] = [];
  layers.forEach((layerNodes, layerIdx) => {
    const r = radii[layerIdx]!;
    const count = layerNodes.length;
    layerNodes.forEach((n, i) => {
      if (layerIdx === 0 && count === 1) {
        out.push({ ...n, x: cx, y: cy });
        return;
      }
      const angle = (2 * Math.PI * i) / Math.max(count, 1) - Math.PI / 2;
      out.push({
        ...n,
        x: cx + r * Math.cos(angle),
        y: cy + r * Math.sin(angle),
      });
    });
  });
  return out;
}

function truncate(s: string, max: number): string {
  return s.length > max ? `${s.slice(0, max - 1)}…` : s;
}
