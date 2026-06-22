/**
 * UI рендер карточки объекта/лота — 4 канонические характеристики.
 * Принимает ViewModel независимо от источника (api или kmz).
 */
import type { ViewModel } from "@core/viewmodel";
import { clear, el, fmtArea, fmtDate } from "@ui/render-utils";

export function renderObjectCard(
  container: HTMLElement,
  vm: ViewModel,
): void {
  clear(container);

  const head = el("header", { class: "obj-head" });
  head.append(el("span", { class: "obj-kind", text: vm.kind }));
  head.append(el("h1", { class: "obj-id", text: vm.id }));
  container.append(head);

  container.append(renderPhysical(vm));
  container.append(renderOwnership(vm));
  container.append(renderGeo(vm));
  container.append(renderTemporal(vm));

  if (vm.kind === "lot" && vm.members && vm.members.length > 0) {
    container.append(renderMembers(vm.members));
  }
}

function renderPhysical(vm: ViewModel): HTMLElement {
  const sec = el("section", { class: "char char-physical" });
  sec.append(el("h2", { text: "ЧТО ЭТО" }));
  const dl = el("dl");
  appendDt(dl, "Тип", vm.physical.object_type);
  appendDt(dl, "Адрес", vm.physical.address);
  appendDt(dl, "Площадь", fmtArea(vm.physical.area_m2));
  if (vm.physical.floors !== null && vm.physical.floors !== undefined) {
    appendDt(dl, "Этажность", String(vm.physical.floors));
  }
  if (vm.physical.etp) {
    const etpSrc = String(vm.physical.etp.source ?? "");
    const conf = vm.physical.etp.confidence;
    appendDt(
      dl,
      "ЭТП-профиль",
      `источник: ${etpSrc}; confidence: ${typeof conf === "number" ? conf.toFixed(2) : "—"}`,
    );
  }
  sec.append(dl);
  return sec;
}

function renderOwnership(vm: ViewModel): HTMLElement {
  const sec = el("section", { class: "char char-ownership" });
  sec.append(el("h2", { text: "ЧЬЁ ЭТО" }));
  if (vm.ownership.rights.length === 0) {
    sec.append(el("p", { class: "empty", text: "Нет данных о правах" }));
    return sec;
  }
  const list = el("ul", { class: "rights" });
  for (const r of vm.ownership.rights) {
    const li = el("li");
    li.append(el("strong", { text: r.right_type }));
    if (r.share) li.append(el("span", { text: ` (доля ${r.share})` }));
    if (r.right_holder_inn) {
      const b = vm.ownership.beneficiaries.find((x) => x.inn === r.right_holder_inn);
      const label = b?.name_short ?? b?.name_full ?? `ИНН ${r.right_holder_inn}`;
      li.append(el("span", { text: ` — ${label}` }));
    }
    if (r.registration_date) {
      li.append(
        el("span", {
          class: "right-date",
          text: ` (рег. ${fmtDate(r.registration_date)})`,
        }),
      );
    }
    list.append(li);
  }
  sec.append(list);
  return sec;
}

function renderGeo(vm: ViewModel): HTMLElement {
  const sec = el("section", { class: "char char-geo" });
  sec.append(el("h2", { text: "ГДЕ ЭТО" }));
  if (vm.geo.center) {
    const [lon, lat] = vm.geo.center;
    appendDt(sec, "Центр", `${lat.toFixed(6)}, ${lon.toFixed(6)}`);
  } else {
    sec.append(el("p", { class: "muted", text: "Геометрия пока не материализована (C3.3 план)" }));
  }
  return sec;
}

function renderTemporal(vm: ViewModel): HTMLElement {
  const sec = el("section", { class: "char char-temporal" });
  sec.append(el("h2", { text: "КОГДА ЭТО" }));
  const dl = el("dl");
  appendDt(dl, "Дата выписки", fmtDate(vm.temporal.extract_date));
  appendDt(dl, "На дату (as_of)", fmtDate(vm.temporal.as_of_date));
  sec.append(dl);
  return sec;
}

function renderMembers(members: string[]): HTMLElement {
  const sec = el("section", { class: "char char-members" });
  sec.append(el("h2", { text: "ЧЛЕНЫ ЛОТА" }));
  const ul = el("ul", { class: "members" });
  for (const cad of members) {
    ul.append(el("li", { text: cad }));
  }
  sec.append(ul);
  return sec;
}

function appendDt(
  parent: HTMLElement,
  label: string,
  value: string | null | undefined,
): void {
  const dt = el("dt", { text: label });
  const dd = el("dd", { text: value ?? "—" });
  parent.append(dt, dd);
}
