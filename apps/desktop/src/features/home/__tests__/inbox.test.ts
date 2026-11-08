import test from "node:test";
import assert from "node:assert/strict";
import type { Job, PipelineStage, Project } from "@panelflow/shared-types";
import type { OriginalSeries } from "@panelflow/api-client";
import { buildInbox, pickFocusProject, reviewStageFor } from "../inbox";

const NOW = Date.parse("2026-11-08T12:00:00Z");
const DAY = 86_400_000;
const iso = (msAgo: number) => new Date(NOW - msAgo).toISOString();

const project = (id: string, stage: PipelineStage, extra: Partial<Project> = {}): Project => ({
  id, title: `Title ${id}`, source_type: "MANGA" as Project["source_type"], source_url: null, source_metadata: {},
  rights_status: "AUTHORIZED_WEB" as Project["rights_status"], license_info: "", workspace_path: "", current_stage: stage,
  settings: {}, created_at: iso(10 * DAY), updated_at: iso(DAY), total_pages: 5, ready_pages: 5, failed_pages: 0, ...extra,
});

const job = (id: string, projectId: string, type: string, status: Job["status"], agoMs: number, extra: Partial<Job> = {}): Job => ({
  job_id: id, project_id: projectId, job_type: type, status, progress: 0, message: "", input: {}, output: {}, error: null,
  created_at: iso(agoMs), started_at: iso(agoMs), finished_at: status === "RUNNING" || status === "QUEUED" ? null : iso(agoMs), ...extra,
});

const build = (projects: Project[], jobs: Job[] = [], series: OriginalSeries[] = []) => buildInbox({ projects, jobs, series, now: NOW });

test("each stage that waits for approval opens the screen where it is approved", () => {
  const expected: Array<[PipelineStage, string, string]> = [
    ["ACQUIRED", "pages", "Review pages, Title p"], ["PANELS_DETECTED", "panels", "Review panels, Title p"],
    ["OCR_COMPLETE", "ocr", "Review OCR, Title p"], ["STORY_ANALYZED", "story", "Review story, Title p"],
    ["SCRIPT_GENERATED", "script", "Review script, Title p"], ["VOICE_GENERATED", "audio", "Review audio, Title p"],
    ["SHOT_PLAN_GENERATED", "motion", "Review motion, Title p"], ["RENDERED", "render", "Review render, Title p"],
  ];
  for (const [stage, screen, title] of expected) {
    const [item] = build([project("p", stage)]);
    assert.equal(item.kind, "review", stage);
    assert.equal(item.title, title);
    assert.deepEqual(item.action, { type: "open", to: `/projects/p/${screen}` });
    assert.equal(reviewStageFor(stage), screen);
  }
});

test("stages that are not waiting for a person produce nothing", () => {
  for (const stage of ["NEW", "OCR_APPROVED", "STORY_APPROVED", "EXPORTED", "MOTION_APPROVED"] as PipelineStage[]) {
    assert.deepEqual(build([project("p", stage)]), [], stage);
  }
});

test("a project ready to upload opens its publish stage", () => {
  const [item] = build([project("p", "QA_APPROVED")]);
  assert.equal(item.kind, "publish");
  assert.deepEqual(item.action, { type: "open", to: "/projects/p/publish" });
});

test("unknown rights give one Rights decision that opens the acquire stage and never links past the gate", () => {
  const items = build([project("p", "RENDERED", { rights_status: "UNKNOWN" as Project["rights_status"] })]);
  assert.equal(items.length, 1);
  assert.equal(items[0].kind, "blocked");
  assert.equal(items[0].title, "Rights decision, Title p");
  assert.deepEqual(items[0].action, { type: "open", to: "/projects/p/acquire" });
  for (const stage of ["QA_APPROVED", "RENDERED", "OCR_COMPLETE"] as PipelineStage[]) {
    const [item] = build([project("p", stage, { rights_status: "UNKNOWN" as Project["rights_status"] })]);
    assert.ok(item.action.type === "open" && !/render|publish/.test(item.action.to), stage);
  }
});

test("a recent failed job offers Retry with the first line of its error", () => {
  const failed = job("j1", "p", "OCR_EXTRACTION", "FAILED", DAY, { error: "CUDA out of memory\nTraceback (most recent call last)..." });
  const [item] = build([project("p", "NORMALIZED")], [failed]);
  assert.equal(item.kind, "failed");
  assert.equal(item.title, "OCR extraction failed, Title p");
  assert.equal(item.subtitle, "CUDA out of memory");
  assert.equal(item.actionLabel, "Retry");
  assert.deepEqual(item.action, { type: "retry-job", jobId: "j1" });
});

