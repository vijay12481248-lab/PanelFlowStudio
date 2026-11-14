import test from "node:test";
import assert from "node:assert/strict";
import type { SceneCrossCheck, SceneRun } from "@panelflow/api-client";
import { confidenceLabel, humanValue, itemRows, ownerCanSubmit, planSummary, waitingFirst } from "../sceneView";

const cc: SceneCrossCheck = {
  judges: ["qwen3.5:9b", "qwen3-vl-8b"], single_judge: false, seconds: 9,
  items: [
    { key: "camera", status: "disputed", value: null, confidence: 0.3, suspect_flips: [], answers: {
      "qwen3.5:9b": { round1: "level", round2: "level", evidence: "the horizon is flat" },
      "qwen3-vl-8b": { round1: "looks_up", round2: "looks_up", evidence: "faces seen from below" } } },
    { key: "people", status: "agreed", value: "2", confidence: 0.9, suspect_flips: [], answers: {} },
    { key: "action:1", status: "resolved", value: "blocking", confidence: 0.7, suspect_flips: ["qwen3-vl-8b"], answers: {
      "qwen3.5:9b": { round1: "blocking", round2: null, evidence: "arms raised" },
      "qwen3-vl-8b": { round1: "striking", round2: "blocking", evidence: "ok" } } },
  ],
};

test("rows are labelled in plain words and carry the percentage", () => {
  const rows = itemRows(cc);
  assert.deepEqual(rows.map((r) => r.label), ["Camera angle", "People in the picture", "Person 2 (from the left)"]);
  assert.equal(rows[1].confidencePct, 90);
  assert.equal(rows[1].statusText, "Both judges agree");
  assert.equal(rows[2].statusText, "Settled after a second look");
});

test("a disputed row carries both judges' wording and is highlighted", () => {
  const [camera] = itemRows(cc);
  assert.equal(camera.highlight, true);
  assert.equal(camera.statusText, "Judges still disagree: your call");
  assert.deepEqual(camera.perJudge.map((j) => [j.judge, j.round1, j.evidence]), [["qwen3.5:9b", "level", "the horizon is flat"], ["qwen3-vl-8b", "looks_up", "faces seen from below"]]);
  assert.equal(itemRows(cc)[1].highlight, false);
});

test("a suspect flip is listed on the row", () => {
  assert.deepEqual(itemRows(cc)[2].flipped, ["qwen3-vl-8b"]);
});

test("no analysis gives no rows", () => {
  assert.deepEqual(itemRows(undefined), []);
  assert.deepEqual(itemRows(null), []);
  assert.deepEqual(itemRows({} as SceneCrossCheck), []);
});

test("confidence labels switch at 0.8 and 0.5", () => {
  assert.equal(confidenceLabel(0.79), "medium");
  assert.equal(confidenceLabel(0.8), "high");
  assert.equal(confidenceLabel(0.49), "low");
  assert.equal(confidenceLabel(0.5), "medium");
});

test("camera values read as plain words", () => {
  assert.equal(humanValue("camera", "looks_up"), "looking up (low angle)");
  assert.equal(humanValue("camera", "level"), "level");
  assert.equal(humanValue("people", "2"), "2");
  assert.equal(humanValue("action:0", "striking"), "striking");
  assert.equal(humanValue("camera", null), "unclear");
});

test("the owner can submit once liked is chosen and there is a reason", () => {
  const base = { liked: null as number | null, agrees: false, note: "", goodTags: [] as string[], wrongTags: [] as string[] };
  assert.equal(ownerCanSubmit(base), false);
  assert.equal(ownerCanSubmit({ ...base, liked: 70 }), false); // chosen but no reason yet
  assert.equal(ownerCanSubmit({ ...base, liked: 70, agrees: true }), true);
  assert.equal(ownerCanSubmit({ ...base, liked: 0, note: "  nope  " }), true);
  assert.equal(ownerCanSubmit({ ...base, liked: 50, wrongTags: ["camera"] }), true);
  assert.equal(ownerCanSubmit({ ...base, liked: 50, note: "   " }), false);
  assert.equal(ownerCanSubmit({ ...base, agrees: true }), false); // no liked value
});

test("the plan reads as one sentence", () => {
  const plan = { camera: { angle: "low", distance: "medium" }, light: { direction: "back" }, actors: [
    { id: "hero", side: "left", action_state: "striking" }, { id: "villain", side: "right", action_state: "blocking" }] };
  assert.equal(planSummary(plan), "low angle, medium shot, hero on the left striking, villain on the right blocking, light from behind");
  assert.equal(planSummary({}), "");
});

test("the first waiting run is the first pending one", () => {
  const run = (id: string, review_state: SceneRun["review_state"]) => ({ id, review_state } as SceneRun);
  assert.equal(waitingFirst([run("a", "reviewed"), run("b", "pending"), run("c", "pending")])?.id, "b");
  assert.equal(waitingFirst([run("a", "reviewed")]), null);
});
