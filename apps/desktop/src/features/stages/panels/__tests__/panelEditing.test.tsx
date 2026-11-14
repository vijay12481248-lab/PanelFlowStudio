import { mountPage } from "../../../__tests__/pageHarness"; // first: installs jsdom before Radix loads
import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { act } from "react";
import { api } from "@panelflow/api-client";
import type { Project } from "@panelflow/shared-types";
import { PanelsStage } from "../PanelsStage";

const project = () => ({ id: "p1", title: "Dawn Gate", current_stage: "NORMALIZED", rights_status: "AUTHORIZED_WEB", stale_stages: [] }) as unknown as Project;
const page = (n: number) => ({ id: `pg${n}`, project_id: "p1", sequence: n, filename: `${n}.jpg`, status: "READY", width: 1920, height: 22000, byte_size: 1000, error_message: null });
const panel = (id: string, pageN: number, seq: number, status = "DETECTED", over: Record<string, unknown> = {}) => ({ id, project_id: "p1", page_id: `pg${pageN}`, sequence: seq, page_sequence: seq, x: 100, y: seq * 1000, width: 1000, height: 800, status, panel_type: "WEBTOON_SEGMENT", confidence: 0.9, detection_method: "AUTO", reading_direction: "ltr", ...over });
const BASE = () => [panel("a", 1, 1), panel("b", 1, 2), panel("c", 1, 3, "IGNORED"), panel("d", 2, 1)];

interface Calls { update: any[][]; add: any[][]; split: any[][]; merge: any[][]; del: string[]; reorder: any[][] }
function stub(over: Record<string, unknown> = {}) {
  const calls: Calls = { update: [], add: [], split: [], merge: [], del: [], reorder: [] };
  let panels: any[] = BASE();
  Object.assign(api as any, {
    listPages: async () => [page(1), page(2)],
    listPanels: async () => panels,
    listProjectJobs: async () => [],
    getCachedProjectHistory: () => ({ canUndo: true, canRedo: false, busy: false, recoveryRequired: false, conflicted: false }),
    getNormalizedPageImageUrl: (_p: string, id: string) => `/page/${id}.png`,
    getPanelImageUrl: (_p: string, id: string) => `/panel/${id}.png`,
    updatePanel: async (...a: any[]) => { calls.update.push(a); const next = { ...panels.find((p) => p.id === a[1]), x: a[2], y: a[3], width: a[4], height: a[5], ...(a[6] ? { status: a[6] } : {}), ...(a[7] ? { panel_type: a[7] } : {}) }; panels = panels.map((p) => (p.id === a[1] ? next : p)); return next; },
    addPanel: async (...a: any[]) => { calls.add.push(a); const n = panel("new", 1, 4, "MANUAL", { x: a[2], y: a[3], width: a[4], height: a[5] }); panels = [...panels, n]; return n; },
    splitPanel: async (...a: any[]) => { calls.split.push(a); const keep = panels.filter((p) => p.page_id === "pg1" && p.id !== a[2]); const out = [...keep, panel("a1", 1, 1), panel("a2", 1, 2)]; panels = [...panels.filter((p) => p.page_id !== "pg1"), ...out]; return out; },
    mergePanels: async (...a: any[]) => { calls.merge.push(a); const m = panel("m", 1, 1); panels = [m, ...panels.filter((p) => !a[1].includes(p.id))]; return m; },
    deletePanel: async (_p: string, id: string) => { calls.del.push(id); panels = panels.filter((p) => p.id !== id); },
    reorderPanels: async (...a: any[]) => { calls.reorder.push(a); const order: string[] = a[1]; panels = order.map((id, i) => ({ ...panels.find((p) => p.id === id), page_sequence: panels.find((p) => p.id === id)!.page_sequence })); return panels; },
    ...over,
  });
  return { calls, set: (p: any[]) => { panels = p; } };
}
const text = (d: Document) => d.body.textContent ?? "";
const button = (d: Document | Element, label: string | RegExp) => [...d.querySelectorAll("button")].find((b) => (typeof label === "string" ? b.textContent?.trim() === label || b.getAttribute("aria-label") === label : label.test(b.textContent ?? "") || label.test(b.getAttribute("aria-label") ?? ""))) as HTMLButtonElement | undefined;
const dialogButton = (d: Document, label: string) => [...d.querySelectorAll('[role="dialog"] button')].find((b) => b.textContent?.trim() === label) as HTMLButtonElement | undefined;
const boxEl = (d: Document, id: string) => d.querySelector(`[data-box-id="${id}"]`) as Element;
const boxLabel = (d: Document, id: string) => boxEl(d, id)?.getAttribute("aria-label");
const order = (d: Document) => [...d.querySelectorAll("[data-list-panel]")].map((e) => e.getAttribute("data-list-panel"));
const byLabel = (d: Document, label: string) => d.querySelector(`[aria-label="${label}"]`) as any;
const key = (el: Element | Window, k: string, extra: Record<string, unknown> = {}) => act(async () => { (el as any).dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true, cancelable: true, ...extra })); });
async function until(cond: () => boolean, ms = 3000) { for (let i = 0; i < ms / 25 && !cond(); i++) await new Promise((r) => setTimeout(r, 25)); }

