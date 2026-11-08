import { mountPage } from "../../../__tests__/pageHarness"; // first: installs jsdom before Radix loads
import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { act } from "react";
import { api } from "@panelflow/api-client";
import type { Page, Project } from "@panelflow/shared-types";
import { PagesStage } from "../PagesStage";

const project = { id: "p1", title: "Dawn Gate", current_stage: "ACQUIRED", rights_status: "AUTHORIZED_WEB", stale_stages: [] } as unknown as Project;
const mk = (n: number, status: Page["status"] = "READY", over: Partial<Page> = {}) => ({ id: `pg${n}`, project_id: "p1", sequence: n, filename: `${n}.png`, status, error_message: status === "FAILED" ? "bad file" : null, width: 800, height: 1200, byte_size: 2048, ...over }) as Page;

interface Calls { reorder: string[][]; rotate: string[]; del: string[]; confirm: number; retry: number }
function stub(initial: Page[], over: Record<string, unknown> = {}) {
  let pages = [...initial];
  const calls: Calls = { reorder: [], rotate: [], del: [], confirm: 0, retry: 0 };
  Object.assign(api as any, {
    listPages: async () => pages.map((p, i) => ({ ...p, sequence: i + 1 })),
    reorderPages: async (_id: string, ids: string[]) => { calls.reorder.push(ids); pages = ids.map((id) => pages.find((p) => p.id === id)!); return pages.map((p, i) => ({ ...p, sequence: i + 1 })); },
    rotatePage: async (_id: string, pageId: string) => { calls.rotate.push(pageId); return pages.find((p) => p.id === pageId)!; },
    deletePage: async (_id: string, pageId: string) => { calls.del.push(pageId); pages = pages.filter((p) => p.id !== pageId); },
    confirmAcquisition: async () => { calls.confirm++; return { ...project, current_stage: "NORMALIZED" }; },
    retryFailedPages: async () => { calls.retry++; return { job_id: "j9", message: "" }; },
    getJob: async () => ({ job_id: "j9", status: "SUCCEEDED", progress: 1, message: "", job_type: "RETRY_PAGES" }),
    getManifest: async () => ({ project_id: "p1", version: "1", pages: [{ marker: "manifest-page-one" }] }),
    getPageImageUrl: (_p: string, id: string) => `/img/${id}.png`,
    ...over,
  });
  return calls;
}
const text = (d: Document) => d.body.textContent ?? "";
const byLabel = (d: Document, label: string) => d.querySelector(`[aria-label="${label}"]`) as HTMLButtonElement | null;
const button = (d: Document, label: string | RegExp) => [...d.querySelectorAll("button")].find((b) => (typeof label === "string" ? b.textContent?.trim() === label : label.test(b.textContent ?? ""))) as HTMLButtonElement | undefined;
const order = (d: Document) => [...d.querySelectorAll("[data-page-id]")].map((e) => e.getAttribute("data-page-id"));

async function show(onConfirmed: (p: Project) => void = () => {}, onContinue: (p: Project) => void = () => {}) {
  const view = await mountPage(<PagesStage project={project} onConfirmed={onConfirmed} onContinue={onContinue} />);
  await view.settle();
  return view;
}

function forbidBrowserDialogs() {
  const w = globalThis as any;
  const saved = { confirm: w.window?.confirm, alert: w.window?.alert };
  w.window.confirm = () => { throw new Error("window.confirm must not be used"); };
  w.window.alert = () => { throw new Error("window.alert must not be used"); };
  return () => { w.window.confirm = saved.confirm; w.window.alert = saved.alert; };
}

test("pages render in sequence order with one h2 and no h1", async () => {
  stub([mk(1), mk(2), mk(3)]);
  const view = await show();
  assert.deepEqual(order(view.document), ["pg1", "pg2", "pg3"]);
  assert.equal(view.document.querySelectorAll("h1").length, 0);
  assert.ok(text(view.document).includes("Review pages"));
  await view.cleanup();
});

