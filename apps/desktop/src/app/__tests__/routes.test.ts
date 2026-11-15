import test from "node:test";
import assert from "node:assert/strict";
import type { PipelineStage } from "@panelflow/shared-types";
import { STAGES, isChronoFlowProject, nextStage, paths, prevStage, stageForProject, type Stage } from "../routes";

// The expected values below are what the old App.tsx handleOpenProject did, stage by stage.
const LEGACY: Array<[PipelineStage, Stage, Stage]> = [
  // [current_stage, without visual_storytelling, with visual_storytelling]
  ["NEW", "acquire", "acquire"],
  ["RIGHTS_APPROVED", "acquire", "acquire"],
  ["ACQUIRED", "pages", "pages"],
  ["NORMALIZED", "ocr", "story"],
  ["PANELS_DETECTED", "ocr", "story"],
  ["OCR_COMPLETE", "story", "story"],
  ["OCR_APPROVED", "story", "story"],
  ["STORY_ANALYZED", "script", "script"],
  ["STORY_APPROVED", "script", "script"],
  ["SCRIPT_GENERATED", "audio", "audio"],
  ["SCRIPT_APPROVED", "audio", "audio"],
  ["VOICE_GENERATED", "motion", "motion"],
  ["AUDIO_APPROVED", "motion", "motion"],
  ["SHOT_PLAN_GENERATED", "motion", "motion"],
  ["MOTION_APPROVED", "render", "render"],
  ["RENDERED", "render", "render"],
  ["QA_APPROVED", "render", "render"],
  ["EXPORTED", "render", "render"],
];

for (const [current_stage, plain, visual] of LEGACY) {
  test(`stageForProject(${current_stage}) matches the old screen routing`, () => {
    assert.equal(stageForProject({ current_stage, settings: {} }), plain);
    assert.equal(stageForProject({ current_stage, settings: { visual_storytelling: true } }), visual);
  });
}

test("isChronoFlowProject recognises both ways a project is marked", () => {
  assert.equal(isChronoFlowProject({ source_type: "CHRONOFLOW_AI" as any, settings: {} }), true);
  assert.equal(isChronoFlowProject({ source_type: "MANGA" as any, settings: { workflow_type: "chronoflow" } }), true);
  assert.equal(isChronoFlowProject({ source_type: "MANGA" as any, settings: {} }), false);
});

test("paths encode ids and build every destination", () => {
  assert.equal(paths.stage("a b", "ocr"), "/projects/a%20b/ocr");
  assert.equal(paths.project("p1"), "/projects/p1");
  assert.equal(paths.editor("p1"), "/editor/p1");
  assert.equal(paths.home(), "/home");
  assert.equal(paths.jobs(), "/jobs");
  assert.equal(paths.create(), "/create");
  assert.equal(paths.create("stories"), "/create/stories");
  assert.equal(paths.chronoflow({}), "/create/chronoflow");
  assert.equal(paths.chronoflow({ projectId: "p1" }), "/create/chronoflow/p1");
  assert.equal(paths.chronoflow({ jobId: "j 1" }), "/create/chronoflow/job/j%201");
  assert.equal(paths.library("audio"), "/library/audio");
  assert.equal(paths.settings("providers"), "/settings/providers");
  assert.equal(paths.settings(), "/settings/engine");
});

test("nextStage and prevStage walk STAGES and stop at the ends", () => {
  assert.equal(nextStage("render"), "publish");
  assert.equal(nextStage("publish"), null);
  assert.equal(prevStage("acquire"), null);
  assert.equal(prevStage("pages"), "acquire");
  assert.equal(STAGES.length, 10);
});
