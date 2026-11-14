import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { ENGINES, HISTORY, button, engineSelect, job, project, region, show, stub, text, until } from "./ocrFixtures";

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
