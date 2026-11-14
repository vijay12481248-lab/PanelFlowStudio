import test from "node:test";
import assert from "node:assert/strict";
import type { Page } from "@panelflow/shared-types";
import { canConfirm, clampZoom, defaultViewMode, moveItem, pageIdsAfterMove } from "../pagesModel";

const page = (id: string, status: Page["status"] = "READY", w = 800, h = 1200) => ({ id, status, width: w, height: h, sequence: 1 }) as Page;

test("moveItem returns a new array with the item moved", () => {
  const input = ["a", "b", "c", "d"];
  assert.deepEqual(moveItem(input, 0, 1), ["b", "a", "c", "d"]);
  assert.deepEqual(moveItem(input, 3, 1), ["a", "d", "b", "c"]);
  assert.deepEqual(moveItem(input, 2, 2), ["a", "b", "c", "d"]);
  assert.deepEqual(input, ["a", "b", "c", "d"], "input is not changed");
});

test("moveItem with an index out of range returns an unchanged copy", () => {
  const input = ["a", "b"];
  for (const [from, to] of [[-1, 0], [0, 2], [5, 0], [0, -1]] as const) {
    const out = moveItem(input, from, to);
    assert.deepEqual(out, ["a", "b"]);
    assert.notEqual(out, input);
  }
});

test("pageIdsAfterMove lists the page ids in the new order", () => {
  const pages = [page("a"), page("b"), page("c")];
  assert.deepEqual(pageIdsAfterMove(pages, 2, 0), ["c", "a", "b"]);
});

test("confirming needs a ready page; failed pages do not block it", () => {
  assert.deepEqual(canConfirm([]), { ok: false, reason: "No pages are ready yet. Go back to Acquire." });
  assert.equal(canConfirm([page("a", "FAILED"), page("b", "PENDING")]).ok, false);
  assert.deepEqual(canConfirm([page("a", "FAILED"), page("b")]), { ok: true, reason: null });
});

test("tall strips open fit-width, normal pages open fit-page", () => {
  assert.equal(defaultViewMode(page("a", "READY", 800, 1200)), "fit-page");
  assert.equal(defaultViewMode(page("a", "READY", 800, 1440)), "fit-page");
  assert.equal(defaultViewMode(page("a", "READY", 800, 1441)), "fit-width");
  assert.equal(defaultViewMode(page("a", "READY", 0, 0)), "fit-page");
});

test("zoom steps by 25 and stays between 25 and 400", () => {
  assert.equal(clampZoom(100, 25), 125);
  assert.equal(clampZoom(100, -25), 75);
  assert.equal(clampZoom(25, -25), 25);
  assert.equal(clampZoom(400, 25), 400);
});
