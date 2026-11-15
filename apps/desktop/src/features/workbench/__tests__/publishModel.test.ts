import test from "node:test";
import assert from "node:assert/strict";
import type { PipelineStage, Project, RenderJob, RenderValidationReport, YouTubePackagingData } from "@panelflow/shared-types";
import { canHandOff, chaptersText, durationLabel, latestRender, packagingBundle, publishChecks } from "../publishModel";

const project = (current_stage: PipelineStage, over: Partial<Project> = {}) =>
  ({ current_stage, rights_status: "AUTHORIZED_WEB", stale_stages: [], ...over }) as Pick<Project, "current_stage" | "rights_status" | "stale_stages">;

const report = (over: Partial<RenderValidationReport> = {}): RenderValidationReport => ({
  is_valid: true, video_valid: true, audio_valid: true, sync_valid: true, black_frames_count: 0, timeline_gaps_count: 0, clipping_samples_count: 0, duration_sec: 370, warnings: [], ...over,
});
const render = (id: string, status: RenderJob["status"], created_at: string, over: Partial<RenderJob> = {}): RenderJob =>
  ({ render_id: id, project_id: "p1", status, current_stage: "", progress: 1, frames_done: 0, frames_total: 0, output_profile: "youtube_1080p", output_path: "", created_at, ...over }) as RenderJob;

const states = (p: ReturnType<typeof project>, renders: RenderJob[], validation?: RenderValidationReport) =>
  Object.fromEntries(publishChecks({ project: p, renders, validation }).map((c) => [c.id, c.state]));

test("the five checks come in a fixed order", () => {
  assert.deepEqual(publishChecks({ project: project("NEW"), renders: [] }).map((c) => c.id), ["rights", "approved", "render", "fresh", "valid"]);
});

test("everything passes for an approved project with a valid, current render", () => {
  const renders = [render("r1", "COMPLETE", "2026-11-08T10:00:00Z", { validation_report: report() })];
  const checks = publishChecks({ project: project("QA_APPROVED"), renders });
  assert.ok(checks.every((c) => c.state === "pass"), JSON.stringify(checks));
  assert.equal(canHandOff(checks), true);
});

test("unknown rights fail the rights check and hold hand-off", () => {
  const checks = publishChecks({ project: project("QA_APPROVED", { rights_status: "UNKNOWN" as Project["rights_status"] }), renders: [render("r1", "COMPLETE", "2026-11-08T10:00:00Z", { validation_report: report() })] });
  assert.equal(checks[0].state, "fail");
  assert.equal(checks[0].detail, "Rights are unknown, so publishing is held");
  assert.equal(canHandOff(checks), false);
});

test("a render that has not been approved is waiting, not failed, and copying is still allowed", () => {
  const checks = publishChecks({ project: project("RENDERED"), renders: [render("r1", "COMPLETE", "2026-11-08T10:00:00Z", { validation_report: report() })] });
  assert.equal(checks.find((c) => c.id === "approved")!.state, "pending");
  assert.equal(checks.find((c) => c.id === "approved")!.detail, "Approve the render first");
  assert.equal(canHandOff(checks), true);
});

test("with no render at all the render, freshness and validity checks are waiting", () => {
  const s = states(project("MOTION_APPROVED"), []);
  assert.deepEqual([s.render, s.fresh, s.valid], ["pending", "pending", "pending"]);
  assert.equal(publishChecks({ project: project("MOTION_APPROVED"), renders: [] })[2].detail, "Render the video first");
});

test("the newest render decides: a newer failure fails the check with its message even if an older render finished", () => {
  const renders = [render("old", "COMPLETE", "2026-11-07T10:00:00Z", { validation_report: report() }), render("new", "FAILED", "2026-11-08T10:00:00Z", { error_message: "Out of GPU memory" })];
  const check = publishChecks({ project: project("RENDERED"), renders }).find((c) => c.id === "render")!;
  assert.equal(check.state, "fail");
  assert.ok(check.detail.includes("Out of GPU memory"));
});

test("a render in progress is waiting", () => {
  const check = publishChecks({ project: project("RENDERED"), renders: [render("r", "ENCODING", "2026-11-08T10:00:00Z")] }).find((c) => c.id === "render")!;
  assert.equal(check.state, "pending");
  assert.equal(check.detail, "A render is running");
});

