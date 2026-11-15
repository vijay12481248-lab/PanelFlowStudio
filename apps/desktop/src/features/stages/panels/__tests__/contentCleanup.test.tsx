import { mountPage } from "../../../__tests__/pageHarness"; // first: installs jsdom before Radix loads
import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { api } from "@panelflow/api-client";
import type { Panel } from "@panelflow/shared-types";
import { ContentCleanup, type Review } from "../ContentCleanup";
import { DetectAndReview } from "../DetectReviewControl";

const PANELS = [{ id: "pn1", page_id: "pg1", x: 0, y: 100, width: 1920, height: 900, status: "DETECTED", page_sequence: 1 }, { id: "pn2", page_id: "pg1", x: 0, y: 1100, width: 1920, height: 900, status: "DETECTED", page_sequence: 2 }] as unknown as Panel[];
const SUGGESTIONS = (): Review => ({
  suggestions: [
    { region_id: "r1", panel_id: "pn1", page_id: "pg1", text: "MANHUAPLUS.COM", bbox: [10, 20, 300, 60], reason: "Matches a promotional label" },
    { region_id: "r2", panel_id: "pn2", page_id: "pg1", text: "READ ON MANHUAPLUS.COM", bbox: [0, 0, 500, 80], reason: "Contains a website link" },
  ],
  labels: ["ManhuaPlus.com"], regions_checked: 24, ocr_required: false,
});

interface Calls { saveRules: any[][]; saveLabels: any[][]; suggest: number; blur: any[][]; update: any[][]; changed: number; blurred: number }
function stub(over: Record<string, unknown> = {}) {
  const calls: Calls = { saveRules: [], saveLabels: [], suggest: 0, blur: [], update: [], changed: 0, blurred: 0 };
  Object.assign(api as any, {
    getContentCleanupRules: async () => ({ enabled: true, labels: ["ManhuaPlus.com", "Read on ManhuaPlus.com"] }),
    // The real report lists every panel, with the action the engine took: keep, review, blur or exclude.
    getContentCleanupReport: async () => ({ panels: { pn1: { panel_id: "pn1", sequence: 1, action: "blur", reason: "label" }, pn9: { panel_id: "pn9", sequence: 9, action: "exclude", reason: "label" }, pn3: { panel_id: "pn3", sequence: 3, action: "keep", reason: "" }, pn4: { panel_id: "pn4", sequence: 4, action: "keep", reason: "" }, pn5: { panel_id: "pn5", sequence: 5, action: "review", reason: "possible" } } }),
    saveContentCleanupRules: async (...a: any[]) => { calls.saveRules.push(a); return a[1]; },
    savePanelContentLabels: async (...a: any[]) => { calls.saveLabels.push(a); return { labels: a[1] }; },
    getPanelContentSuggestions: async () => { calls.suggest++; return SUGGESTIONS(); },
    blurPanelText: async (...a: any[]) => { calls.blur.push(a); return { success: true, panel_id: a[1], blurred_count: 1 }; },
    updatePanel: async (...a: any[]) => { calls.update.push(a); return {}; },
    getPanelImageUrl: (_p: string, id: string) => `/panel/${id}.png`,
    getTextBlurPreviewUrl: (_p: string, id: string, region: string) => `/preview/${id}/${region}.png`,
    ...over,
  });
  return calls;
}
const text = (d: Document) => d.body.textContent ?? "";
const button = (d: Document | Element, label: string | RegExp) => [...d.querySelectorAll("button")].find((b) => (typeof label === "string" ? b.textContent?.trim() === label : label.test(b.textContent ?? ""))) as HTMLButtonElement | undefined;
const byLabel = (d: Document, label: string) => d.querySelector(`[aria-label="${label}"]`) as any;
async function until(cond: () => boolean, ms = 3000) { for (let i = 0; i < ms / 25 && !cond(); i++) await new Promise((r) => setTimeout(r, 25)); }

const Harness: React.FC<{ initial?: Review | null; calls: Calls }> = ({ initial = null, calls }) => {
  const [review, setReview] = React.useState<Review | null>(initial);
  return <ContentCleanup projectId="p1" panels={PANELS} review={review} onReview={setReview} onPanelsChanged={() => { calls.changed++; }} onBlurred={() => { calls.blurred++; }} />;
};
async function show(calls: Calls, initial: Review | null = null) {
  const view = await mountPage(<Harness initial={initial} calls={calls} />);
  await view.settle();
  await until(() => Boolean(byLabel(view.document, "Shared exclusion labels")));
  return view;
}

test("the saved rules fill the controls, and the report says what was done to the panels it checked", async () => {
  stub();
  const view = await show({} as Calls);
  assert.equal((byLabel(view.document, "Shared exclusion labels") as HTMLTextAreaElement).value, "ManhuaPlus.com\nRead on ManhuaPlus.com");
  await until(() => text(view.document).includes("checked automatically"));
  assert.ok(text(view.document).includes("5 panels were checked automatically: 1 blurred, 1 excluded, 1 need review, 2 kept."), "keep and review are not cleanups");
  await view.cleanup();
});

