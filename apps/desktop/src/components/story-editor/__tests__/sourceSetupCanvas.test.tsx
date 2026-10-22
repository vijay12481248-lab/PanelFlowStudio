import React, { act } from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
import { api } from "@panelflow/api-client";
import { SourceSetupCanvas } from "../SourceSetupCanvas";
import { splitSelector, transformSelector, validPolygon } from "../selectorGeometry";
import type { Handle, Selector } from "../selectorGeometry";
import type { Page, Panel } from "@panelflow/shared-types";
const { JSDOM } = createRequire(import.meta.url)("jsdom");
const page = { id: "page-a", sequence: 1, width: 800, height: 1200 } as Page;
const panel = { id: "panel-a", page_id: page.id, page_sequence: 1, x: 20, y: 30, width: 200, height: 300, crop_filename: "original.png" } as Panel;

async function mount(options: { initialView?: "pages" | "panels" | "both"; empty?: boolean; extraPanels?: boolean } = {}) {
  const dom = new JSDOM("<!doctype html><div id='root'></div>", { url: "http://localhost/", pretendToBeVisual: true });
  const keys = ["window", "document", "navigator", "HTMLElement", "HTMLInputElement", "SVGElement", "IS_REACT_ACT_ENVIRONMENT"];
  const previous = new Map(keys.map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  for (const key of keys) Object.defineProperty(globalThis, key, { configurable: true, writable: true, value: key === "IS_REACT_ACT_ENVIRONMENT" ? true : dom.window[key] });
  const { createRoot } = await import("react-dom/client");
  const container = dom.window.document.getElementById("root")!;
  const root = createRoot(container);
  const originalSave = api.savePanelSelections, originalDelete = api.deletePanel, originalDetect = api.detectPagePanels, originalList = api.listPanels, originalCreate = api.addPageSelections;
  const calls: unknown[][] = [], deleted: string[] = [];
  let fail = false, latest: Panel[] = [];
  const detectionCalls: unknown[][] = [];
  api.detectPagePanels = async (...args) => { detectionCalls.push(args); if (fail) throw new Error("Detection unavailable"); return [panel]; };
  api.listPanels = async () => [panel];
  api.addPageSelections = async (...args) => { calls.push(args); return args[2].map((s, i) => ({ ...panel, ...s, id: `created-${i}`, crop_filename: `created-${i}.png` })); };
  api.savePanelSelections = async (...args) => {
    calls.push(args);
    if (fail) throw new Error("Save unavailable");
    return args[2].map((s, i) => ({ ...panel, ...s, id: i ? `new-${i}` : panel.id, page_sequence: i + 1, crop_filename: `saved-${i}.png`, polygon_json: s.points ? JSON.stringify(s.points) : null }));
  };
  api.deletePanel = async (_project, id) => { deleted.push(id); };
  function Host() {
    const [panels, setPanels] = React.useState(options.empty ? [] : options.extraPanels ? [panel, { ...panel, id: "panel-b", page_sequence: 2, x: 300 }] : [panel]);
    const [selected, setSelected] = React.useState(panel.id);
    const [selectedPage, setSelectedPage] = React.useState(page.id);
    const drafts = React.useRef({});
    const pages = [page, { ...page, id: "page-b", sequence: 2 }];
    return <SourceSetupCanvas projectId="project" page={pages.find(p => p.id === selectedPage)!} pages={pages} onSelectPage={setSelectedPage}
      drafts={drafts} initialView={options.initialView || "panels"} panels={panels} selectedPanelId={selected}
      onSelectPanel={p => setSelected(p.id)} onPanelSaved={() => {}}
      onPanelsChanged={all => { latest = all; setPanels(all); }} onAddPanel={() => {}} />;
  }
  await act(async () => root.render(<Host />));
  const button = (name: string) => {
    const found = Array.from(container.querySelectorAll("button")).find((e: any) => e.textContent?.trim() === name || e.getAttribute("aria-label") === name);
    assert.ok(found, `Expected button ${name}`); return found as HTMLButtonElement;
  };
  const click = async (name: string) => { await act(async () => button(name).click()); };
  const pointer = async (type: string, x: number, y: number, target?: Element | null) => {
    const svg = container.querySelector('[aria-label="Panel selector editor"]') || container.querySelector('[aria-label="Page selector editor"]')!;
    (svg as any).getBoundingClientRect = () => ({ left: 0, top: 0, width: 400, height: 600 });
    const event = new dom.window.MouseEvent(type, { clientX: x, clientY: y, button: 0, bubbles: true });
    Object.defineProperty(event, "pointerId", { value: 1 });
    await act(async () => (target || svg).dispatchEvent(event));
  };
  const tab = async (name: string) => { const node = container.querySelector(`[role="tab"][id="setup-tab-${name.toLowerCase()}"]`); assert.ok(node); await act(async () => (node as HTMLButtonElement).click()); };
  return { container, calls, deleted, detectionCalls, click, tab, pointer, button, latest: () => latest, fail: (value: boolean) => { fail = value; },
    async close() {
      await act(async () => root.unmount()); api.savePanelSelections = originalSave; api.deletePanel = originalDelete;
      api.detectPagePanels = originalDetect; api.listPanels = originalList; api.addPageSelections = originalCreate;
      dom.window.close(); for (const [key, descriptor] of previous) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete (globalThis as any)[key]; }
    } };
}