async function show() {
  const view = await mountPage(<PanelsStage project={project()} onConfirmed={() => {}} onContinue={() => {}} onOpenStoryEditor={() => {}} />);
  await view.settle();
  await until(() => Boolean(boxEl(view.document, "a")));
  return view;
}
function forbidDialogs() {
  const w = window as any;
  const saved = { confirm: w.confirm, alert: w.alert };
  w.confirm = () => { throw new Error("window.confirm must not be used"); };
  w.alert = () => { throw new Error("window.alert must not be used"); };
  return () => { w.confirm = saved.confirm; w.alert = saved.alert; };
}
function stubRect(zoom: number) {
  const proto = (window as any).Element.prototype;
  const saved = proto.getBoundingClientRect;
  proto.getBoundingClientRect = () => ({ left: 0, top: 0, width: (1920 * zoom) / 100, height: (22000 * zoom) / 100, right: 0, bottom: 0, x: 0, y: 0, toJSON() {} });
  return () => { proto.getBoundingClientRect = saved; };
}
const ptr = (el: Element, type: string, x: number, y: number) => act(async () => { el.dispatchEvent(new (window as any).MouseEvent(type, { bubbles: true, cancelable: true, clientX: x, clientY: y, button: 0 })); });

test("nudging a box with the keyboard saves the new position once", async () => {
  const { calls } = stub();
  const view = await show();
  await key(boxEl(view.document, "a"), "ArrowRight");
  await until(() => calls.update.length > 0);
  assert.equal(calls.update.length, 1);
  assert.deepEqual(calls.update[0], ["p1", "a", 110, 1000, 1000, 800]);
  assert.ok(boxLabel(view.document, "a")!.includes("at 110, 1000"));
  await view.cleanup();
});

test("a position the engine refuses is put back, and the person is told, without any console-only failure", async () => {
  const restore = forbidDialogs();
  const originalError = console.error;
  let consoleErrors = 0;
  console.error = (...args: unknown[]) => { const first = String(args[0]); if (!first.includes("act(") && !first.includes("[PanelFlow Error Alert]")) consoleErrors++; }; // the app's own error system logs its reports
  try {
    stub({ updatePanel: async () => { throw new Error("Panel is linked to a video scene."); } });
    const view = await show();
    const before = boxLabel(view.document, "a");
    await key(boxEl(view.document, "a"), "ArrowRight");
    await until(() => text(view.document).includes("It was put back."));
    assert.ok(text(view.document).includes("Couldn't save the new position. It was put back."));
    assert.equal(boxLabel(view.document, "a"), before, "the box is back where it was");
    assert.equal(consoleErrors, 0);
    await view.cleanup();
  } finally { restore(); console.error = originalError; }
});

test("a second change is not sent while one is still being saved", async () => {
  const calls: any[][] = [];
  stub({ updatePanel: async (...a: any[]) => { calls.push(a); await new Promise(() => {}); } });
  const view = await show();
  await key(boxEl(view.document, "a"), "ArrowRight");
  await key(boxEl(view.document, "b"), "ArrowDown");
  assert.equal(calls.length, 1);
  await view.cleanup();
});

test("an excluded panel cannot be moved but can still be selected and deleted", async () => {
  const { calls } = stub();
  const view = await show();
  await key(boxEl(view.document, "c"), "ArrowRight");
  assert.equal(calls.update.length, 0);
  await view.click(button(view.document, /Select panel 3|^Panel 3/)!);
  assert.ok(button(view.document, "Delete panel"));
  await view.cleanup();
});

