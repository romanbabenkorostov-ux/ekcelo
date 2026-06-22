/**
 * SPA shell. Координирует два адаптера (api + kmz) → общую ViewModel → UI.
 *
 * Маршрутизация — простая через hash:
 *   #               → каталог (api) + KMZ-drop (offline)
 *   #/objects/{cad} → объект (4 характеристики) + граф + карта
 *   #/lots/{lot_id} → лот (4 характеристики) + members
 *   #/grants        → управление грантами (C6 RBAC)
 *
 * FE-2: kmz→ViewModel офлайн-режим (объект из KMZ = тот же UI).
 * FE-3: карта (Leaflet) geo.geometry + UI грантов.
 */

import { ApiClient, redirectToLogin } from "@adapters/api";
import {
  kmzToViewModel,
  parseKmzFile,
  type KmzDocument,
} from "@adapters/kmz";
import type { CatalogCard, GrantCreate, ViewModel } from "@core/viewmodel";
import { renderCatalog } from "@ui/catalog";
import { renderGrants } from "@ui/grants";
import { renderGraphSvg } from "@ui/graph-svg";
import { renderMap } from "@ui/map";
import { renderObjectCard } from "@ui/object-card";
import { clear, el } from "@ui/render-utils";

const api = new ApiClient({ onUnauthorized: redirectToLogin });

const app = document.querySelector<HTMLElement>("#app");
if (!app) throw new Error("missing #app root");

// Офлайн-KMZ держим в памяти — при загрузке файла показываем его объекты.
let offlineKmz: KmzDocument | null = null;

async function route(): Promise<void> {
  const hash = window.location.hash;
  if (hash.startsWith("#/objects/")) {
    const cad = decodeURIComponent(hash.slice("#/objects/".length));
    await showObject(cad);
  } else if (hash.startsWith("#/lots/")) {
    const lotId = decodeURIComponent(hash.slice("#/lots/".length));
    await showLot(lotId);
  } else if (hash === "#/grants") {
    await showGrants();
  } else {
    await showCatalog();
  }
}

async function showCatalog(): Promise<void> {
  if (!app) return;
  clear(app);
  app.append(headerNav());
  app.append(modeBar());

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

  // Если объект есть в загруженном KMZ — берём из него (офлайн-режим),
  // иначе из api. Источник помечается бейджем.
  const fromKmz = offlineKmz?.placemarks.some(
    (p) => p.cadNumber === cad && p.objectType !== "photo",
  );

  const sourceBadge = el("div", { class: "mode-label" });
  app.append(sourceBadge);
  const card = el("section", { class: "object" });
  const mapBox = el("section", { class: "map-box" });
  const graphBox = el("section", { class: "graph" });
  app.append(card, mapBox, graphBox);

  try {
    let vm: ViewModel;
    let graph: ViewModel["ownership"]["graph"];
    if (fromKmz && offlineKmz) {
      vm = kmzToViewModel(offlineKmz, cad);
      graph = vm.ownership.graph ?? { nodes: [], edges: [] };
      sourceBadge.append(el("span", { class: "badge-source kmz", text: "источник: KMZ (офлайн)" }));
    } else {
      const [apiVm, apiGraph] = await Promise.all([
        api.getObject(cad),
        api.getGraph(cad).catch(() => ({ nodes: [], edges: [] })),
      ]);
      vm = apiVm;
      graph = apiGraph;
      sourceBadge.append(el("span", { class: "badge-source", text: "источник: API (ViewModel REST)" }));
    }
    renderObjectCard(card, vm);
    // FE-3: карта geo.geometry (Leaflet). Async — не блокирует остальной рендер.
    void renderMap(mapBox, vm.geo);
    renderGraphSvg(graphBox, graph ?? { nodes: [], edges: [] }, {
      onNodeClick: (node) => {
        // Клик на object-узел графа → навигация (если cad-подобный id)
        if (/^\d+:\d+:\d+:\d+$/.test(node.id)) {
          window.location.hash = `#/objects/${encodeURIComponent(node.id)}`;
        }
      },
    });
  } catch (err) {
    card.textContent = `Ошибка: ${(err as Error).message}`;
  }
}

async function showGrants(): Promise<void> {
  if (!app) return;
  clear(app);
  app.append(headerNav());
  const box = el("section", { class: "grants" });
  app.append(box);

  const reload = async (): Promise<void> => {
    try {
      const grants = await api.getMyGrants();
      renderGrants(box, grants, {
        onCreate: async (body: GrantCreate) => {
          try {
            await api.createGrant(body);
            await reload();
          } catch (err) {
            alert(`Не удалось выдать грант: ${(err as Error).message}`);
          }
        },
        onRevoke: async (grantId: string) => {
          try {
            await api.revokeGrant(grantId);
            await reload();
          } catch (err) {
            alert(`Не удалось отозвать: ${(err as Error).message}`);
          }
        },
      });
    } catch (err) {
      box.textContent = `Ошибка загрузки грантов: ${(err as Error).message}`;
    }
  };
  await reload();
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
  nav.append(el("a", { href: "#", text: "← Каталог" }));
  nav.append(el("a", { href: "#/grants", text: "Гранты" }));
  nav.append(el("a", { href: "/auth/login", text: "Войти" }));
  nav.append(el("a", { href: "/auth/logout", text: "Выйти" }));
  return nav;
}

/** Панель режима: drag-drop KMZ для офлайн-просмотра. */
function modeBar(): HTMLElement {
  const bar = el("div", { class: "mode-bar" });
  bar.append(el("span", { class: "mode-label", text: "Режим: API (онлайн)" }));

  const drop = el("label", {
    class: "kmz-drop",
    text: offlineKmz
      ? `KMZ загружен: ${offlineKmz.placemarks.length} placemark'ов`
      : "Перетащите .kmz сюда или кликните (офлайн-просмотр)",
  });
  const input = el("input") as HTMLInputElement;
  input.type = "file";
  input.accept = ".kmz";
  input.style.display = "none";
  drop.append(input);

  const loadFile = async (file: File): Promise<void> => {
    try {
      offlineKmz = await parseKmzFile(file);
      drop.firstChild!.textContent = `KMZ загружен: ${offlineKmz.placemarks.length} placemark'ов. Откройте объект по cad.`;
    } catch (err) {
      drop.firstChild!.textContent = `Ошибка KMZ: ${(err as Error).message}`;
    }
  };

  input.addEventListener("change", () => {
    const f = input.files?.[0];
    if (f) void loadFile(f);
  });
  drop.addEventListener("dragover", (ev) => {
    ev.preventDefault();
    drop.classList.add("dragover");
  });
  drop.addEventListener("dragleave", () => drop.classList.remove("dragover"));
  drop.addEventListener("drop", (ev) => {
    ev.preventDefault();
    drop.classList.remove("dragover");
    const f = ev.dataTransfer?.files?.[0];
    if (f) void loadFile(f);
  });

  bar.append(drop);
  return bar;
}

window.addEventListener("hashchange", () => void route());
window.addEventListener("DOMContentLoaded", () => void route());