test("Setup crops contain only detected panels and expose editing tools and all nine handles", async () => {
  const editor = await mount();
  try {
    assert.equal(editor.container.querySelectorAll('[aria-label="Detected panel crops"] img').length, 1);
    assert.equal(editor.container.querySelector('img[alt="Setup page 1"]'), null);
    for (const name of ["Select", "Rectangle", "Polygon", "Pen"]) assert.ok(editor.button(name));
    for (const handle of ["nw", "n", "ne", "e", "se", "s", "sw", "w", "center"]) assert.ok(editor.container.querySelector(`[aria-label="Selector ${handle} handle"]`));
    assert.equal(editor.container.querySelector('[aria-label="Panel selector editor"]')?.getAttribute("viewBox"), "20 30 200 300");
  } finally { await editor.close(); }
});

test("pointer corner resize saves exact source coordinates; failure keeps draft and retry persists it", async () => {
  const editor = await mount();
  try {
    await editor.pointer("pointerdown", 0, 0, editor.container.querySelector('[aria-label="Selector nw handle"]'));
    await editor.pointer("pointermove", 40, 60); await editor.pointer("pointerup", 40, 60);
    editor.fail(true); await editor.click("Save selectors");
    assert.deepEqual(editor.calls[0], ["project", "panel-a", [{ x: 40, y: 60, width: 180, height: 270, points: undefined }]]);
    assert.match(editor.container.textContent!, /Save unavailable/);
    assert.equal(editor.latest().length, 0);
    editor.fail(false); await editor.click("Save selectors");
    assert.equal(editor.latest()[0].width, 180);
    assert.equal(editor.container.querySelector('[aria-label="Panel selector editor"]')?.getAttribute("viewBox"), "40 60 180 270");
  } finally { await editor.close(); }
});

test("selector draft undo and redo restore real split geometry and invalidate redo after a new edit", async () => {
  const editor = await mount();
  try {
    await editor.click("Split vertically");
    assert.equal(editor.container.querySelectorAll('[aria-label="Active selector"] option').length, 2);
    await editor.click("Undo");
    assert.equal(editor.container.querySelectorAll('[aria-label="Active selector"] option').length, 1);
    await editor.click("Redo");
    assert.equal(editor.container.querySelectorAll('[aria-label="Active selector"] option').length, 2);
    await editor.click("Undo"); await editor.click("Split horizontally");
    assert.equal(editor.button("Redo").disabled, true);
    await editor.click("Save selectors");
    assert.deepEqual(editor.latest().map(p => [p.y, p.height]), [[30, 150], [180, 150]]);
  } finally { await editor.close(); }
});

test("one completed resize gesture is one reversible draft action", async () => {
  const editor = await mount();
  try {
    await editor.pointer("pointerdown", 0, 0, editor.container.querySelector('[aria-label="Selector nw handle"]'));
    await editor.pointer("pointermove", 20, 30); await editor.pointer("pointermove", 40, 60); await editor.pointer("pointerup", 40, 60);
    await editor.click("Undo"); assert.equal(editor.button("Undo").disabled, true);
    await editor.click("Redo"); await editor.click("Save selectors");
    assert.deepEqual(editor.latest().map(p => [p.x, p.y, p.width, p.height]), [[40, 60, 180, 270]]);
  } finally { await editor.close(); }
});

test("focused Setup shortcuts use draft history without reaching a parent editor", async () => {
  const editor = await mount();
  const win = editor.container.ownerDocument.defaultView!;
  let parentUndo = 0;
  const parent = () => { parentUndo++; };
  win.addEventListener("keydown", parent);
  try {
    await editor.click("Split vertically");
    const surface = editor.container.querySelector('[aria-label="Current panel crop"]')!;
    await act(async () => surface.dispatchEvent(new win.KeyboardEvent("keydown", { key: "z", ctrlKey: true, bubbles: true, cancelable: true })));
    assert.equal(editor.container.querySelectorAll('[aria-label="Active selector"] option').length, 1);
    assert.equal(parentUndo, 0);
    await act(async () => surface.dispatchEvent(new win.KeyboardEvent("keydown", { key: "z", ctrlKey: true, shiftKey: true, bubbles: true, cancelable: true })));
    assert.equal(editor.container.querySelectorAll('[aria-label="Active selector"] option').length, 2);
    assert.equal(parentUndo, 0);
  } finally { win.removeEventListener("keydown", parent); await editor.close(); }
});

