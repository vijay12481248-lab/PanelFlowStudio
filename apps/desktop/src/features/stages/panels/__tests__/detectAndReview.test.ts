import test from "node:test";
import assert from "node:assert/strict";
import { ReviewError, runDetectAndReview, type ReviewDeps } from "../detectAndReview";

const ENGINES = [{ engine_id: "mock_ocr", is_available: true }, { engine_id: "windows_media", is_available: true }];

function deps(over: Partial<Record<keyof ReviewDeps["api"], any>> = {}, jobStates: string[] = ["SUCCEEDED"]) {
  const log: string[] = [];
  let poll = 0;
  const api = {
    listOCREngines: async () => { log.push("engines"); return ENGINES; },
    detectPanels: async (_p: string, direction: string, ratio: number) => { log.push(`detect:${direction}:${ratio}`); return { job_id: "j1" }; },
    getJob: async () => { const status = jobStates[Math.min(poll++, jobStates.length - 1)]; log.push(`job:${status}`); return { status, error: status === "FAILED" ? "Model could not load." : null, message: "" }; },
    cancelJob: async (id: string) => { log.push(`cancel:${id}`); return {}; },
    listPanels: async () => { log.push("panels"); return []; },
    detectTextRegions: async () => { log.push("regions"); return [{ id: "r1", raw_text: "", corrected_text: "", status: "NEEDS_REVIEW" }, { id: "r2", raw_text: "Hello", corrected_text: "", status: "NEEDS_REVIEW" }, { id: "r3", raw_text: "", corrected_text: "", status: "IGNORED" }, { id: "r4", raw_text: "", corrected_text: "", status: "NEEDS_REVIEW" }]; },
    ocrSingleRegion: async (_p: string, id: string, engine: string) => { log.push(`ocr:${id}:${engine}`); return {}; },
    getPanelContentSuggestions: async () => { log.push("suggestions"); return { suggestions: [], labels: [], regions_checked: 2, ocr_required: false }; },
    ...over,
  };
  return { log, deps: { api, sleep: async () => {} } as unknown as ReviewDeps };
}

test("it runs the steps in order and reads text only for regions that have none and are not excluded", async () => {
  const { log, deps: d } = deps();
  const steps: string[] = [];
  const review = await runDetectAndReview({ projectId: "p1", direction: "rtl", deps: d, isCancelled: () => false, onStep: (s) => steps.push(s) });
  assert.deepEqual(log, ["engines", "detect:rtl:0.02", "job:SUCCEEDED", "panels", "regions", "ocr:r1:windows_media", "ocr:r4:windows_media", "suggestions"]);
  assert.equal(review.regions_checked, 2);
  assert.deepEqual(steps.filter((s) => /^Reading text/.test(s)), ["Reading text 1 of 2", "Reading text 2 of 2"]);
  assert.equal(steps[0], "Checking the OCR engine");
});

test("with no usable engine it stops at once and says so, and with only a test engine it says that", async () => {
  const none = deps({ listOCREngines: async () => [{ engine_id: "paddle_ocr", is_available: false }] });
  await assert.rejects(() => runDetectAndReview({ projectId: "p1", direction: "ltr", deps: none.deps, isCancelled: () => false, onStep: () => {} }), (e: unknown) => e instanceof ReviewError && e.message === "No OCR engine is available. Install one in Settings.");
  assert.deepEqual(none.log, []);
  const mock = deps({ listOCREngines: async () => [{ engine_id: "mock_ocr", is_available: true }] });
  await assert.rejects(() => runDetectAndReview({ projectId: "p1", direction: "ltr", deps: mock.deps, isCancelled: () => false, onStep: () => {} }), (e: unknown) => e instanceof ReviewError && e.message.startsWith("Only a test engine is available."));
});

test("a failed detection job stops the review with the engine's reason", async () => {
  const { log, deps: d } = deps({}, ["RUNNING", "FAILED"]);
  await assert.rejects(() => runDetectAndReview({ projectId: "p1", direction: "ltr", deps: d, isCancelled: () => false, onStep: () => {} }), (e: unknown) => e instanceof ReviewError && e.message === "Couldn't detect the panels. Model could not load.");
  assert.ok(!log.includes("regions"), "nothing after the failure ran");
});

test("a job that runs for a very long time is waited for, never given up on", async () => {
  const states = [...Array(1500).fill("RUNNING"), "SUCCEEDED"];
  const { log, deps: d } = deps({}, states);
  await runDetectAndReview({ projectId: "p1", direction: "ltr", deps: d, isCancelled: () => false, onStep: () => {} });
  assert.equal(log.filter((l) => l === "job:RUNNING").length, 1500);
  assert.ok(log.includes("suggestions"), "and it finished");
});

test("cancelling cancels the running job and runs nothing after", async () => {
  let polls = 0;
  const { log, deps: d } = deps({}, ["RUNNING", "RUNNING", "RUNNING"]);
  await assert.rejects(() => runDetectAndReview({ projectId: "p1", direction: "ltr", deps: d, isCancelled: () => polls++ >= 2, onStep: () => {} }), (e: unknown) => e instanceof ReviewError && e.message === "Detect and review was cancelled.");
  assert.ok(log.includes("cancel:j1"));
  assert.ok(!log.includes("regions") && !log.includes("suggestions"));
});

test("leaving the screen (cancelled before the job starts) calls nothing further", async () => {
  const { log, deps: d } = deps();
  await assert.rejects(() => runDetectAndReview({ projectId: "p1", direction: "ltr", deps: d, isCancelled: () => true, onStep: () => {} }));
  assert.deepEqual(log, ["engines"]);
});

test("cancelling between regions stops the reading", async () => {
  let reads = 0;
  const { log, deps: d } = deps({ ocrSingleRegion: async (_p: string, id: string) => { reads++; log2.push(id); } });
  const log2: string[] = [];
  await assert.rejects(() => runDetectAndReview({ projectId: "p1", direction: "ltr", deps: d, isCancelled: () => reads >= 1, onStep: () => {} }));
  assert.deepEqual(log2, ["r1"]);
  assert.ok(!log.includes("suggestions"));
});
