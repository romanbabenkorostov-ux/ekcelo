/**
 * UI грантов — структура таблицы + форма + колбэки.
 */
import { describe, expect, it, vi } from "vitest";

import type { Grant } from "../src/core/viewmodel";
import { renderGrants } from "../src/ui/grants";

function container(): HTMLElement {
  const div = document.createElement("div");
  document.body.append(div);
  return div;
}

function sampleGrants(): Grant[] {
  return [
    {
      grant_id: "g1",
      subject_sub: "alice",
      action: "view",
      resource_type: "object",
      resource_id: "61:44:0050706:31",
      granted_by: "root",
      revocable: true,
      expires_at: null,
    },
    {
      grant_id: "g2",
      subject_sub: "alice",
      action: "edit",
      resource_type: "lot",
      resource_id: "lot-001",
      granted_by: "root",
      revocable: false,
      expires_at: "2026-12-31",
    },
  ];
}

describe("renderGrants", () => {
  it("пустой список → сообщение + форма", () => {
    const c = container();
    renderGrants(c, [], { onCreate: () => {}, onRevoke: () => {} });
    expect(c.querySelector(".empty")).toBeTruthy();
    expect(c.querySelector(".grant-form")).toBeTruthy();
  });

  it("рисует таблицу грантов", () => {
    const c = container();
    renderGrants(c, sampleGrants(), { onCreate: () => {}, onRevoke: () => {} });
    const rows = c.querySelectorAll(".grants-table tr");
    // header + 2 гранта
    expect(rows).toHaveLength(3);
    expect(c.textContent).toContain("61:44:0050706:31");
    expect(c.textContent).toContain("lot-001");
  });

  it("revocable грант → кнопка Отозвать; non-revocable → нет", () => {
    const c = container();
    renderGrants(c, sampleGrants(), { onCreate: () => {}, onRevoke: () => {} });
    const buttons = c.querySelectorAll(".btn-revoke");
    expect(buttons).toHaveLength(1); // только g1 revocable
  });

  it("клик Отозвать вызывает onRevoke с grant_id", () => {
    const c = container();
    const onRevoke = vi.fn();
    renderGrants(c, sampleGrants(), { onCreate: () => {}, onRevoke });
    c.querySelector<HTMLButtonElement>(".btn-revoke")?.click();
    expect(onRevoke).toHaveBeenCalledWith("g1");
  });

  it("expires_at: дата vs ∞", () => {
    const c = container();
    renderGrants(c, sampleGrants(), { onCreate: () => {}, onRevoke: () => {} });
    expect(c.textContent).toContain("∞"); // g1 null
    expect(c.textContent).toContain("2026-12-31"); // g2
  });

  it("submit формы вызывает onCreate с собранным body", () => {
    const c = container();
    const onCreate = vi.fn();
    renderGrants(c, [], { onCreate, onRevoke: () => {} });
    const form = c.querySelector<HTMLFormElement>(".grant-form")!;
    (form.querySelector('input[name="subject_sub"]') as HTMLInputElement).value = "bob";
    (form.querySelector('input[name="resource_id"]') as HTMLInputElement).value = "61:44:0050706:99";
    (form.querySelector('select[name="action"]') as HTMLSelectElement).value = "view";
    (form.querySelector('select[name="resource_type"]') as HTMLSelectElement).value = "object";
    form.dispatchEvent(new Event("submit"));
    expect(onCreate).toHaveBeenCalledWith({
      subject_sub: "bob",
      action: "view",
      resource_type: "object",
      resource_id: "61:44:0050706:99",
    });
  });

  it("submit с пустыми полями НЕ вызывает onCreate", () => {
    const c = container();
    const onCreate = vi.fn();
    renderGrants(c, [], { onCreate, onRevoke: () => {} });
    const form = c.querySelector<HTMLFormElement>(".grant-form")!;
    form.dispatchEvent(new Event("submit"));
    expect(onCreate).not.toHaveBeenCalled();
  });
});
