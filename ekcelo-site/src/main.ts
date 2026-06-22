/**
 * SPA shell. Координирует api-adapter + UI-рендеры.
 *
 * Маршрутизация — простая через hash:
 *   #               → каталог
 *   #/objects/{cad} → объект (4 характеристики) + граф
 *   #/lots/{lot_id} → лот (4 характеристики) + members
 */

import { ApiClient, redirectToLogin } from "@adapters/api";
import type { CatalogCard } from "@core/viewmodel";
import { renderCatalog } from "@ui/catalog";
import { renderGraph } from "@ui/graph";
import { renderObjectCard } from "@ui/object-card";
import { clear, el } from "@ui/render-utils";

const api = new ApiClient({ onUnauthorized: redirectToLogin });

const app = document.querySelector<HTMLElement>("#app");
if (!app) throw new Error("missing #app root");

async function route(): Promise<void> {
  const hash = window.location.hash;
  if (hash.startsWith("#/objects/")) {
    const cad = decodeURIComponent(hash.slice("#/objects/".length));
    await showObject(cad);
  } else if (hash.startsWith("#/lots/")) {
    const lotId = decodeURIComponent(hash.slice("#/lots/".length));
    await showLot(lotId);
  } else {
    await showCatalog();
  }
}

async function showCatalog(): Promise<void> {
  if (!app) return;
  clear(app);
  app.append(headerNav());
  const status = el("p", { class: "status", text: "Загрузка…" });
  app.append(status);
  const filters = el("div", { class: "filters" });
  const searchInput = el("input", { class: "search" }) as HTMLInputElement;
  searchInput.placeholder = "Поиск по адресу/cad…";
  filters.append(searchInput);
  app.append(filters);
  const list = el("div", { class: "list" });
  app.append(list);

  const reload = async (): Promise<void> => {
    status.textContent = "Загрузка…";
    try {
      const cards = await api.getCatalog(
        searchInput.value ? { q: searchInput.value } : {},
      );
      status.textContent = `Найдено: ${cards.length}`;
      renderCatalog(list, cards, { onSelect: navigate });
    } catch (err) {
      status.textContent = `Ошибка: ${(err as Error).message}`;
    }
  };

  let debounce: number | undefined;
  searchInput.addEventListener("input", () => {
    window.clearTimeout(debounce);
    debounce = window.setTimeout(() => void reload(), 300);
  });

  await reload();
}

function navigate(card: CatalogCard): void {
  const slug = card.kind === "object" ? "objects" : "lots";
  window.location.hash = `#/${slug}/${encodeURIComponent(card.id)}`;
}

async function showObject(cad: string): Promise<void> {
  if (!app) return;
  clear(app);
  app.append(headerNav());
  const card = el("section", { class: "object" });
  const graphBox = el("section", { class: "graph" });
  app.append(card, graphBox);
  try {
    const [vm, graph] = await Promise.all([
      api.getObject(cad),
      api.getGraph(cad).catch(() => ({ nodes: [], edges: [] })),
    ]);
    renderObjectCard(card, vm);
    renderGraph(graphBox, graph);
  } catch (err) {
    card.textContent = `Ошибка: ${(err as Error).message}`;
  }
}

async function showLot(lotId: string): Promise<void> {
  if (!app) return;
  clear(app);
  app.append(headerNav());
  const card = el("section", { class: "object lot" });
  app.append(card);
  try {
    const vm = await api.getLot(lotId);
    renderObjectCard(card, vm);
  } catch (err) {
    card.textContent = `Ошибка: ${(err as Error).message}`;
  }
}

function headerNav(): HTMLElement {
  const nav = el("nav", { class: "nav" });
  const back = el("a", { href: "#", text: "← Каталог" });
  nav.append(back);
  const login = el("a", { href: "/auth/login", text: "Войти" });
  const logout = el("a", { href: "/auth/logout", text: "Выйти" });
  nav.append(login, logout);
  return nav;
}

window.addEventListener("hashchange", () => void route());
window.addEventListener("DOMContentLoaded", () => void route());
