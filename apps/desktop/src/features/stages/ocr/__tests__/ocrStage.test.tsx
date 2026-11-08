import { mountPage } from "../../../__tests__/pageHarness"; // first: installs jsdom before Radix loads
import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { api } from "@panelflow/api-client";
import type { Project } from "@panelflow/shared-types";
import { OcrStage } from "../OcrStage";

const project = (stage = "PANELS_DETECTED") => ({ id: "p1", title: "Dawn Gate", current_stage: stage, rights_status: "AUTHORIZED_WEB", stale_stages: [] }) as unknown as Project;
const page = (n: number) => ({ id: `pg${n}`, project_id: "p1", sequence: n, filename: `${n}.jpg`, status: "READY", width: 1920, height: 22000, byte_size: 1, error_message: null });
const panel = (id: string, n: number) => ({ id, project_id: "p1", page_id: "pg1", sequence: n, page_sequence: n, x: 0, y: n * 1000, width: 1920, height: 900, status: "DETECTED", panel_type: "WEBTOON_SEGMENT", confidence: 0.9, detection_method: "AUTO", reading_direction: "ltr" });
// Real region shape: the crop's own coordinates, text from the engine, statuses NEEDS_REVIEW / CONFIRMED / BLURRED / IGNORED.
const region = (id: string, panelId: string, seq: number, over: Record<string, unknown> = {}) => ({ id, project_id: "p1", page_id: "pg1", panel_id: panelId, sequence_in_panel: seq, sequence_global: seq, x: 100, y: 100 * seq, width: 400, height: 80, region_type: "SPEECH", confidence: 1, status: "NEEDS_REVIEW", detection_method: "AUTO", raw_text: "", corrected_text: "", speaker_character_id: null, ...over });
const ENGINES = [
  { engine_id: "mock_ocr", display_name: "Mock OCR", description: "", is_available: true },
  { engine_id: "windows_media", display_name: "Windows OCR", description: "", is_available: true },
  { engine_id: "paddle_ocr", display_name: "PaddleOCR", description: "", is_available: false },
];
const HISTORY = (over: Record<string, unknown> = {}) => ({ scope: "project", revision: 3, undoCount: 1, redoCount: 1, undoLabel: "Edit", redoLabel: "Edit", canUndo: true, canRedo: true, busy: false, recoveryRequired: false, conflicted: false, fingerprint: "f", error: null, ...over });
const job = (status: string, over: Record<string, unknown> = {}) => ({ job_id: "jo", project_id: "p1", job_type: "OCR_EXTRACTION", status, progress: 0.5, message: "Reading", input: {}, output: {}, error: null, created_at: null, started_at: null, finished_at: null, ...over });

