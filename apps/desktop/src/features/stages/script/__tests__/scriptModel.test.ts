import test from "node:test";
import assert from "node:assert/strict";
import type { ScriptSegment, ScriptValidationReport, StoryboardPanelRef, VideoScript } from "@panelflow/shared-types";
import { normalizeCharacters } from "../../story/storyModel";
import {
  CAMERA_MOTIONS, EMOTIONS, PROFILES, SEGMENT_ACTIONS, canApproveScript, coverageLabel, isScriptApproved, issueFor, reasonsFor, speakerName,
  unsupportedIssues, unsupportedSegmentIds, withCameraMotion,
} from "../scriptModel";

const report = (over: Partial<ScriptValidationReport> = {}) => ({
  script_id: "sc1", total_segments: 4, supported_segments: 2, weakly_supported_segments: 1, unsupported_segments: 1, coverage_score: 0.753, passed: false,
  issues: [
    { segment_id: "s2", status: "UNSUPPORTED", text: "He flew", reasons: ["No panel shows flying."] },
    { segment_id: "s3", status: "WEAKLY_SUPPORTED", text: "He smiled" },
    { segment_id: "s4", status: "SUPPORTED", reasons: ["Only partly visible."] },
    { segment_id: "s5", status: "UNSUPPORTED", issues: ["Legacy reason field."] },
  ],
  ...over,
}) as ScriptValidationReport;

test("the issue for a segment is an unsupported status or any reasons, and nothing else", () => {
  const r = report();
  assert.equal(issueFor(r, "s2")?.text, "He flew");
  assert.equal(issueFor(r, "s3"), null, "weakly supported with no reasons is not an issue");
  assert.equal(issueFor(r, "s4")?.segment_id, "s4", "reasons make it an issue even when supported");
  assert.equal(issueFor(r, "nope"), null);
  assert.equal(issueFor(null, "s2"), null);
});

test("unsupported issues and their ids", () => {
  const r = report();
  assert.deepEqual(unsupportedIssues(r).map((i) => i.segment_id), ["s2", "s4", "s5"]);
  assert.deepEqual([...unsupportedSegmentIds(r)].sort(), ["s2", "s4", "s5"]);
  assert.deepEqual(unsupportedIssues(null), []);
  assert.equal(unsupportedSegmentIds(null).size, 0);
});

test("reasons come from reasons, then issues, then one generic sentence", () => {
  assert.deepEqual(reasonsFor({ reasons: ["a", "b"] }), ["a", "b"]);
  assert.deepEqual(reasonsFor({ reasons: [], issues: ["old"] }), ["old"]);
  assert.equal(reasonsFor({}).length, 1);
  assert.ok(reasonsFor({})[0].length > 20);
});

test("coverage says Not checked without a report and never 100 percent", () => {
  assert.equal(coverageLabel(null), "Not checked");
  assert.equal(coverageLabel(report({ coverage_score: 0.753 })), "75%");
  assert.equal(coverageLabel(report({ coverage_score: 1 })), "100%");
  assert.equal(coverageLabel(report({ coverage_score: 0 })), "0%");
});

const seg = (over: Partial<ScriptSegment>) => ({ segment_id: "s", type: "DIALOGUE", speaker_character_id: null, ...over }) as ScriptSegment;
const chars = normalizeCharacters([{ id: "c1", display_name: "Shangguan Yulin", canonical_name: null }]);

test("a speaker is the narrator, a named character, or Speaker, never a raw id", () => {
  assert.equal(speakerName(seg({ type: "NARRATOR" }), chars), "Narrator");
  assert.equal(speakerName(seg({ speaker_character_id: "c1" }), chars), "Shangguan Yulin");
  assert.equal(speakerName(seg({ speaker_character_id: "ghost9" }), chars), "Speaker");
  assert.equal(speakerName(seg({}), chars), "Speaker");
});

const script = (status: VideoScript["status"] = "DRAFT") => ({ script_id: "sc1", status, segments: [] }) as unknown as VideoScript;

