/**
 * Утилиты безопасного рендера. UI-слой никогда не делает innerHTML с
 * данными — только textContent / createElement. Защита от XSS.
 */

export function el<K extends keyof HTMLElementTagNameMap>(
  tag: K,
  attrs: { class?: string; text?: string; href?: string; title?: string } = {},
  children: Array<Node | string> = [],
): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (attrs.class) node.className = attrs.class;
  if (attrs.text !== undefined) node.textContent = attrs.text;
  if (attrs.href && "href" in node) (node as HTMLAnchorElement).href = attrs.href;
  if (attrs.title) node.title = attrs.title;
  for (const child of children) {
    node.append(typeof child === "string" ? document.createTextNode(child) : child);
  }
  return node;
}

export function clear(node: Element): void {
  while (node.firstChild) node.removeChild(node.firstChild);
}

export function fmtArea(area: number | null | undefined): string {
  if (area === null || area === undefined) return "—";
  return `${area.toLocaleString("ru-RU", { maximumFractionDigits: 2 })} м²`;
}

export function fmtDate(iso: string | null | undefined): string {
  if (!iso) return "—";
  return iso.slice(0, 10);
}