test("split creates exact adjacent persisted panel records; delete is explicit and persists", async () => {
  const editor = await mount();
  try {
    await editor.click("Split vertically");
    assert.equal(editor.container.querySelectorAll('[aria-label="Active selector"] option').length, 2);
    await editor.click("Save selectors");
    assert.deepEqual(editor.latest().map(p => [p.x, p.width]), [[20, 100], [120, 100]]);
    await editor.click("Delete panel"); assert.equal(editor.deleted.length, 0);
    await editor.click("Confirm delete panel"); assert.deepEqual(editor.deleted, [panel.id]);
    assert.equal(editor.latest().length, 1);
  } finally { await editor.close(); }
});

test("Rectangle creates a real selector; cancelled gestures restore the prior geometry", async () => {
  const editor = await mount();
  try {
    await editor.click("Rectangle"); await editor.pointer("pointerdown", 40, 60);
    await editor.pointer("pointermove", 200, 300); await editor.pointer("pointerup", 200, 300);
    assert.equal(editor.container.querySelectorAll('[aria-label="Active selector"] option').length, 2);
    await editor.pointer("pointerdown", 200, 300, editor.container.querySelector('[aria-label="Selector center handle"]'));
    await editor.pointer("pointermove", 300, 400); await editor.pointer("pointercancel", 300, 400);
    await editor.click("Save selectors");
    assert.deepEqual(editor.latest().map(p => [p.x, p.y, p.width, p.height]), [[20, 30, 200, 300], [40, 60, 80, 120]]);
  } finally { await editor.close(); }
});

for (const tool of ["Polygon", "Pen"]) test(`${tool} creates and persists a non-rectangular selector`, async () => {
  const editor = await mount();
  try {
    await editor.click(tool);
    if (tool === "Polygon") {
      for (const [x, y] of [[40, 40], [200, 40], [200, 240]]) await editor.pointer("pointerdown", x, y);
    } else {
      await editor.pointer("pointerdown", 40, 40); await editor.pointer("pointermove", 200, 40);
      await editor.pointer("pointermove", 200, 240); await editor.pointer("pointerup", 200, 240);
    }
    await editor.click("Finish shape"); await editor.click("Save selectors");
    assert.equal(editor.latest().length, 2);
    assert.deepEqual(JSON.parse(editor.latest()[1].polygon_json!), [[40, 50], [120, 50], [120, 150]]);
  } finally { await editor.close(); }
});

test("geometry clamps every resize edge, translates shapes, and partitions without gaps", () => {
  const box: Selector = { id: "s", kind: "rect", x: 20, y: 30, width: 101, height: 99 };
  for (const handle of ["nw", "n", "ne", "e", "se", "s", "sw", "w", "center"] as Handle[]) {
    for (const delta of [-10000, 10000]) {
      const next = transformSelector(box, handle, delta, delta, { x: 0, y: 0, width: 300, height: 300 });
      assert.ok(next.width >= 4 && next.height >= 4 && next.x >= 0 && next.y >= 0 && next.x + next.width <= 300 && next.y + next.height <= 300);
    }
  }
  for (const direction of ["vertical", "horizontal"] as const) for (const count of [2, 3, 7, 12]) {
    const parts = splitSelector(box, direction, count);
    const dimension = direction === "vertical" ? "width" : "height", origin = direction === "vertical" ? "x" : "y";
    assert.equal(parts.reduce((sum, p) => sum + p[dimension], 0), box[dimension]);
    for (let i = 1; i < parts.length; i++) assert.equal(parts[i][origin], parts[i - 1][origin] + parts[i - 1][dimension]);
  }
  assert.throws(() => splitSelector({ ...box, width: 5 }, "vertical", 2));
  assert.equal(validPolygon([{ x: 0, y: 0 }, { x: 50, y: 50 }, { x: 0, y: 50 }, { x: 50, y: 0 }]), false);
  const polygon: Selector = { ...box, kind: "polygon", points: [{ x: 20, y: 30 }, { x: 121, y: 30 }, { x: 121, y: 129 }] };
  assert.equal(transformSelector(polygon, "center", 10, 10, { x: 0, y: 0, width: 300, height: 300 }).points![0].x, 30);
});

