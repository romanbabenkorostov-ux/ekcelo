/**
 * UI рендер каталога. Не знает откуда данные (контракт ViewModel).
 */
import type { CatalogCard } from "@core/viewmodel";
import { clear, el, fmtDate } from "@ui/render-utils";

export interface CatalogCallbacks {
  onSelect: (card: CatalogCard) => void;
}

export function renderCatalog(
  container: HTMLElement,
  cards: CatalogCard[],
  cb: CatalogCallbacks,
): void {
  clear(container);
  if (cards.length === 0) {
    container.append(el("p", { class: "empty", text: "Каталог пуст" }));
    return;
  }
  const list = el("ul", { class: "catalog-list" });
  for (const card of cards) {
    const item = el("li", { class: `catalog-item catalog-${card.kind}` });
    const title = el("button", { class: "catalog-title", text: card.title });
    title.addEventListener("click", () => cb.onSelect(card));
    item.append(title);
    item.append(el("span", { class: "catalog-kind", text: card.kind }));
    if (card.address) {
      item.append(el("p", { class: "catalog-address", text: card.address }));
    }
    if (card.extract_date) {
      item.append(
        el("span", {
          class: "catalog-date",
          text: `выписка: ${fmtDate(card.extract_date)}`,
        }),
      );
    }
    list.append(item);
  }
  container.append(list);
}
