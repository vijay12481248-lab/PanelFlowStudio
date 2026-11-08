import { mountPage } from "../../../__tests__/pageHarness"; // first: installs jsdom before Radix loads
import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { act } from "react";
import { api } from "@panelflow/api-client";
import type { Project } from "@panelflow/shared-types";
import { PanelsStage } from "../PanelsStage";

const project = (stage = "NORMALIZED") => ({ id: "p1", title: "Dawn Gate", current_stage: stage, rights_status: "AUTHORIZED_WEB", stale_stages: [] }) as unknown as Project;

// Real shapes: webtoon strips 1920 px wide, panels of type WEBTOON_SEGMENT, some excluded (IGNORED).
const page = (n: number) => ({ id: `pg${n}`, project_id: "p1", sequence: n, filename: `${n}.jpg`, status: "READY", width: 1920, height: 22000, byte_size: 1000, error_message: null });
const panel = (id: string, pageN: number, seq: number, status = "DETECTED") => ({ id, project_id: "p1", page_id: `pg${pageN}`, sequence: seq, page_sequence: seq, x: 0, y: seq * 1000, width: 1920, height: 900, status, panel_type: "WEBTOON_SEGMENT", confidence: 0.9, detection_method: "AUTO", reading_direction: "ltr" });
const PANELS = [panel("a", 1, 1), panel("b", 1, 2), panel("c", 1, 3, "IGNORED"), panel("d", 2, 1)];
const HISTORY = (over: Record<string, unknown> = {}) => ({ scope: "project", revision: 3, undoCount: 1, redoCount: 1, undoLabel: "Move panel", redoLabel: "Delete panel", canUndo: true, canRedo: true, busy: false, recoveryRequired: false, conflicted: false, fingerprint: "f", error: null, ...over });
const job = (status: string, type = "PANEL_DETECTION", over: Record<string, unknown> = {}) => ({ job_id: "jd", project_id: "p1", job_type: type, status, progress: 0.5, message: "Detecting", input: {}, output: {}, error: null, created_at: null, started_at: null, finished_at: null, ...over });

interface Calls { detect: any[][]; detectPage: any[][]; normalize: any[][]; confirm: number; getProject: number; undo: number; redo: number; listPanels: number; getJob: number }
function stub(opts: { pages?: any[]; panels?: any[]; jobs?: any[]; jobResult?: any; history?: any; over?: Record<string, unknown> } = {}) {
  const calls: Calls = { detect: [], detectPage: [], normalize: [], confirm: 0, getProject: 0, undo: 0, redo: 0, listPanels: 0, getJob: 0 };
  let panels = opts.panels ?? PANELS;
  let history = opts.history ?? HISTORY();
  Object.assign(api as any, {
    listPages: async () => opts.pages ?? [page(1), page(2), page(3)],
    listPanels: async () => { calls.listPanels++; return panels; },
    listProjectJobs: async () => opts.jobs ?? [],
    getJob: async (id: string) => { calls.getJob++; return opts.jobResult ?? (opts.jobs ?? []).find((j) => j.job_id === id) ?? job("SUCCEEDED", "PANEL_DETECTION", { progress: 1 }); },
    detectPanels: async (...a: any[]) => { calls.detect.push(a); return { job_id: "jd", message: "" }; },
    detectPagePanels: async (...a: any[]) => { calls.detectPage.push(a); return [panel("n1", 1, 1)]; },
    normalizeProject: async (...a: any[]) => { calls.normalize.push(a); return { job_id: "jn", message: "" }; },
    confirmPanels: async () => { calls.confirm++; return { current_stage: "PANELS_DETECTED", message: "" }; },
    getProject: async () => { calls.getProject++; return project("PANELS_DETECTED"); },
    undo: async () => { calls.undo++; history = HISTORY({ canUndo: false }); return { state: null, history }; },
    redo: async () => { calls.redo++; return { state: null, history }; },
    getCachedProjectHistory: () => history,
    getNormalizedPageImageUrl: (_p: string, id: string) => `/page/${id}.png`,
    getPanelImageUrl: (_p: string, id: string) => `/panel/${id}.png`,
    ...opts.over,
  });
  return { calls, setPanels: (p: any[]) => { panels = p; } };
}
const text = (d: Document) => d.body.textContent ?? "";
const button = (d: Document | Element, label: string | RegExp) => [...d.querySelectorAll("button")].find((b) => (typeof label === "string" ? b.textContent?.trim() === label || b.getAttribute("aria-label") === label : label.test(b.textContent ?? "") || label.test(b.getAttribute("aria-label") ?? ""))) as HTMLButtonElement | undefined;
const dialogButton = (d: Document, label: string) => [...d.querySelectorAll('[role="dialog"] button')].find((b) => b.textContent?.trim() === label) as HTMLButtonElement | undefined;
const boxes = (d: Document) => [...d.querySelectorAll("[data-box-id]")].map((e) => e.getAttribute("data-box-id"));
async function until(cond: () => boolean, ms = 4000) { for (let i = 0; i < ms / 25 && !cond(); i++) await new Promise((r) => setTimeout(r, 25)); }