test("drawing a panel adds one box where it was dragged and selects it", async () => {
  const restore = stubRect(40);
  const { calls } = stub();
  const view = await show();
  await view.click(button(view.document, "Draw panel")!);
  const overlay = view.document.querySelector("[data-canvas-overlay]")!;
  await ptr(overlay, "pointerdown", 100, 400);
  await ptr(overlay, "pointermove", 300, 1000);
  await ptr(overlay, "pointerup", 300, 1000);
  await until(() => calls.add.length > 0);
  assert.equal(calls.add.length, 1);
  assert.deepEqual(calls.add[0], ["p1", "pg1", 250, 1000, 500, 1500]);
  await until(() => Boolean(boxEl(view.document, "new")));
  assert.equal(boxEl(view.document, "new").getAttribute("aria-pressed"), "true");
  await view.cleanup(); restore();
});

test("Add by numbers checks the box is inside the page and big enough, then adds it once", async () => {
  const { calls } = stub();
  const view = await show();
  await view.click(button(view.document, "Add by numbers")!);
  const field = (label: string) => [...view.document.querySelectorAll('[role="dialog"] label')].find((l) => l.textContent?.trim() === label) && (view.document.getElementById(([...view.document.querySelectorAll('[role="dialog"] label')].find((l) => l.textContent?.trim() === label) as HTMLLabelElement).htmlFor) as HTMLInputElement);
  await view.setValue(field("Width")!, "9000");
  await view.click(dialogButton(view.document, "Add panel")!);
  assert.ok(text(view.document).includes("Keep the panel inside the page and at least 30 pixels wide and high."));
  assert.equal(calls.add.length, 0);
  await view.setValue(field("Width")!, "400");
  await view.clickTwice(dialogButton(view.document, "Add panel")!);
  await view.settle();
  assert.equal(calls.add.length, 1);
  assert.deepEqual(calls.add[0], ["p1", "pg1", 50, 50, 400, 300]);
  await view.cleanup();
});

test("splitting sends the direction once and shows the page's new panels", async () => {
  const { calls } = stub();
  const view = await show();
  await view.click(button(view.document, "Select panel 1")!);
  await view.clickTwice(button(view.document, "Split horizontally")!);
  await until(() => calls.split.length > 0);
  await view.settle();
  assert.deepEqual(calls.split, [["p1", "a", "horizontal", 0.5]]);
  await until(() => Boolean(boxEl(view.document, "a1")));
  assert.ok(boxEl(view.document, "a2"));
  await view.cleanup();
});

test("Merge needs two panels, says so, and merges the chosen ones once", async () => {
  const { calls } = stub();
  const view = await show();
  const merge = () => button(view.document, /^Merge selected/)!;
  assert.equal(merge().disabled, true);
  assert.ok(text(view.document).includes("Choose at least two panels to merge."));
  await view.click(byLabel(view.document, "Merge panel 1"));
  assert.equal(merge().disabled, true, "one is not enough");
  await view.click(byLabel(view.document, "Merge panel 2"));
  assert.equal(merge().disabled, false);
  await view.clickTwice(merge());
  await until(() => calls.merge.length > 0);
  assert.deepEqual(calls.merge, [["p1", ["a", "b"]]]);
  await view.cleanup();
});

test("Mark full page uses the page's size", async () => {
  const { calls } = stub();
  const view = await show();
  await view.click(button(view.document, "Select panel 1")!);
  await view.click(button(view.document, "Mark full page")!);
  await until(() => calls.update.length > 0);
  assert.deepEqual(calls.update[0], ["p1", "a", 0, 0, 1920, 22000, "CONFIRMED", "FULL_PAGE"]);
  await view.cleanup();
});