test("Pages paginates one scrollable page at a time and Auto Detect refreshes real results or reports failure", async () => {
  const editor = await mount({ initialView: "pages" });
  try {
    assert.equal(editor.container.querySelectorAll('[aria-label="Current source page"]').length, 1);
    assert.equal(editor.container.querySelector('[aria-label="Current source page"]')?.getAttribute("data-page-id"), "page-a");
    assert.equal(editor.button("Previous setup page").disabled, true);
    await editor.click("Next setup page");
    assert.equal(editor.container.querySelectorAll('[aria-label="Current source page"]').length, 1);
    assert.equal(editor.container.querySelector('[aria-label="Current source page"]')?.getAttribute("data-page-id"), "page-b");
    assert.equal(editor.button("Next setup page").disabled, true);
    await editor.click("Previous setup page");
    editor.fail(true); await editor.click("Auto Detect");
    assert.match(editor.container.textContent!, /Detection unavailable/);
    assert.equal(editor.latest().length, 0, "failed detection retains the panel inventory");
    editor.fail(false); await editor.click("Auto Detect");
    assert.deepEqual(editor.detectionCalls, [["project", "page-a"], ["project", "page-a"]]);
    assert.equal(editor.latest()[0].id, "panel-a");
    assert.match(editor.container.textContent!, /Panel detection complete/);
  } finally { await editor.close(); }
});

test("Both synchronizes page clicks and panel thumbnails; divider has pointer and keyboard control", async () => {
  const editor = await mount({ initialView: "both", extraPanels: true });
  try {
    assert.ok(editor.container.querySelector('[aria-label="Page selector editor"]'));
    assert.ok(editor.container.querySelector('[aria-label="Panel selector editor"]'));
    await act(async () => editor.container.querySelector('[aria-label="Page panel 2"]')!.dispatchEvent(new window.MouseEvent("click", { bubbles: true })));
    assert.equal(editor.button("Edit panel 2").getAttribute("aria-pressed"), "true");
    assert.equal(editor.container.querySelector('[aria-label="Panel selector editor"]')?.getAttribute("viewBox"), "300 30 200 300");
    await editor.click("Edit panel 1");
    assert.equal(editor.container.querySelector('[aria-label="Page panel 1"]')?.getAttribute("aria-pressed"), "true");
    const separator = editor.container.querySelector('[role="separator"]')!;
    (editor.container.querySelector('[role="tabpanel"]') as any).getBoundingClientRect = () => ({ left: 0, width: 800 });
    await editor.pointer("pointerdown", 400, 0, separator); await editor.pointer("pointermove", 600, 0, separator); await editor.pointer("pointerup", 600, 0, separator);
    assert.equal(separator.getAttribute("aria-valuenow"), "75");
    await act(async () => separator.dispatchEvent(new window.KeyboardEvent("keydown", { key: "Home", bubbles: true })));
    assert.equal(separator.getAttribute("aria-valuenow"), "25");
    await editor.tab("Pages");
    await act(async () => editor.container.querySelector('[aria-label="Page panel 1"]')!.dispatchEvent(new window.MouseEvent("dblclick", { bubbles: true })));
    assert.equal(editor.container.querySelector('[role="tab"][aria-selected="true"]')?.textContent, "Panels");
    assert.equal(editor.container.querySelector('[aria-label="Current source page"]'), null);
    assert.ok(editor.container.querySelector('[aria-label="Panel selector editor"]'));
  } finally { await editor.close(); }
});

test("common selectors stay synchronized across tabs and Page edits save with page bounds", async () => {
  const editor = await mount({ initialView: "pages" });
  try {
    await editor.click("Split vertically");
    for (const tab of ["Panels", "Both", "Pages"]) {
      await editor.tab(tab);
      assert.equal(editor.container.querySelectorAll('[aria-label="Active selector"] option').length, 2);
      assert.ok(editor.button("Delete selector")); assert.ok(editor.button("Save selectors"));
    }
    await editor.click("Save selectors");
    assert.equal(editor.calls[0][3], true, "page edit explicitly requests page-wide validation");
    assert.deepEqual(editor.latest().map(p => p.width), [100, 100]);
  } finally { await editor.close(); }
});

test("an empty page supports real manual selector creation before Auto Detect", async () => {
  const editor = await mount({ initialView: "pages", empty: true });
  try {
    assert.equal(editor.button("Delete panel").disabled, true);
    await editor.click("Rectangle"); await editor.pointer("pointerdown", 40, 60); await editor.pointer("pointermove", 200, 300); await editor.pointer("pointerup", 200, 300);
    await editor.click("Save selectors");
    assert.deepEqual(editor.calls[0], ["project", "page-a", [{ x: 80, y: 120, width: 320, height: 480, points: undefined }]]);
    assert.equal(editor.latest()[0].id, "created-0");
    await editor.click("Delete panel"); await editor.click("Confirm delete panel");
    assert.equal(editor.latest().length, 0);
    assert.equal(editor.button("Save selectors").disabled, true, "a completed page draft must not return after deleting its saved panel");
  } finally { await editor.close(); }
});