test("Move later on the first page saves the swapped order once and the grid follows", async () => {
  const calls = stub([mk(1), mk(2), mk(3)]);
  const view = await show();
  await view.clickTwice(byLabel(view.document, "Move page 1 later")!);
  await view.settle();
  assert.deepEqual(calls.reorder, [["pg2", "pg1", "pg3"]]);
  assert.deepEqual(order(view.document), ["pg2", "pg1", "pg3"]);
  await view.cleanup();
});

test("Move earlier is disabled on the first page and Move later on the last", async () => {
  stub([mk(1), mk(2)]);
  const view = await show();
  assert.equal(byLabel(view.document, "Move page 1 earlier")!.disabled, true);
  assert.equal(byLabel(view.document, "Move page 2 later")!.disabled, true);
  assert.equal(byLabel(view.document, "Move page 2 earlier")!.disabled, false);
  await view.cleanup();
});

test("a failed reorder restores the previous order and says so", async () => {
  stub([mk(1), mk(2)], { reorderPages: async () => { throw new Error("boom C:\\engine\\x.py"); } });
  const view = await show();
  await view.click(byLabel(view.document, "Move page 1 later")!);
  await view.settle();
  assert.deepEqual(order(view.document), ["pg1", "pg2"]);
  assert.ok(text(view.document).includes("Couldn't save the new order"));
  assert.ok(!text(view.document).includes("x.py"));
  await view.cleanup();
});

test("Rotate rotates the page by 90 degrees once, even on a double click", async () => {
  const calls = stub([mk(1), mk(2)]);
  const view = await show();
  await view.clickTwice(byLabel(view.document, "Rotate page 2")!);
  await view.settle();
  assert.deepEqual(calls.rotate, ["pg2"]);
  await view.cleanup();
});

test("Delete asks in the app first; Cancel deletes nothing, confirming deletes once; no browser dialogs are used", async () => {
  const restore = forbidBrowserDialogs();
  try {
    const calls = stub([mk(1), mk(2), mk(3)]);
    const view = await show();
    await view.click(byLabel(view.document, "Delete page 2")!);
    const dialog = () => view.document.querySelector('[role="dialog"]');
    assert.ok(dialog());
    assert.ok(text(view.document).includes("Delete page 2?"));
    await view.click([...dialog()!.querySelectorAll("button")].find((b) => b.textContent === "Cancel")!);
    await view.settle();
    assert.deepEqual(calls.del, []);
    assert.equal(order(view.document).length, 3);
    await view.click(byLabel(view.document, "Delete page 2")!);
    await view.clickTwice([...dialog()!.querySelectorAll("button")].find((b) => b.textContent === "Delete page")!);
    await view.settle();
    assert.deepEqual(calls.del, ["pg2"]);
    assert.deepEqual(order(view.document), ["pg1", "pg3"]);
    await view.cleanup();
  } finally { restore(); }
});

test("a failed delete explains itself in the page, not in a browser alert", async () => {
  const restore = forbidBrowserDialogs();
  try {
    stub([mk(1), mk(2)], { deletePage: async () => { throw new Error("no"); } });
    const view = await show();
    await view.click(byLabel(view.document, "Delete page 1")!);
    await view.click([...view.document.querySelectorAll('[role="dialog"] button')].find((b) => b.textContent === "Delete page")!);
    await view.settle();
    assert.ok(text(view.document).includes("Couldn't delete the page"));
    assert.equal(order(view.document).length, 2);
    await view.cleanup();
  } finally { restore(); }
});

test("Confirm acquisition is disabled with the reason when no page is ready", async () => {
  const calls = stub([mk(1, "FAILED")]);
  const view = await show();
  const confirm = button(view.document, /^Confirm acquisition/)!;
  assert.equal(confirm.disabled, true);
  assert.ok(text(view.document).includes("No pages are ready yet. Go back to Acquire."));
  await view.click(confirm);
  assert.equal(calls.confirm, 0);
  await view.cleanup();
});