interface Calls { detect: number; extract: any[][]; update: any[][]; confirm: number; getProject: number; listRegions: number; undo: number; contract: number; downloads: Array<[string, string]>; inFlight: number; maxInFlight: number }
function stub(opts: { regions?: any[]; engines?: any[]; jobs?: any[]; jobResult?: any; history?: any; over?: Record<string, unknown> } = {}) {
  const calls: Calls = { detect: 0, extract: [], update: [], confirm: 0, getProject: 0, listRegions: 0, undo: 0, contract: 0, downloads: [], inFlight: 0, maxInFlight: 0 };
  let regions = opts.regions ?? [region("r1", "pa", 1, { raw_text: "Hello" }), region("r2", "pa", 2), region("r3", "pb", 1, { status: "CONFIRMED", raw_text: "Done" })];
  Object.assign(api as any, {
    listPages: async () => [page(1)],
    listPanels: async () => [panel("pa", 1), panel("pb", 2)],
    listTextRegions: async () => { calls.listRegions++; return regions; },
    listOCREngines: async () => opts.engines ?? ENGINES,
    listProjectJobs: async () => opts.jobs ?? [],
    getJob: async () => opts.jobResult ?? (opts.jobs ?? [])[0] ?? job("SUCCEEDED", { progress: 1 }),
    listCharacters: async () => [],
    detectTextRegions: async () => { calls.detect++; return regions; },
    extractOCR: async (...a: any[]) => { calls.extract.push(a); return { job_id: "jo", message: "" }; },
    updateTextRegion: async (...a: any[]) => {
      calls.update.push(a); calls.inFlight++; calls.maxInFlight = Math.max(calls.maxInFlight, calls.inFlight);
      await new Promise((r) => setTimeout(r, 5));
      calls.inFlight--;
      regions = regions.map((r) => (r.id === a[1] ? { ...r, ...a[2] } : r));
      return regions.find((r) => r.id === a[1]);
    },
    confirmOCR: async () => { calls.confirm++; return { project_id: "p1", current_stage: "OCR_CONFIRMED", message: "" }; },
    getProject: async () => { calls.getProject++; return project("OCR_CONFIRMED"); },
    undo: async () => { calls.undo++; return { state: null, history: HISTORY({ canUndo: false }) }; },
    redo: async () => ({ state: null, history: HISTORY() }),
    getCachedProjectHistory: () => opts.history ?? HISTORY(),
    getCanonicalExportContract: async () => { calls.contract++; return { contract_version: "1", panels: [] }; },
    getPanelImageUrl: (_p: string, id: string) => `/panel/${id}.png`,
    ...opts.over,
  });
  return calls;
}
const text = (d: Document) => d.body.textContent ?? "";
const button = (d: Document | Element, label: string | RegExp) => [...d.querySelectorAll("button")].find((b) => (typeof label === "string" ? b.textContent?.trim() === label || b.getAttribute("aria-label") === label : label.test(b.textContent ?? "") || label.test(b.getAttribute("aria-label") ?? ""))) as HTMLButtonElement | undefined;
async function until(cond: () => boolean, ms = 4000) { for (let i = 0; i < ms / 25 && !cond(); i++) await new Promise((r) => setTimeout(r, 25)); }

async function show(over: Partial<React.ComponentProps<typeof OcrStage>> = {}, p = project()) {
  const view = await mountPage(<OcrStage project={p} onApproved={() => {}} onContinue={() => {}} onOpenStoryEditor={() => {}} download={() => {}} {...over} />);
  await view.settle();
  await until(() => Boolean(button(view.document, "Read text")));
  await view.settle();
  return view;
}
const engineSelect = (d: Document) => d.querySelector('select[aria-label="OCR engine"]') as HTMLSelectElement;

test("the stage has one h2 and no h1, and no mock engine is preselected: the first real available engine is", async () => {
  stub();
  const view = await show();
  assert.equal(view.document.querySelectorAll("h1").length, 0);
  assert.ok(view.document.querySelectorAll("h2").length >= 1);
  const select = engineSelect(view.document);
  await until(() => select.value !== "");
  assert.equal(select.value, "windows_media");
  const options = [...select.querySelectorAll("option")];
  assert.equal(options.find((o) => o.value === "paddle_ocr")?.disabled, true);
  assert.ok(options.find((o) => o.value === "paddle_ocr")?.textContent?.includes("Not installed"));
  assert.equal(options.find((o) => o.value === "mock_ocr")?.disabled, false, "a test engine can still be chosen on purpose");
  await view.cleanup();
});

test("with only a test engine, or none, Read text is disabled and the reason is shown", async () => {
  stub({ engines: [ENGINES[0], ENGINES[2]] });
  const only = await show();
  assert.equal(button(only.document, "Read text")!.disabled, true);
  assert.ok(text(only.document).includes("Only a test engine is available. Choose or install a real one in Settings."));
  await only.cleanup();
  stub({ engines: [] });
  const none = await show();
  assert.equal(button(none.document, "Read text")!.disabled, true);
  assert.ok(text(none.document).includes("No OCR engine is available. Install one in Settings."));
  await none.cleanup();
});