async function show(p = project(), over: Partial<React.ComponentProps<typeof PanelsStage>> = {}) {
  const view = await mountPage(<PanelsStage project={p} onConfirmed={() => {}} onContinue={() => {}} onOpenStoryEditor={() => {}} {...over} />);
  await view.settle();
  await until(() => boxes(view.document).length > 0 || text(view.document).includes("No panels"));
  return view;
}

test("the stage shows the pages with their panel counts and the current page's panels on the canvas, one h2, no h1", async () => {
  stub();
  const view = await show();
  assert.equal(view.document.querySelectorAll("h1").length, 0);
  assert.equal(view.document.querySelectorAll("h2").length >= 1, true);
  const chips = [...view.document.querySelectorAll("[data-page-id]")];
  assert.deepEqual(chips.map((c) => c.getAttribute("data-page-id")), ["pg1", "pg2", "pg3"]);
  assert.ok(chips[0].textContent!.includes("2 panels"), "excluded panels are not counted");
  assert.ok(chips[2].textContent!.includes("0 panels"));
  assert.deepEqual(boxes(view.document), ["a", "b", "c"], "the excluded panel is still drawn");
  await view.cleanup();
});

test("Right and Left arrows change page, and a page with no panels says so", async () => {
  stub();
  const view = await show();
  const press = (k: string) => act(async () => { window.dispatchEvent(new KeyboardEvent("keydown", { key: k, bubbles: true })); });
  await press("ArrowRight");
  assert.deepEqual(boxes(view.document), ["d"]);
  await press("ArrowRight");
  assert.ok(text(view.document).includes("No panels on this page"));
  await press("ArrowLeft");
  assert.deepEqual(boxes(view.document), ["d"]);
  await view.cleanup();
});

test("detecting asks first when panels exist, then sends the direction once and follows the job to reload the panels", async () => {
  const { calls } = stub();
  const view = await show();
  await view.click(button(view.document, "Detect panels")!);
  assert.ok(text(view.document).includes("Detect again?"));
  await view.click(dialogButton(view.document, "Cancel")!);
  assert.equal(calls.detect.length, 0);
  await view.setSelect(view.document.querySelector('[aria-label="Reading direction"]') as HTMLSelectElement, "rtl");
  await view.click(button(view.document, "Detect panels")!);
  await view.clickTwice(dialogButton(view.document, "Detect panels")!);
  const before = calls.listPanels;
  await until(() => calls.listPanels > before);
  assert.deepEqual(calls.detect, [["p1", "rtl", 0.02]]);
  assert.ok(calls.listPanels > before, "panels reloaded when the job ended");
  await view.cleanup();
});

test("with no panels yet, Detect panels starts at once", async () => {
  const { calls } = stub({ panels: [] });
  const view = await show();
  await view.click(button(view.document, "Detect panels")!);
  await view.settle();
  assert.equal(calls.detect.length, 1);
  assert.ok(!text(view.document).includes("Detect again?"));
  await view.cleanup();
});

test("a detection already running when the stage opens is followed, not restarted, and polling stops after leaving", async () => {
  const { calls } = stub({ jobs: [job("RUNNING", "PANEL_DETECTION", { message: "Page 4 of 12" })] });
  const view = await show();
  assert.equal(calls.detect.length, 0);
  assert.ok(text(view.document).includes("Page 4 of 12"));
  await view.cleanup();
  const after = calls.getJob;
  await new Promise((r) => setTimeout(r, 1300));
  assert.equal(calls.getJob, after, "no polling after the stage unmounted");
});

test("a failed detection or normalisation job says why in words, and a job that is still running is never called failed", async () => {
  stub({ jobResult: job("FAILED", "PANEL_DETECTION", { error: "Model could not load." }) });
  const a = await show();
  await a.click(button(a.document, "Detect panels")!);
  await a.click(dialogButton(a.document, "Detect panels")!);
  await until(() => text(a.document).includes("Couldn't detect the panels"));
  assert.ok(text(a.document).includes("Couldn't detect the panels. Model could not load."));
  await a.cleanup();
  stub({ jobResult: job("FAILED", "NORMALIZATION", { error: "Disk is full." }) });
  const b = await show();
  await b.click(button(b.document, "Normalize pages")!);
  await until(() => text(b.document).includes("Couldn't normalize the pages"));
  assert.ok(text(b.document).includes("Couldn't normalize the pages. Disk is full."));
  await b.cleanup();
  const { calls } = stub({ jobResult: job("RUNNING", "PANEL_DETECTION") });
  const c = await show();
  await c.click(button(c.document, "Detect panels")!);
  await c.click(dialogButton(c.document, "Detect panels")!);
  await new Promise((r) => setTimeout(r, 2500));
  assert.ok(calls.getJob >= 2, "it keeps polling");
  assert.ok(!text(c.document).includes("Couldn't detect"), "a running job is not a failure");
  await c.cleanup();
});