test("Confirm acquisition confirms once and hands over the updated project", async () => {
  const calls = stub([mk(1), mk(2), mk(3, "FAILED")]);
  const handed: Project[] = [];
  const view = await show((p) => handed.push(p));
  const confirm = button(view.document, "Confirm acquisition (2 pages)")!;
  assert.ok(confirm);
  await view.clickTwice(confirm);
  await view.settle();
  assert.equal(calls.confirm, 1);
  assert.equal(handed.length, 1);
  assert.equal(handed[0].current_stage, "NORMALIZED");
  await view.cleanup();
});

test("a refused confirmation shows the engine's plain reason and does not move on", async () => {
  stub([mk(1)], { confirmAcquisition: async () => { throw new Error("Project is already confirmed."); } });
  let moved = 0;
  const view = await show(() => { moved++; });
  await view.click(button(view.document, /^Confirm acquisition/)!);
  await view.settle();
  assert.ok(text(view.document).includes("Couldn't confirm the pages. Project is already confirmed."));
  assert.equal(moved, 0);
  assert.ok(!button(view.document, /^Confirm acquisition/)!.disabled, "can try again");
  await view.cleanup();
});

test("Continue to panels moves on without confirming", async () => {
  const calls = stub([mk(1)]);
  let continued = 0;
  const view = await show(() => {}, () => { continued++; });
  await view.click(button(view.document, "Continue to panels")!);
  assert.equal(continued, 1);
  assert.equal(calls.confirm, 0);
  await view.cleanup();
});

test("Retry failed pages starts one retry job", async () => {
  const calls = stub([mk(1), mk(2, "FAILED")]);
  const view = await show();
  await view.clickTwice(button(view.document, "Retry failed pages (1)")!);
  await view.settle();
  assert.equal(calls.retry, 1);
  await view.cleanup();
});

test("View manifest shows the manifest the engine holds", async () => {
  stub([mk(1)]);
  const view = await show();
  await view.click(button(view.document, "View manifest")!);
  await view.settle();
  assert.ok(text(view.document).includes("manifest-page-one"));
  await view.cleanup();
});

test("the inspector opens on a page, changes view mode, stays within 25 to 400 percent zoom, and steps between pages", async () => {
  stub([mk(1), mk(2)]);
  const view = await show();
  await view.click(byLabel(view.document, "Open Page 1")!);
  const inspector = () => view.document.querySelector('[role="dialog"]')!;
  assert.ok(inspector());
  assert.ok(text(view.document).includes("Page 1 of 2"));
  assert.equal(byLabel(view.document, "Fit page")!.getAttribute("aria-pressed"), "true");
  await view.click(byLabel(view.document, "Original size")!);
  assert.equal(byLabel(view.document, "Original size")!.getAttribute("aria-pressed"), "true");
  for (let i = 0; i < 20; i++) await view.click(byLabel(view.document, "Zoom in")!);
  assert.ok(inspector().textContent!.includes("400%"));
  for (let i = 0; i < 30; i++) await view.click(byLabel(view.document, "Zoom out")!);
  assert.ok(inspector().textContent!.includes("25%"));
  await view.click(byLabel(view.document, "Next page")!);
  assert.ok(text(view.document).includes("Page 2 of 2"));
  await act(async () => { window.dispatchEvent(new KeyboardEvent("keydown", { key: "ArrowLeft" })); });
  assert.ok(text(view.document).includes("Page 1 of 2"), "arrow keys step through pages");
  await view.cleanup();
});

test("a failed page cannot be opened or rotated but can be moved and deleted", async () => {
  stub([mk(1, "FAILED"), mk(2)]);
  const view = await show();
  assert.equal(byLabel(view.document, "Open Page 1"), null);
  assert.equal(byLabel(view.document, "Rotate page 1"), null);
  assert.ok(byLabel(view.document, "Delete page 1"));
  assert.equal(byLabel(view.document, "Move page 1 later")!.disabled, false);
  await view.cleanup();
});

test("no pages: an empty state points back to Acquire", async () => {
  stub([]);
  const view = await show();
  assert.ok(text(view.document).includes("No pages yet"));
  assert.equal(button(view.document, /^Confirm acquisition/)!.disabled, true);
  await view.cleanup();
});
