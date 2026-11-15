import test from "node:test";
import assert from "node:assert/strict";
import type { PipelineStage, Project } from "@panelflow/shared-types";
import { STAGES } from "../../../app/routes";
import { STAGE_LABEL, stageSteps } from "../stageModel";

const project = (current_stage: PipelineStage, over: Partial<Project> = {}) =>
  ({ id: "p1", current_stage, rights_status: "AUTHORIZED_WEB", stale_stages: [], ...over }) as Pick<Project, "id" | "current_stage" | "rights_status" | "stale_stages">;
const statuses = (p: ReturnType<typeof project>) => Object.fromEntries(stageSteps(p).map((s) => [s.id, s.status]));

test("the steps are the ten stages in order with plain labels", () => {
  const steps = stageSteps(project("NEW"));
  assert.deepEqual(steps.map((s) => s.id), [...STAGES]);
  assert.deepEqual(steps.map((s) => s.label), ["Source", "Pages", "Panels", "OCR", "Story", "Script", "Audio", "Motion", "Render", "Publish"]);
  assert.equal(STAGE_LABEL.ocr, "OCR");
});

const EXPECTED_ACTIVE: Array<[PipelineStage, string]> = [
  ["NEW", "acquire"], ["RIGHTS_APPROVED", "acquire"], ["ACQUIRED", "pages"], ["NORMALIZED", "panels"], ["PANELS_DETECTED", "panels"],
  ["OCR_COMPLETE", "ocr"], ["OCR_APPROVED", "ocr"], ["STORY_ANALYZED", "story"], ["STORY_APPROVED", "story"], ["SCRIPT_GENERATED", "script"],
  ["SCRIPT_APPROVED", "script"], ["VOICE_GENERATED", "audio"], ["AUDIO_APPROVED", "audio"], ["SHOT_PLAN_GENERATED", "motion"],
  ["MOTION_APPROVED", "motion"], ["RENDERED", "render"], ["QA_APPROVED", "publish"],
];

for (const [stage, active] of EXPECTED_ACTIVE) {
  test(`at ${stage} exactly ${active} is in progress, earlier stages are done and later ones not started`, () => {
    const s = statuses(project(stage));
    assert.deepEqual(Object.entries(s).filter(([, v]) => v === "active").map(([k]) => k), [active]);
    const at = STAGES.indexOf(active as (typeof STAGES)[number]);
    STAGES.forEach((id, i) => assert.equal(s[id], i < at ? "done" : i === at ? "active" : "upcoming", `${id} at ${stage}`));
  });
}

test("an exported project has every step done", () => {
  assert.ok(Object.values(statuses(project("EXPORTED"))).every((v) => v === "done"));
});

test("a stale stage says stale even when it was done, and leaves the others alone", () => {
  const s = statuses(project("SCRIPT_APPROVED", { stale_stages: ["audio"] }));
  assert.equal(s.audio, "stale");
  assert.equal(s.script, "active");
  assert.equal(s.ocr, "done");
  const done = statuses(project("RENDERED", { stale_stages: ["motion"] }));
  assert.equal(done.motion, "stale", "stale beats done");
  assert.equal(done.audio, "done");
});

test("unknown rights block Render and Publish until they are past, and nothing else", () => {
  const unknown = { rights_status: "UNKNOWN" } as Partial<Project>;
  const s = statuses(project("MOTION_APPROVED", unknown));
  assert.equal(s.render, "blocked");
  assert.equal(s.publish, "blocked");
  assert.deepEqual(Object.entries(s).filter(([, v]) => v === "blocked").map(([k]) => k), ["render", "publish"]);
  assert.equal(statuses(project("NEW", unknown)).render, "blocked", "blocked even far from the stage");
  const exported = statuses(project("EXPORTED", unknown));
  assert.equal(exported.render, "done");
  assert.equal(exported.publish, "done");
});

test("rights values other than UNKNOWN never block", () => {
  for (const rights of ["AUTHORIZED_WEB", "LOCAL_DIRECTORY", "PUBLIC_DOMAIN", "USER_OWNED"]) {
    assert.ok(!Object.values(statuses(project("MOTION_APPROVED", { rights_status: rights as Project["rights_status"] }))).includes("blocked"), rights);
  }
});

test("stale wins over blocked", () => {
  const s = statuses(project("MOTION_APPROVED", { rights_status: "UNKNOWN" as Project["rights_status"], stale_stages: ["render"] }));
  assert.equal(s.render, "stale");
});

test("every step that is not upcoming links, plus the next one, and later steps do not", () => {
  const steps = stageSteps(project("OCR_COMPLETE"));
  const linked = steps.filter((s) => s.href).map((s) => s.id);
  assert.deepEqual(linked, ["acquire", "pages", "panels", "ocr", "story"]);
  assert.equal(steps.find((s) => s.id === "ocr")!.href, "/projects/p1/ocr");
  const blocked = stageSteps(project("NEW", { rights_status: "UNKNOWN" as Project["rights_status"] }));
  assert.deepEqual(blocked.filter((s) => s.href).map((s) => s.id), ["acquire", "pages", "render", "publish"]);
  assert.deepEqual(stageSteps(project("EXPORTED")).filter((s) => !s.href), []);
});