test("a stale render fails the freshness check", () => {
  const renders = [render("r", "COMPLETE", "2026-11-08T10:00:00Z", { validation_report: report() })];
  const check = publishChecks({ project: project("QA_APPROVED", { stale_stages: ["render"] }), renders }).find((c) => c.id === "fresh")!;
  assert.equal(check.state, "fail");
  assert.equal(check.detail, "Audio or motion changed after this render. Render again.");
});

test("validity comes from the render's report, or from a separately loaded one", () => {
  const renders = [render("r", "COMPLETE", "2026-11-08T10:00:00Z")];
  assert.equal(states(project("QA_APPROVED"), renders).valid, "pending");
  assert.equal(states(project("QA_APPROVED"), renders, report()).valid, "pass");
  const bad = publishChecks({ project: project("QA_APPROVED"), renders, validation: report({ is_valid: false, warnings: ["Black frames at 0:12", "Audio clips at 1:02"] }) }).find((c) => c.id === "valid")!;
  assert.equal(bad.state, "fail");
  assert.equal(bad.detail, "Black frames at 0:12");
  const warned = publishChecks({ project: project("QA_APPROVED"), renders, validation: report({ warnings: ["a", "b", "c"] }) }).find((c) => c.id === "valid")!;
  assert.deepEqual([warned.state, warned.detail], ["pass", "Passed with 3 warnings"]);
  assert.equal(publishChecks({ project: project("QA_APPROVED"), renders, validation: report({ warnings: ["a"] }) }).find((c) => c.id === "valid")!.detail, "Passed with 1 warning");
  assert.equal(publishChecks({ project: project("QA_APPROVED"), renders, validation: report() }).find((c) => c.id === "valid")!.detail, "Passed with no warnings");
});

test("latestRender is the newest finished render and ignores failed and running ones", () => {
  const renders = [render("failed", "FAILED", "2026-11-09T10:00:00Z"), render("a", "COMPLETE", "2026-11-07T10:00:00Z"), render("b", "COMPLETE", "2026-11-08T10:00:00Z"), render("running", "MUXING", "2026-11-10T10:00:00Z")];
  assert.equal(latestRender(renders)?.render_id, "b");
  assert.equal(latestRender([]), undefined);
  assert.equal(latestRender([render("f", "FAILED", "2026-11-09T10:00:00Z")]), undefined);
});

const DATA: YouTubePackagingData = {
  project_id: "p1", titles: ["Title A", "Title B"], description: "A line.\nAnother line.", tags: ["manga", "recap"], tags_string: "manga, recap", hashtags: ["#manga", "#recap"], hashtags_string: "#manga #recap",
  chapters: [{ timestamp: "0:00", seconds: 0, title: "Intro" }, { timestamp: "1:05", seconds: 65, title: "The fight" }],
  thumbnail: { aspect_ratio: "16:9", recommended_width: 1280, recommended_height: 720, prompt: "p", negative_prompt: "n", workflow_id: "w", seed: 1, text_hooks: ["HE LIED"], composition_guidance: "g" },
};

test("chaptersText is one line per chapter in the form YouTube reads", () => {
  assert.equal(chaptersText(DATA.chapters), "0:00 Intro\n1:05 The fight");
  assert.equal(chaptersText([]), "");
});

test("packagingBundle is title, description, chapters, tags and hashtags, skipping what is empty", () => {
  assert.equal(packagingBundle(DATA, "Title B"), "Title B\n\nA line.\nAnother line.\n\n0:00 Intro\n1:05 The fight\n\nmanga, recap\n#manga #recap");
  assert.equal(packagingBundle({ ...DATA, chapters: [], tags_string: "", hashtags_string: "#x" }, "T"), "T\n\nA line.\nAnother line.\n\n#x");
  assert.equal(packagingBundle({ ...DATA, chapters: [], tags_string: "", hashtags_string: "", description: "" }, "T"), "T");
});

test("durationLabel reads like a person would say it", () => {
  assert.equal(durationLabel(45), "45 s");
  assert.equal(durationLabel(370), "6 min 10 s");
  assert.equal(durationLabel(3840), "1 h 4 min");
  assert.equal(durationLabel(0), "0 s");
  assert.equal(durationLabel(59.6), "1 min 0 s");
});