test("approving a script needs a script, no change in flight, and no failed validation, and says why not", () => {
  assert.deepEqual(canApproveScript({ script: null, report: null, busy: false }), { ok: false, reason: "Generate a script first." });
  assert.deepEqual(canApproveScript({ script: script(), report: null, busy: true }), { ok: false, reason: "Wait for the current change to finish." });
  assert.equal(canApproveScript({ script: script(), report: report({ passed: false, unsupported_segments: 2 }), busy: false }).reason, "2 unsupported lines must be fixed first.");
  assert.equal(canApproveScript({ script: script(), report: report({ passed: false, unsupported_segments: 1 }), busy: false }).reason, "1 unsupported line must be fixed first.");
  assert.equal(canApproveScript({ script: script(), report: report({ passed: false, unsupported_segments: 0 }), busy: false }).ok, false);
  assert.deepEqual(canApproveScript({ script: script(), report: report({ passed: true, unsupported_segments: 0 }), busy: false }), { ok: true, reason: null });
  assert.deepEqual(canApproveScript({ script: script(), report: null, busy: false }), { ok: true, reason: null }, "no report: the engine decides");
});

test("a script counts as approved from SCRIPT_APPROVED onward or when its status says so", () => {
  assert.equal(isScriptApproved("STORY_APPROVED", "DRAFT"), false);
  assert.equal(isScriptApproved("SCRIPT_GENERATED", undefined), false);
  assert.equal(isScriptApproved("SCRIPT_APPROVED", "DRAFT"), true);
  assert.equal(isScriptApproved("RENDERED", undefined), true);
  assert.equal(isScriptApproved("SCRIPT_GENERATED", "APPROVED"), true);
});

test("changing one panel's camera motion keeps its other camera fields and leaves the rest alone", () => {
  const panels = [
    { panel_id: "a", camera_motion: { type: "SLOW_PUSH", intensity: 0.5 } },
    { panel_id: "b", camera_motion: { type: "PAN", intensity: 0.2 } },
    { panel_id: "c" },
  ] as unknown as StoryboardPanelRef[];
  const out = withCameraMotion(panels, 1, "STATIC");
  assert.deepEqual(out[1].camera_motion, { type: "STATIC", intensity: 0.2 });
  assert.equal(out[0], panels[0]);
  assert.equal((panels[1].camera_motion as any).type, "PAN", "the input is not changed");
  assert.deepEqual(withCameraMotion(panels, 2, "IMPACT")[2].camera_motion, { type: "IMPACT" });
  const copy = withCameraMotion(panels, 9, "STATIC");
  assert.deepEqual(copy, panels);
  assert.notEqual(copy, panels);
});

test("the line actions are the engine's ten, and only Remove and Merge with next ask first", () => {
  assert.deepEqual(SEGMENT_ACTIONS.map((a) => a.id), ["regenerate", "shorten", "expand", "more_drama", "less_drama", "split", "merge_next", "move_up", "move_down", "remove"]);
  assert.deepEqual(SEGMENT_ACTIONS.filter((a) => a.confirm).map((a) => a.id), ["merge_next", "remove"]);
  assert.equal(new Set(SEGMENT_ACTIONS.map((a) => a.label)).size, 10, "labels are distinct");
});

test("the choice lists", () => {
  assert.deepEqual([...EMOTIONS], ["NEUTRAL", "DETERMINED", "TENSE", "CALM", "JOYFUL", "SAD", "ANGRY", "FEARFUL", "SURPRISED"]);
  assert.deepEqual(PROFILES.map((p) => p.value), ["FAITHFUL", "CONDENSED", "DRAMATIC_NARRATION", "ACCESSIBLE_RECAP"]);
  assert.deepEqual(CAMERA_MOTIONS.map((c) => c.value), ["SLOW_PUSH", "CHARACTER_FOCUS", "REACTION_CLOSEUP", "IMPACT", "PAN", "STATIC"]);
});
