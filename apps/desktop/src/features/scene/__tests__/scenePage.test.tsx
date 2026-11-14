import { mountPage } from "../../__tests__/pageHarness"; // first: installs jsdom before Radix loads
import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { api } from "@panelflow/api-client";
import type { SceneRun } from "@panelflow/api-client";
import { ScenePage } from "../ScenePage";

const PLAN = { scene_type: "fight", brief: "the hero fights the villain", camera: { angle: "eye_level", distance: "medium", note: "" }, light: { direction: "back" },
  actors: [{ id: "hero", side: "left", action_state: "striking" }, { id: "villain", side: "right", action_state: "blocking" }], contacts: [] };

const item = (key: string, status: string, value: string | null, confidence: number, answers: Record<string, any> = {}) => ({ key, status, value, confidence, answers, suspect_flips: [] });

const makeRun = (over: Partial<SceneRun> = {}): SceneRun => ({
  id: "run-1", project_id: "p1", job_id: null, brief: "the hero fights the villain", scene_type: "fight", plan: PLAN, image_path: "panels/a.png", status: "needs_review",
  system_review: { unmet: ["the camera looks up at the scene from a low angle"] }, attempts: 3, seconds: 70, review_state: "pending", created_at: "2026-11-14T10:00:00",
  analysis: { id: "a1", judges: ["qwen3.5:9b", "qwen3-vl-8b"], single_judge: false, seconds: 9, error: null, created_at: null, crosscheck: { judges: ["qwen3.5:9b", "qwen3-vl-8b"], single_judge: false, seconds: 9, items: [
    item("camera", "disputed", null, 0.3, { "qwen3.5:9b": { round1: "level", round2: "level", evidence: "flat horizon" }, "qwen3-vl-8b": { round1: "looks_up", round2: "looks_up", evidence: "faces seen from below" } }),
    item("people", "agreed", "2", 0.9),
  ] } as any },
  feedback: null, ...over,
});

function stub(run: SceneRun, queue: SceneRun[] = [run]) {
  const calls = { feedback: [] as any[], proposal: [] as string[], correct: [] as any[], generate: [] as any[], dismissed: [] as string[], created: [] as any[] };
  (api as any).getSceneRun = async () => run;
  (api as any).listSceneRuns = async () => ({ items: queue, total_unreviewed: queue.length });
  (api as any).sceneRunImageUrl = (id: string) => `http://engine/img/${id}`;
  (api as any).submitSceneFeedback = async (id: string, body: any) => { calls.feedback.push([id, body]); return { ...run, review_state: "reviewed", feedback: { ...body, created_at: null } }; };
  (api as any).dismissSceneRun = async (id: string) => { calls.dismissed.push(id); return run; };
  (api as any).sceneProposal = async (brief: string) => { calls.proposal.push(brief); return { plan: PLAN, summary: "eye-level view, medium shot, hero on the left striking, villain on the right blocking, light from behind", questions: [] }; };
  (api as any).sceneCorrect = async (plan: any, corr: Record<string, string>) => { calls.correct.push(corr); return { plan: { ...plan, camera: { ...plan.camera, angle: corr["camera.angle"] ?? plan.camera.angle } }, summary: "high angle, medium shot, hero on the left striking, villain on the right blocking, light from behind" }; };
  (api as any).listProjects = async () => [];
  (api as any).createProject = async (p: any) => { calls.created.push(p); return { id: "proj-new", title: p.title }; };
  (api as any).sceneGenerate = async (projectId: string, plan: any) => { calls.generate.push([projectId, plan]); return { job_id: "job-1", status: "QUEUED" }; };
  (api as any).getJob = async () => ({ job_id: "job-1", status: "SUCCEEDED", output: { run_id: "run-new" }, error: null });
  return calls;
}

const text = (doc: Document) => doc.body.textContent ?? "";
const button = (doc: Document, label: string) => [...doc.querySelectorAll("button")].find((b) => b.textContent?.trim() === label) as HTMLButtonElement | undefined;
const byLabel = (doc: Document, label: string) => doc.querySelector(`[aria-label="${label}"]`) as HTMLElement;
function setValue(doc: Document, el: HTMLElement, value: string) {
  const win = doc.defaultView as any;
  const proto = el instanceof win.HTMLTextAreaElement ? win.HTMLTextAreaElement.prototype : el instanceof win.HTMLSelectElement ? win.HTMLSelectElement.prototype : win.HTMLInputElement.prototype;
  Object.getOwnPropertyDescriptor(proto, "value")!.set!.call(el, value);
  el.dispatchEvent(new win.Event(el instanceof win.HTMLSelectElement ? "change" : "input", { bubbles: true }));
}
const tick = (ms = 60) => new Promise((r) => setTimeout(r, ms));

test("opening a run shows the picture, the AI review rows and the owner's panel", async () => {
  stub(makeRun());
  const view = await mountPage(<ScenePage pollMs={20} />, "/page?run=run-1");
  await view.settle();
  const img = view.document.querySelector("img") as HTMLImageElement;
  assert.ok(img && img.src === "http://engine/img/run-1");
  assert.match(text(view.document), /Camera angle/);
  assert.match(text(view.document), /People in the picture/);
  assert.match(text(view.document), /Both judges agree/);
  assert.match(text(view.document), /Your verdict/);
  assert.match(text(view.document), /the camera looks up at the scene from a low angle/); // what the system itself missed
  await view.cleanup();
});