test("Save for all episodes sends the switch and the labels, one per line without blanks, once", async () => {
  const calls = stub();
  const view = await show(calls);
  const area = byLabel(view.document, "Shared exclusion labels") as HTMLTextAreaElement;
  const { act } = await import("react");
  await act(async () => {
    Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value")!.set!.call(area, "A.com\n\n  B.com  \n");
    area.dispatchEvent(new window.Event("input", { bubbles: true }));
  });
  await view.clickTwice(button(view.document, "Save for all episodes")!);
  await until(() => calls.saveRules.length > 0);
  assert.deepEqual(calls.saveRules, [["p1", { enabled: true, labels: ["A.com", "B.com"] }]]);
  await view.cleanup();
});

test("scanning lists the suggestions with what was checked; if OCR has not run it says to run it first", async () => {
  const calls = stub();
  const view = await show(calls);
  await view.click(button(view.document, "Scan for promotional text")!);
  await until(() => text(view.document).includes("MANHUAPLUS.COM"));
  assert.ok(text(view.document).includes("Checked 24 text regions. 2 suggestions."));
  assert.equal(calls.suggest, 1);
  await view.cleanup();
  stub({ getPanelContentSuggestions: async () => ({ suggestions: [], labels: [], regions_checked: 0, ocr_required: true }) });
  const noOcr = await show(calls);
  await noOcr.click(button(noOcr.document, "Scan for promotional text")!);
  await until(() => text(noOcr.document).includes("Read the text in OCR first"));
  assert.ok(text(noOcr.document).includes("Read the text in OCR first, then scan again to find website links and credits."));
  await noOcr.cleanup();
});

test("Save labels and scan saves the labels, then scans once", async () => {
  const calls = stub();
  const view = await show(calls, SUGGESTIONS());
  await view.clickTwice(button(view.document, "Save labels and scan")!);
  await until(() => calls.saveLabels.length > 0 && calls.suggest > 0);
  assert.deepEqual(calls.saveLabels, [["p1", ["ManhuaPlus.com"]]]);
  assert.equal(calls.suggest, 1);
  await view.cleanup();
});

test("Blur this text blurs that region once, removes the suggestion and tells the screen", async () => {
  const calls = stub();
  const view = await show(calls, SUGGESTIONS());
  await view.clickTwice(button(view.document.querySelector('[data-suggestion="r1"]')!, "Blur this text")!);
  await until(() => calls.blur.length > 0);
  await view.settle();
  assert.deepEqual(calls.blur, [["p1", "pn1", { region_ids: ["r1"] }]]);
  assert.equal(view.document.querySelector('[data-suggestion="r1"]'), null);
  assert.ok(view.document.querySelector('[data-suggestion="r2"]'));
  assert.equal(calls.blurred, 1);
  await view.cleanup();
});

test("Exclude promotional panel excludes the whole panel, keeping its box, and drops its other suggestions", async () => {
  const calls = stub();
  const view = await show(calls, SUGGESTIONS());
  await view.click(button(view.document.querySelector('[data-suggestion="r2"]')!, "Exclude promotional panel")!);
  await until(() => calls.update.length > 0);
  assert.deepEqual(calls.update, [["p1", "pn2", 0, 1100, 1920, 900, "IGNORED"]]);
  assert.equal(calls.changed, 1);
  assert.equal(view.document.querySelector('[data-suggestion="r2"]'), null);
  await view.cleanup();
});

test("excluding a panel also drops the other suggestions that were for that same panel", async () => {
  const calls = stub();
  const two = SUGGESTIONS();
  two.suggestions.push({ region_id: "r3", panel_id: "pn2", page_id: "pg1", text: "CREDITS", bbox: [0, 0, 5, 5], reason: "Credit line" });
  const view = await show(calls, two);
  await view.click(button(view.document.querySelector('[data-suggestion="r2"]')!, "Exclude promotional panel")!);
  await until(() => calls.update.length > 0);
  await view.settle();
  assert.equal(view.document.querySelector('[data-suggestion="r3"]'), null);
  assert.ok(view.document.querySelector('[data-suggestion="r1"]'), "a suggestion on another panel stays");
  await view.cleanup();
});

test("a suggestion for a panel that is gone says so and sends nothing", async () => {
  const calls = stub();
  const gone: Review = { ...SUGGESTIONS(), suggestions: [{ region_id: "rx", panel_id: "missing", page_id: "pg1", text: "X.COM", bbox: [0, 0, 10, 10], reason: "r" }] };
  const view = await show(calls, gone);
  await view.click(button(view.document, "Exclude promotional panel")!);
  assert.ok(text(view.document).includes("That panel is no longer in the project."));
  assert.equal(calls.update.length, 0);
  await view.cleanup();
});