test("Detect text regions runs once on a double click", async () => {
  const calls = stub();
  const view = await show();
  await view.clickTwice(button(view.document, "Detect text regions")!);
  await until(() => calls.detect > 0);
  assert.equal(calls.detect, 1);
  await view.cleanup();
});

test("Read text sends the chosen engine once, follows the job and reloads the regions when it ends", async () => {
  const calls = stub();
  const view = await show();
  await until(() => engineSelect(view.document).value === "windows_media");
  const before = calls.listRegions;
  await view.clickTwice(button(view.document, "Read text")!);
  await until(() => calls.extract.length > 0);
  assert.deepEqual(calls.extract, [["p1", "windows_media", "en"]]);
  await until(() => calls.listRegions > before);
  assert.ok(calls.listRegions > before, "regions reloaded after the job ended");
  await view.cleanup();
});

test("a text-reading job already running when the stage opens is followed, not restarted, and Read text waits", async () => {
  const calls = stub({ jobs: [job("RUNNING")], jobResult: job("RUNNING") });
  const view = await show();
  await until(() => text(view.document).includes("Reading"));
  assert.ok(text(view.document).includes("Reading"));
  assert.equal(calls.extract.length, 0);
  assert.equal(button(view.document, "Read text")!.disabled, true);
  await view.cleanup();
});

test("a failed reading job says so in words and is not called finished", async () => {
  stub({ jobs: [job("RUNNING")], jobResult: job("FAILED", { error: "The engine ran out of memory." }) });
  const view = await show();
  await until(() => text(view.document).includes("Couldn't read the text."));
  assert.ok(text(view.document).includes("Couldn't read the text. The engine ran out of memory."));
  await view.cleanup();
});

test("Confirm all with text confirms only regions that have text, one at a time, never writes a placeholder, and reports the counts", async () => {
  const calls = stub({ regions: [region("a", "pa", 1, { raw_text: "One" }), region("b", "pa", 2), region("c", "pa", 3, { raw_text: "Three" }), region("d", "pb", 1, { raw_text: "   " })] });
  const view = await show();
  await view.clickTwice(button(view.document, "Confirm all with text")!);
  await until(() => text(view.document).includes("2 confirmed"));
  assert.deepEqual(calls.update.map((u) => u.slice(0, 2)), [["p1", "a"], ["p1", "c"]]);
  assert.deepEqual(calls.update.map((u) => u[2]), [{ status: "CONFIRMED", corrected_text: "One" }, { status: "CONFIRMED", corrected_text: "Three" }]);
  assert.equal(calls.maxInFlight, 1, "never more than one request at a time");
  assert.ok(text(view.document).includes("2 confirmed, 2 left because they have no text."));
  assert.ok(!JSON.stringify(calls.update).includes("..."));
  await view.cleanup();
});

test("Confirm all with text stops at the first failure and says how far it got", async () => {
  let n = 0;
  const calls = stub({ regions: [region("a", "pa", 1, { raw_text: "One" }), region("b", "pa", 2, { raw_text: "Two" }), region("c", "pa", 3, { raw_text: "Three" })], over: { updateTextRegion: async (...a: any[]) => { n++; if (n === 2) throw new Error("Region was changed elsewhere."); return {}; } } });
  const view = await show();
  await view.click(button(view.document, "Confirm all with text")!);
  await until(() => text(view.document).includes("stopped"));
  assert.ok(text(view.document).includes("1 confirmed, then it stopped. Region was changed elsewhere."));
  assert.equal(n, 2, "nothing is sent after the failure");
  void calls;
  await view.cleanup();
});

test("Approve text is disabled with the reason while regions need review, and enabled when none do", async () => {
  stub();
  const blocked = await show();
  assert.equal(button(blocked.document, "Approve text")!.disabled, true);
  assert.ok(text(blocked.document).includes("2 regions still need review."));
  await blocked.cleanup();
  stub({ regions: [region("a", "pa", 1, { status: "CONFIRMED", raw_text: "x" }), region("i", "pa", 2, { status: "BLURRED", raw_text: "y" })] });
  const open = await show();
  assert.equal(button(open.document, "Approve text")!.disabled, false);
  await open.cleanup();
});