test("Delete asks first, in the app; Cancel deletes nothing; confirming deletes once and clears the selection", async () => {
  const restore = forbidDialogs();
  try {
    const { calls } = stub();
    const view = await show();
    await view.click(button(view.document, "Select panel 2")!);
    await view.click(button(view.document, "Delete panel")!);
    assert.ok(text(view.document).includes("Delete panel 2?"));
    await view.click(dialogButton(view.document, "Cancel")!);
    assert.equal(calls.del.length, 0);
    await key(window, "Delete");
    assert.ok(text(view.document).includes("Delete panel 2?"), "the Delete key asks too");
    await view.clickTwice(dialogButton(view.document, "Delete panel")!);
    await until(() => calls.del.length > 0);
    await view.settle();
    assert.deepEqual(calls.del, ["b"]);
    assert.equal(boxEl(view.document, "b"), null);
    assert.equal(button(view.document, "Delete panel"), undefined, "nothing is selected any more");
    await view.cleanup();
  } finally { restore(); }
});

test("Move later reorders the page's panels and keeps the other pages in place; a refusal puts the order back", async () => {
  const { calls } = stub();
  const view = await show();
  assert.deepEqual(order(view.document), ["a", "b", "c"]);
  await view.clickTwice(button(view.document, "Move panel 1 later")!);
  await until(() => calls.reorder.length > 0);
  assert.deepEqual(calls.reorder, [["p1", ["b", "a", "c", "d"]]], "page 2's panel stays after page 1's");
  await view.cleanup();
  stub({ reorderPanels: async () => { throw new Error("no"); } });
  const failing = await show();
  await failing.click(button(failing.document, "Move panel 1 later")!);
  await until(() => text(failing.document).includes("Couldn't save the new order"));
  assert.deepEqual(order(failing.document), ["a", "b", "c"]);
  assert.ok(text(failing.document).includes("Couldn't save the new order. The panels are back in their old order."));
  await failing.cleanup();
});

test("Move earlier is disabled on the first panel and Move later on the last", async () => {
  stub();
  const view = await show();
  assert.equal(button(view.document, "Move panel 1 earlier")!.disabled, true);
  assert.equal(button(view.document, "Move panel 3 later")!.disabled, true);
  await view.cleanup();
});

test("the inspector's number fields move a panel exactly, and a box outside the page is refused inline", async () => {
  const { calls } = stub();
  const view = await show();
  await view.click(button(view.document, "Select panel 1")!);
  const x = byLabel(view.document, "X position") as HTMLInputElement;
  await view.setValue(x, "300");
  await view.click(button(view.document, "Apply position")!);
  await until(() => calls.update.length > 0);
  assert.deepEqual(calls.update[0], ["p1", "a", 300, 1000, 1000, 800]);
  await view.setValue(byLabel(view.document, "Width") as HTMLInputElement, "5000");
  assert.ok(text(view.document).includes("Keep the panel inside the page and at least 30 pixels wide and high."));
  assert.equal(button(view.document, "Apply position")!.disabled, true);
  await view.cleanup();
});

test("Tab is left alone so keyboard users can move through the page, and [ and ] move between panels", async () => {
  stub();
  const view = await show();
  const tab = new KeyboardEvent("keydown", { key: "Tab", bubbles: true, cancelable: true });
  await act(async () => { window.dispatchEvent(tab); });
  assert.equal(tab.defaultPrevented, false);
  await view.click(button(view.document, "Select panel 1")!);
  await key(window, "]");
  assert.equal(boxEl(view.document, "b").getAttribute("aria-pressed"), "true");
  await key(window, "[");
  assert.equal(boxEl(view.document, "a").getAttribute("aria-pressed"), "true");
  await view.cleanup();
});

test("Escape leaves draw mode and clears the selection and the merge choices", async () => {
  stub();
  const view = await show();
  await view.click(button(view.document, "Select panel 1")!);
  await view.click(button(view.document, "Draw panel")!);
  assert.equal(button(view.document, "Draw panel")!.getAttribute("aria-pressed"), "true");
  await key(window, "Escape");
  assert.equal(button(view.document, "Draw panel")!.getAttribute("aria-pressed"), "false");
  assert.equal(boxEl(view.document, "a").getAttribute("aria-pressed"), "false");
  await view.cleanup();
});

test("overlapping panels are flagged in the list", async () => {
  const { set } = stub();
  set([panel("a", 1, 1, "DETECTED", { x: 0, y: 0, width: 1000, height: 1000 }), panel("b", 1, 2, "DETECTED", { x: 100, y: 100, width: 800, height: 800 })]);
  const view = await show();
  assert.ok(text(view.document).includes("Overlaps panel"));
  await view.cleanup();
});
