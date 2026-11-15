import test from "node:test";
import assert from "node:assert/strict";
import type { Page, Panel, ProjectHistoryState } from "@panelflow/shared-types";
import { canConfirmPanels, globalReorder, historyAvailability, isPanelsConfirmed, pageCounts, pageWindow, panelStatus, panelsOnPage, sortPanels } from "../panelsModel";

const page = (id: string, sequence: number) => ({ id, sequence }) as Page;
const panel = (id: string, pageId: string, pageSeq: number, status = "DETECTED") => ({ id, page_id: pageId, page_sequence: pageSeq, status, x: 0, y: 0, width: 100, height: 100 }) as Panel;

test("statuses are words with a tone", () => {
  assert.deepEqual(panelStatus("DETECTED"), { word: "Detected", tone: "accent" });
  assert.deepEqual(panelStatus("CONFIRMED"), { word: "Confirmed", tone: "ok" });
  assert.deepEqual(panelStatus("APPROVED"), { word: "Approved", tone: "ok" });
  assert.deepEqual(panelStatus("NEEDS_REVIEW"), { word: "Needs review", tone: "warn" });
  assert.deepEqual(panelStatus("MANUAL"), { word: "Added by hand", tone: "accent" });
  assert.deepEqual(panelStatus("IGNORED"), { word: "Excluded", tone: "neutral" });
  assert.deepEqual(panelStatus("SOMETHING_NEW"), { word: "Something new", tone: "neutral" });
});

test("a page's panels come in reading order", () => {
  const all = [panel("c", "p1", 3), panel("a", "p1", 1), panel("x", "p2", 1), panel("b", "p1", 2)];
  assert.deepEqual(panelsOnPage(all, "p1").map((p) => p.id), ["a", "b", "c"]);
  assert.deepEqual(panelsOnPage(all, "none"), []);
});

test("all panels sort by page, then by their place on the page", () => {
  const pages = [page("p2", 2), page("p1", 1)];
  const all = [panel("x", "p2", 1), panel("b", "p1", 2), panel("a", "p1", 1), panel("orphan", "gone", 1)];
  assert.deepEqual(sortPanels(all, pages).map((p) => p.id), ["a", "b", "x", "orphan"], "a panel of an unknown page goes last");
});

test("confirming needs a panel that is not excluded", () => {
  assert.deepEqual(canConfirmPanels([]), { ok: false, reason: "Detect or add at least one panel first." });
  assert.equal(canConfirmPanels([panel("a", "p", 1, "IGNORED")]).ok, false);
  assert.deepEqual(canConfirmPanels([panel("a", "p", 1, "IGNORED"), panel("b", "p", 2)]), { ok: true, reason: null });
});

test("panels are confirmed from PANELS_DETECTED onward", () => {
  for (const s of ["NEW", "ACQUIRED", "NORMALIZED"] as const) assert.equal(isPanelsConfirmed(s), false, s);
  for (const s of ["PANELS_DETECTED", "OCR_COMPLETE", "RENDERED"] as const) assert.equal(isPanelsConfirmed(s), true, s);
});

test("panel counts per page leave out excluded panels and count empty pages", () => {
  const pages = [page("p1", 1), page("p2", 2), page("p3", 3)];
  const all = [panel("a", "p1", 1), panel("b", "p1", 2, "IGNORED"), panel("c", "p2", 1)];
  assert.deepEqual(pageCounts(all, pages), { perPage: { p1: 1, p2: 1, p3: 0 }, empty: 1 });
});

const history = (over: Partial<ProjectHistoryState> = {}) => ({ canUndo: true, canRedo: false, busy: false, recoveryRequired: false, conflicted: false, undoLabel: "Move panel", redoLabel: null, ...over }) as ProjectHistoryState;

test("undo and redo are available from the engine's history and blocked, with a sentence, when it is in trouble", () => {
  assert.deepEqual(historyAvailability(history(), false), { canUndo: true, canRedo: false, blocked: null });
  assert.deepEqual(historyAvailability(null, false), { canUndo: false, canRedo: false, blocked: null });
  assert.equal(historyAvailability(history(), true).canUndo, false, "not while another change is running");
  const conflicted = historyAvailability(history({ conflicted: true }), false);
  assert.equal(conflicted.canUndo, false);
  assert.equal(conflicted.blocked, "The project changed somewhere else. Reload the page before undoing.");
  const recovery = historyAvailability(history({ recoveryRequired: true }), false);
  assert.equal(recovery.blocked, "The undo history needs recovery. Reload the page.");
});

test("reordering a page keeps every other panel where it was in the whole project's order", () => {
  const pages = [page("p1", 1), page("p2", 2)];
  const all = sortPanels([panel("a", "p1", 1), panel("b", "p1", 2), panel("c", "p1", 3), panel("x", "p2", 1), panel("y", "p2", 2)], pages);
  assert.deepEqual(globalReorder(all, "p1", ["c", "a", "b"]), ["c", "a", "b", "x", "y"]);
  assert.deepEqual(globalReorder(all, "p2", ["y", "x"]), ["a", "b", "c", "y", "x"], "page 1 is not pushed after page 2's panels");
});

test("the strip shows a window of pages around the selected one", () => {
  assert.deepEqual(pageWindow(10, 4, 40), { start: 0, end: 10 });
  assert.deepEqual(pageWindow(300, 0, 40), { start: 0, end: 40 });
  assert.deepEqual(pageWindow(300, 150, 40), { start: 130, end: 170 });
  assert.deepEqual(pageWindow(300, 299, 40), { start: 260, end: 300 });
  assert.deepEqual(pageWindow(0, 0, 40), { start: 0, end: 0 });
});
