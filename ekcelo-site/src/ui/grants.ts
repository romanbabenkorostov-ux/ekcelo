/**
 * UI управления грантами (C6 RBAC). Список «мои гранты» + форма выдачи +
 * кнопка отзыва. Не знает про HTTP — принимает данные и колбэки.
 *
 * Семантика по C6:
 *   assessor → delegate (передача action другому assessor)
 *   client   → share (view-only третьему лицу)
 * Backend POST /grants сам диспетчеризует по роли — UI просто отправляет.
 */
import type { Grant, GrantCreate } from "@core/viewmodel";
import { clear, el, fmtDate } from "@ui/render-utils";

export interface GrantsCallbacks {
  onCreate: (body: GrantCreate) => void;
  onRevoke: (grantId: string) => void;
}

export function renderGrants(
  container: HTMLElement,
  grants: Grant[],
  cb: GrantsCallbacks,
): void {
  clear(container);
  container.append(el("h2", { text: "Мои гранты доступа" }));

  // Список грантов
  if (grants.length === 0) {
    container.append(el("p", { class: "empty", text: "Грантов нет" }));
  } else {
    const table = el("table", { class: "grants-table" });
    const thead = el("tr");
    for (const h of ["Действие", "Ресурс", "Кем выдан", "До", ""]) {
      thead.append(el("th", { text: h }));
    }
    table.append(thead);
    for (const g of grants) {
      const tr = el("tr");
      tr.append(el("td", { text: g.action }));
      tr.append(el("td", { text: `${g.resource_type}/${g.resource_id}` }));
      tr.append(el("td", { text: g.granted_by }));
      tr.append(el("td", { text: g.expires_at ? fmtDate(g.expires_at) : "∞" }));
      const actionTd = el("td");
      if (g.revocable) {
        const btn = el("button", { class: "btn-revoke", text: "Отозвать" });
        btn.addEventListener("click", () => cb.onRevoke(g.grant_id));
        actionTd.append(btn);
      } else {
        actionTd.append(el("span", { class: "muted", text: "—" }));
      }
      tr.append(actionTd);
      table.append(tr);
    }
    container.append(table);
  }

  // Форма выдачи гранта
  container.append(buildGrantForm(cb));
}

function buildGrantForm(cb: GrantsCallbacks): HTMLElement {
  const form = el("form", { class: "grant-form" });
  form.append(el("h3", { text: "Выдать доступ" }));

  const subInput = inputField("subject_sub", "Кому (sub/username)");
  const ridInput = inputField("resource_id", "Ресурс ID (cad/lot_id/bundle_id)");

  const actionSel = selectField("action", [
    "view", "edit", "export", "input", "delegate", "share",
  ]);
  const typeSel = selectField("resource_type", ["object", "lot", "bundle"]);

  const submit = el("button", { class: "btn-grant", text: "Выдать" });
  submit.setAttribute("type", "submit");

  form.append(subInput.wrap, actionSel.wrap, typeSel.wrap, ridInput.wrap, submit);

  form.addEventListener("submit", (ev) => {
    ev.preventDefault();
    const subject_sub = subInput.input.value.trim();
    const resource_id = ridInput.input.value.trim();
    if (!subject_sub || !resource_id) return;
    cb.onCreate({
      subject_sub,
      action: actionSel.select.value as GrantCreate["action"],
      resource_type: typeSel.select.value as GrantCreate["resource_type"],
      resource_id,
    });
    subInput.input.value = "";
    ridInput.input.value = "";
  });

  return form;
}

function inputField(name: string, placeholder: string): { wrap: HTMLElement; input: HTMLInputElement } {
  const wrap = el("label", { class: "field" });
  wrap.append(el("span", { text: placeholder }));
  const input = el("input") as HTMLInputElement;
  input.name = name;
  input.placeholder = placeholder;
  wrap.append(input);
  return { wrap, input };
}

function selectField(name: string, options: string[]): { wrap: HTMLElement; select: HTMLSelectElement } {
  const wrap = el("label", { class: "field" });
  wrap.append(el("span", { text: name }));
  const select = el("select") as HTMLSelectElement;
  select.name = name;
  for (const opt of options) {
    const o = el("option", { text: opt });
    (o as HTMLOptionElement).value = opt;
    select.append(o);
  }
  wrap.append(select);
  return { wrap, select };
}