test("Before and after shows the panel and the proposed result, and a failed preview says so", async () => {
  stub();
  const view = await show({} as Calls, SUGGESTIONS());
  const item = () => view.document.querySelector('[data-suggestion="r1"]')!;
  await view.click(button(item(), "Before and after")!);
  assert.ok(item().querySelector('img[src="/panel/pn1.png"]'));
  const after = item().querySelector('img[src="/preview/pn1/r1.png"]')!;
  assert.ok(after);
  await view.fire(after, "error");
  assert.ok(text(view.document).includes("Preview unavailable. Retry before applying cleanup."));
  await view.cleanup();
});

test("a failed blur is explained in words and nothing is removed", async () => {
  stub({ blurPanelText: async () => { throw new Error("Panel image is missing."); } });
  const view = await show({} as Calls, SUGGESTIONS());
  await view.click(button(view.document.querySelector('[data-suggestion="r1"]')!, "Blur this text")!);
  await until(() => text(view.document).includes("Couldn't blur that text"));
  assert.ok(text(view.document).includes("Couldn't blur that text. Panel image is missing."));
  assert.ok(view.document.querySelector('[data-suggestion="r1"]'));
  await view.cleanup();
});

// ---- Detect and review ----
const noSleep = async () => {};
function reviewApi(over: Record<string, unknown> = {}) {
  const log: string[] = [];
  Object.assign(api as any, {
    listOCREngines: async () => { log.push("engines"); return [{ engine_id: "windows_media", is_available: true }]; },
    detectPanels: async () => { log.push("detect"); return { job_id: "j1" }; },
    getJob: async () => { log.push("job"); return { status: "SUCCEEDED" }; },
    cancelJob: async () => { log.push("cancel"); return {}; },
    listPanels: async () => { log.push("panels"); return []; },
    detectTextRegions: async () => { log.push("regions"); return []; },
    ocrSingleRegion: async () => { log.push("ocr"); return {}; },
    getPanelContentSuggestions: async () => { log.push("suggestions"); return SUGGESTIONS(); },
    ...over,
  });
  return log;
}

test("Detect and review runs its steps, hands the suggestions over and reloads the panels", async () => {
  const log = reviewApi();
  let received: Review | null = null;
  let panelsChanged = 0;
  const view = await mountPage(<DetectAndReview projectId="p1" direction="ltr" sleep={noSleep} onReview={(r) => { received = r; }} onPanelsChanged={() => { panelsChanged++; }} />);
  await view.click(button(view.document, "Detect and review")!);
  await until(() => received !== null);
  assert.deepEqual(log, ["engines", "detect", "job", "panels", "regions", "suggestions"]);
  assert.equal(panelsChanged, 1);
  await view.cleanup();
});

test("a failure is shown in words and the button is available again", async () => {
  reviewApi({ listOCREngines: async () => [{ engine_id: "mock_ocr", is_available: true }] });
  const view = await mountPage(<DetectAndReview projectId="p1" direction="ltr" sleep={noSleep} onReview={() => {}} onPanelsChanged={() => {}} />);
  await view.click(button(view.document, "Detect and review")!);
  await until(() => text(view.document).includes("Only a test engine is available."));
  assert.ok(text(view.document).includes("Only a test engine is available. Choose or install a real one in Settings."));
  assert.equal(button(view.document, "Detect and review")!.disabled, false);
  await view.cleanup();
});

test("Cancel stops a running review and cancels its job", async () => {
  const log = reviewApi({ getJob: async () => { log.push("job"); return { status: "RUNNING" }; } });
  const view = await mountPage(<DetectAndReview projectId="p1" direction="ltr" sleep={() => new Promise((r) => setTimeout(r, 20))} onReview={() => {}} onPanelsChanged={() => {}} />);
  await view.click(button(view.document, "Detect and review")!);
  await until(() => log.includes("job"));
  await view.click(button(view.document, "Cancel")!);
  await until(() => log.includes("cancel"));
  assert.ok(log.includes("cancel"));
  await until(() => text(view.document).includes("Detect and review was cancelled."));
  assert.ok(text(view.document).includes("Detect and review was cancelled."));
  await view.cleanup();
});

test("leaving the screen stops the review: no calls after it unmounts", async () => {
  const log = reviewApi({ getJob: async () => { log.push("job"); return { status: "RUNNING" }; } });
  const view = await mountPage(<DetectAndReview projectId="p1" direction="ltr" sleep={() => new Promise((r) => setTimeout(r, 20))} onReview={() => {}} onPanelsChanged={() => {}} />);
  await view.click(button(view.document, "Detect and review")!);
  await until(() => log.includes("job"));
  await view.cleanup();
  const after = log.length;
  await new Promise((r) => setTimeout(r, 300));
  assert.ok(log.length <= after + 2, "at most the call already in flight");
});