test("Normalize pages starts one job with the 1920 pixel width", async () => {
  const { calls } = stub();
  const view = await show();
  await view.clickTwice(button(view.document, "Normalize pages")!);
  await view.settle();
  assert.deepEqual(calls.normalize, [["p1", 1920]]);
  await view.cleanup();
});

test("Detect this page replaces that page's panels with the engine's answer", async () => {
  const { calls } = stub();
  const view = await show();
  await view.clickTwice(button(view.document, "Detect this page")!);
  await until(() => boxes(view.document).includes("n1"));
  assert.deepEqual(calls.detectPage, [["p1", "pg1", "ltr"]]);
  assert.deepEqual(boxes(view.document), ["n1"]);
  await view.cleanup();
});

test("Confirm panels is disabled with the reason when nothing is detected", async () => {
  const { calls } = stub({ panels: [panel("x", 1, 1, "IGNORED")] });
  const view = await show();
  const confirm = button(view.document, "Confirm panels")!;
  assert.equal(confirm.disabled, true);
  assert.ok(text(view.document).includes("Detect or add at least one panel first."));
  await view.click(confirm);
  assert.equal(calls.confirm, 0);
  await view.cleanup();
});

test("Confirm panels confirms once and hands over the project; a refusal shows the reason and does not move on", async () => {
  const { calls } = stub();
  const handed: Project[] = [];
  const view = await show(project(), { onConfirmed: (p) => handed.push(p) });
  await view.clickTwice(button(view.document, "Confirm panels")!);
  await view.settle();
  assert.equal(calls.confirm, 1);
  assert.equal(calls.getProject, 1);
  assert.equal(handed[0].current_stage, "PANELS_DETECTED");
  await view.cleanup();
  stub({ over: { confirmPanels: async () => { throw new Error("Two panels overlap completely."); } } });
  let moved = 0;
  const refused = await show(project(), { onConfirmed: () => { moved++; } });
  await refused.click(button(refused.document, "Confirm panels")!);
  await refused.settle();
  assert.ok(text(refused.document).includes("Panels can't be confirmed yet. Two panels overlap completely."));
  assert.equal(moved, 0);
  assert.equal(button(refused.document, "Confirm panels")!.disabled, false);
  await refused.cleanup();
});

test("confirmed panels offer Continue to OCR and Open story editor", async () => {
  stub();
  let continued = 0, opened = 0;
  const view = await show(project("PANELS_DETECTED"), { onContinue: () => { continued++; }, onOpenStoryEditor: () => { opened++; } });
  assert.ok(text(view.document).includes("Confirmed"));
  await view.click(button(view.document, "Continue to OCR")!);
  await view.click(button(view.document, "Open story editor")!);
  assert.deepEqual([continued, opened], [1, 1]);
  await view.cleanup();
});

test("Undo and Redo use the engine's history once each, reload the panels, and disable with the engine's state", async () => {
  const { calls } = stub();
  const view = await show();
  const before = calls.listPanels;
  await view.clickTwice(button(view.document, "Undo")!);
  await until(() => calls.undo > 0);
  await view.settle();
  assert.equal(calls.undo, 1);
  assert.ok(calls.listPanels > before);
  assert.equal(button(view.document, "Undo")!.disabled, true, "the refreshed history says there is nothing left to undo");
  await view.click(button(view.document, "Redo")!);
  assert.equal(calls.redo, 1);
  await view.cleanup();
});

test("a conflicted history blocks undo and redo and says why", async () => {
  stub({ history: HISTORY({ conflicted: true }) });
  const view = await show();
  assert.equal(button(view.document, "Undo")!.disabled, true);
  assert.equal(button(view.document, "Redo")!.disabled, true);
  assert.ok(text(view.document).includes("The project changed somewhere else. Reload the page before undoing."));
  await view.cleanup();
});

test("a project with hundreds of pages draws only a window of them", async () => {
  stub({ pages: Array.from({ length: 300 }, (_, i) => page(i + 1)), panels: Array.from({ length: 625 }, (_, i) => panel(`q${i}`, (i % 300) + 1, 1)) });
  const view = await show();
  const chips = view.document.querySelectorAll("[data-page-id]").length;
  assert.ok(chips <= 41, `${chips} page chips`);
  assert.ok(text(view.document).includes("Page 1 of 300"));
  await view.cleanup();
});
