import assert from "node:assert/strict";
import test from "node:test";
import { readPanelDrag, panelInsertionIndex } from "../panelDrag";

test("panel payload decoder validates, deduplicates and preserves batch reading order", () => {
  const a = { panelId: "a", pageId: "p", imageUrl: "a.png" };
  const b = { panelId: "b", pageId: "p", imageUrl: "b.png" };
  assert.deepEqual(readPanelDrag(JSON.stringify({ ...a, panels: [a, b, a, null, { bad: true }] })), [a, b]);
  assert.deepEqual(readPanelDrag("not JSON"), []);
  assert.deepEqual(readPanelDrag(JSON.stringify(a)), [a]);
  assert.deepEqual(readPanelDrag('{"panels":{}}'), []);
});

test("pointer chooses beginning, between clips, end, and fixed timeline gaps", () => {
  const scenes = [{ start_time_sec: 0, duration_sec: 6 }, { start_time_sec: 10, duration_sec: 4 }];
  for (const [time, expected] of [[-1, 0], [2, 0], [4, 1], [8, 1], [11, 1], [13, 2], [30, 2]]) {
    assert.equal(panelInsertionIndex(scenes, time), expected);
  }
  assert.equal(panelInsertionIndex([], 10), 0);
});