test("a failed job that a newer job of the same type replaced is not shown", () => {
  const failed = job("old", "p", "RENDER", "FAILED", 2 * DAY);
  for (const status of ["SUCCEEDED", "RUNNING", "QUEUED"] as Job["status"][]) {
    assert.deepEqual(build([project("p", "NORMALIZED")], [failed, job("new", "p", "RENDER", status, DAY)]), [], status);
  }
});

test("a failed job of a different type does not hide this one", () => {
  const items = build([project("p", "NORMALIZED")], [job("a", "p", "RENDER", "FAILED", 2 * DAY), job("b", "p", "OCR_EXTRACTION", "SUCCEEDED", DAY)]);
  assert.equal(items.length, 1);
  assert.equal(items[0].kind, "failed");
});

test("a failure older than a week is no longer news", () => {
  assert.deepEqual(build([project("p", "NORMALIZED")], [job("j", "p", "RENDER", "FAILED", 8 * DAY)]), []);
  assert.equal(build([project("p", "NORMALIZED")], [job("j", "p", "RENDER", "FAILED", 6 * DAY)]).length, 1);
});

test("a project with a failed job and a review stage shows only the failure", () => {
  const items = build([project("p", "OCR_COMPLETE")], [job("j", "p", "OCR_EXTRACTION", "FAILED", DAY)]);
  assert.deepEqual(items.map((i) => i.kind), ["failed"]);
});

const episode = (n: number, over: Record<string, unknown> = {}) => ({
  number: n, title: `Ep ${n}`, summary: "", publish_at: null, status: "done", video: "v.mp4", pdf: null, warnings: [],
  upload_status: "", upload_error: "", youtube_url: null, youtube_privacy: null, ...over,
});
const series = (episodes: ReturnType<typeof episode>[]): OriginalSeries => ({
  id: "s1", name: "Moon Tales", genre: "fantasy", channel_id: "c", bible: { premise: { title: "", logline: "" }, characters: [] }, episodes,
} as unknown as OriginalSeries);

test("rendered episodes that are not uploaded are ready to publish, failed uploads are failures", () => {
  const items = build([], [], [series([episode(1), episode(2, { youtube_url: "https://y/1", upload_status: "uploaded" }), episode(3, { upload_status: "failed", upload_error: "Quota exceeded" }), episode(4, { status: "running" })])]);
  assert.deepEqual(items.map((i) => [i.kind, i.title]), [["failed", "Upload failed, episode 3, Moon Tales"], ["publish", "Upload episode 1, Moon Tales"]]);
  assert.equal(items[0].subtitle, "Quota exceeded");
  assert.deepEqual(items[1].action, { type: "open", to: "/create/stories" });
});

test("ChronoFlow projects have no pipeline stage items", () => {
  assert.deepEqual(build([project("p", "OCR_COMPLETE", { settings: { workflow_type: "chronoflow" } })]), []);
});

test("items are ordered failed, blocked, review, publish, newest first within a kind", () => {
  const items = build(
    [project("pub", "QA_APPROVED"), project("rev-old", "OCR_COMPLETE", { updated_at: iso(5 * DAY) }), project("rev-new", "OCR_COMPLETE", { updated_at: iso(DAY) }),
      project("rights", "NEW", { rights_status: "UNKNOWN" as Project["rights_status"] }), project("fail", "NORMALIZED")],
    [job("j", "fail", "RENDER", "FAILED", DAY)],
  );
  assert.deepEqual(items.map((i) => i.projectId), ["fail", "rights", "rev-new", "rev-old", "pub"]);
});

test("pickFocusProject prefers the project of the first inbox item, then the latest updated", () => {
  const projects = [project("a", "NEW", { updated_at: iso(3 * DAY) }), project("b", "NEW", { updated_at: iso(DAY) }), project("c", "OCR_COMPLETE", { updated_at: iso(9 * DAY) })];
  assert.equal(pickFocusProject(projects, build(projects))?.id, "c");
  assert.equal(pickFocusProject(projects, [])?.id, "b");
  assert.equal(pickFocusProject([], []), undefined);
});

test("nothing in, nothing out", () => {
  assert.deepEqual(build([], [], []), []);
});