test("Approve text approves once, reloads the project and hands it over; a refusal shows the reason and does not move on", async () => {
  const calls = stub({ regions: [region("a", "pa", 1, { status: "CONFIRMED", raw_text: "x" })] });
  const approved: string[] = [];
  const view = await show({ onApproved: (p) => approved.push(p.current_stage) });
  await view.clickTwice(button(view.document, "Approve text")!);
  await until(() => approved.length > 0);
  assert.equal(calls.confirm, 1);
  assert.deepEqual(approved, ["OCR_CONFIRMED"]);
  await view.cleanup();

  stub({ regions: [region("a", "pa", 1, { status: "CONFIRMED", raw_text: "x" })], over: { confirmOCR: async () => { throw new Error("Panel 4 has unreviewed text."); } } });
  const moved: string[] = [];
  const refused = await show({ onApproved: (p) => moved.push(p.id) });
  await refused.click(button(refused.document, "Approve text")!);
  await until(() => text(refused.document).includes("Text can't be approved yet."));
  assert.ok(text(refused.document).includes("Text can't be approved yet. Panel 4 has unreviewed text."));
  assert.deepEqual(moved, []);
  await refused.cleanup();
});

test("an approved project offers Continue to story and Open story editor", async () => {
  stub();
  let continued = 0;
  const view = await show({ onContinue: () => { continued++; } }, project("OCR_CONFIRMED"));
  await view.click(button(view.document, "Continue to story")!);
  assert.equal(continued, 1);
  assert.ok(button(view.document, "Open story editor"));
  await view.cleanup();
});

test("Export contract downloads the engine's contract without a browser dialog, and a failure says so in words", async () => {
  const saved: Array<[string, string]> = [];
  const calls = stub();
  const view = await show({ download: (f, c) => saved.push([f, c]) });
  await view.clickTwice(button(view.document, "Export contract")!);
  await until(() => saved.length > 0);
  assert.equal(calls.contract, 1);
  assert.match(saved[0][0], /contract.*\.json$/);
  assert.deepEqual(JSON.parse(saved[0][1]), { contract_version: "1", panels: [] });
  await view.cleanup();
  stub({ over: { getCanonicalExportContract: async () => { throw new Error("The contract is not ready."); } } });
  const failed = await show({ download: () => { throw new Error("must not download"); } });
  await failed.click(button(failed.document, "Export contract")!);
  await until(() => text(failed.document).includes("Couldn't export the contract."));
  assert.ok(text(failed.document).includes("Couldn't export the contract. The contract is not ready."));
  await failed.cleanup();
});

test("Undo and Redo use the engine's history once each and are disabled with its state", async () => {
  const calls = stub();
  const view = await show();
  await view.clickTwice(button(view.document, "Undo")!);
  await until(() => calls.undo > 0);
  assert.equal(calls.undo, 1);
  await view.cleanup();
  stub({ history: HISTORY({ conflicted: true, canUndo: false, canRedo: false }) });
  const blocked = await show();
  assert.equal(button(blocked.document, "Undo")!.disabled, true);
  assert.equal(button(blocked.document, "Redo")!.disabled, true);
  await blocked.cleanup();
});

test("the gate banner counts the regions needing review and no stale milestone banner is shown", async () => {
  stub();
  const view = await show();
  assert.ok(text(view.document).includes("2 regions need review."));
  assert.ok(button(view.document, "Jump to next flagged"));
  assert.ok(!/Milestone|Production Gate|Story Preview Experimental/.test(text(view.document)));
  await view.cleanup();
});

test("with no regions yet, the stage invites detecting them", async () => {
  stub({ regions: [] });
  const view = await show();
  assert.ok(text(view.document).includes("No text regions yet. Detect text regions to find the text in the panels."));
  await view.cleanup();
});
