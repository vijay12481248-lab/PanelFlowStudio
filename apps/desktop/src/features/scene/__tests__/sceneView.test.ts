import test from "node:test";
import assert from "node:assert/strict";
import type { SceneCrossCheck, SceneRun } from "@panelflow/api-client";
import { analysisOverdue, choiceOptions, confidenceLabel, humanValue, itemRows, ownerCanSubmit, planMatch, planSummary, waitingFirst } from "../sceneView";

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
  const base = { liked: null as number | null, agrees: false, note: "", goodTags: [] as string[], wrongTags: [] as string[], choices: {} as Record<string, string> };
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


const PLAN = { scene_type: "fight", camera: { angle: "low", distance: "medium" }, actors: [
  { id: "villain", side: "right", action_state: "blocking" }, { id: "hero", side: "left", action_state: "striking" }] };

test("the plan is compared with what the judges saw, person by person from the left", () => {
  assert.deepEqual(planMatch(PLAN, "camera", "looks_up"), { expected: "low angle (looking up)", match: true });
  assert.equal(planMatch(PLAN, "camera", "level").match, false);
  assert.deepEqual(planMatch(PLAN, "people", "2"), { expected: "2", match: true });
  assert.equal(planMatch(PLAN, "people", "3").match, false);
  assert.deepEqual(planMatch(PLAN, "action:0", "striking"), { expected: "striking", match: true }); // the hero stands on the left, the plan lists him second
  assert.equal(planMatch(PLAN, "action:1", "striking").match, false);
  assert.equal(planMatch(PLAN, "action:5", "x").match, null);
  assert.equal(planMatch(PLAN, "camera", null).match, null);
  assert.equal(planMatch({}, "camera", "level").match, null);
});

test("feelings of the same family count as the planned state", () => {
  const plan = { scene_type: "emotion", camera: { angle: "eye_level" }, actors: [{ id: "girl", side: "center", action_state: "grieving" }] };
  assert.equal(planMatch(plan, "action:0", "lost").match, true);
  assert.equal(planMatch(plan, "action:0", "joyful").match, false);
});

test("a review request is overdue when the judges never reported in ten minutes", () => {
  const run = (created_at: string, analysis: unknown) => ({ created_at, analysis } as unknown as SceneRun);
  const now = Date.parse("2026-11-14T12:00:00Z");
  assert.equal(analysisOverdue(run("2026-11-14T11:49:00", null), now), true); // stored without a zone: UTC
  assert.equal(analysisOverdue(run("2026-11-14T11:55:00", null), now), false);
  assert.equal(analysisOverdue(run("2026-11-14T11:00:00", { id: "a" }), now), false); // it has an analysis
});

test("disputed rows offer each judge's distinct answer as a choice", () => {
  const rows = itemRows(cc);
  assert.deepEqual(choiceOptions(rows[0]).map((c) => c.value), ["level", "looks_up"]);
  assert.deepEqual(choiceOptions(rows[1]), []); // agreed: nothing to settle
});

test("choosing an answer for a disputed item counts as a reason to submit", () => {
  const base = { liked: 40, agrees: false, note: "", goodTags: [] as string[], wrongTags: [] as string[], choices: { camera: "level" } };
  assert.equal(ownerCanSubmit(base), true);
});