test("a disputed item is visibly highlighted and shows both judges", async () => {
  stub(makeRun());
  const view = await mountPage(<ScenePage pollMs={20} />, "/page?run=run-1");
  await view.settle();
  const row = view.document.querySelector('[data-status="disputed"]') as HTMLElement;
  assert.ok(row);
  assert.match(row.textContent ?? "", /Judges still disagree: your call/);
  assert.match(row.textContent ?? "", /qwen3\.5:9b/);
  assert.match(row.textContent ?? "", /faces seen from below/);
  assert.equal(row.getAttribute("data-highlight"), "true");
  await view.cleanup();
});

test("a single-judge analysis says so", async () => {
  const run = makeRun();
  run.analysis!.single_judge = true;
  run.analysis!.judges = ["qwen3.5:9b"];
  stub(run);
  const view = await mountPage(<ScenePage pollMs={20} />, "/page?run=run-1");
  await view.settle();
  assert.match(text(view.document), /Only one judge could look at this picture/);
  await view.cleanup();
});

test("a failed judging shows the reason instead of empty rows", async () => {
  const run = makeRun();
  run.analysis = { id: "a1", judges: [], single_judge: false, seconds: 0, error: "RuntimeError: judges exploded", created_at: null, crosscheck: {} };
  stub(run);
  const view = await mountPage(<ScenePage pollMs={20} />, "/page?run=run-1");
  await view.settle();
  assert.match(text(view.document), /The AI review could not be made/);
  assert.match(text(view.document), /judges exploded/);
  await view.cleanup();
});

test("submit stays disabled until liked is chosen and a reason exists", async () => {
  stub(makeRun());
  const view = await mountPage(<ScenePage pollMs={20} />, "/page?run=run-1");
  await view.settle();
  const submit = () => button(view.document, "Save my review")!;
  assert.equal(submit().disabled, true);
  setValue(view.document, byLabel(view.document, "How much did you like it"), "70");
  await tick();
  assert.equal(submit().disabled, true); // liked alone is not enough
  (view.document.querySelector('[role="switch"]') as HTMLElement).click();
  await tick();
  assert.equal(submit().disabled, false);
  await view.cleanup();
});

test("submit sends liked, agree, tags and note, then shows thanks", async () => {
  const calls = stub(makeRun());
  const view = await mountPage(<ScenePage pollMs={20} />, "/page?run=run-1");
  await view.settle();
  setValue(view.document, byLabel(view.document, "How much did you like it"), "80");
  (button(view.document, "good: pose") as HTMLElement).click();
  (button(view.document, "wrong: camera") as HTMLElement).click();
  setValue(view.document, byLabel(view.document, "Your comments"), "the angle is too flat");
  await tick();
  button(view.document, "Save my review")!.click();
  await tick(100);
  assert.deepEqual(calls.feedback[0], ["run-1", { liked: 80, agrees_with_ai: false, good_tags: ["pose"], wrong_tags: ["camera"], note: "the angle is too flat" }]);
  assert.match(text(view.document), /Thanks, your review is saved/);
  await view.cleanup();
});

test("dismiss asks the engine to drop the request", async () => {
  const calls = stub(makeRun());
  const view = await mountPage(<ScenePage pollMs={20} />, "/page?run=run-1");
  await view.settle();
  button(view.document, "Dismiss")!.click();
  await tick(80);
  assert.deepEqual(calls.dismissed, ["run-1"]);
  await view.cleanup();
});

test("planning a brief shows the plan and correcting it calls the engine", async () => {
  const calls = stub(makeRun());
  const view = await mountPage(<ScenePage pollMs={20} />, "/page");
  await view.settle();
  setValue(view.document, byLabel(view.document, "Describe the picture"), "the hero fights the villain");
  await tick();
  button(view.document, "Plan it")!.click();
  await tick(100);
  assert.deepEqual(calls.proposal, ["the hero fights the villain"]);
  assert.match(text(view.document), /hero on the left striking/);
  setValue(view.document, byLabel(view.document, "Camera angle"), "high");
  await tick(100);
  assert.deepEqual(calls.correct[0], { "camera.angle": "high" });
  assert.match(text(view.document), /high angle, medium shot/);
  await view.cleanup();
});

test("draw it finds or creates the project, polls the job and opens the new run", async () => {
  const calls = stub(makeRun());
  const view = await mountPage(<ScenePage pollMs={20} />, "/page");
  await view.settle();
  setValue(view.document, byLabel(view.document, "Describe the picture"), "the hero fights the villain");
  await tick();
  button(view.document, "Plan it")!.click();
  await tick(100);
  button(view.document, "Draw it")!.click();
  for (let i = 0; i < 80 && !view.router.state.location.search.includes("run=run-new"); i++) await tick(25);
  assert.equal(calls.created[0].title, "Scene Director");
  assert.equal(calls.generate[0][0], "proj-new");
  assert.ok(view.router.state.location.search.includes("run=run-new"));
  await view.cleanup();
});

test("with nothing waiting and no run open the page invites a brief", async () => {
  stub(makeRun(), []);
  const view = await mountPage(<ScenePage pollMs={20} />, "/page");
  await view.settle();
  assert.match(text(view.document), /Describe the picture/);
  assert.match(text(view.document), /Nothing is waiting for your review/);
  await view.cleanup();
});
