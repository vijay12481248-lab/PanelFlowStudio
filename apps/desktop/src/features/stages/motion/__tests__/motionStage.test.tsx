import { mountPage } from "../../../__tests__/pageHarness"; // first: installs jsdom before Radix loads
import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { api } from "@panelflow/api-client";
import type { Panel, Project } from "@panelflow/shared-types";
import { MotionStage } from "../MotionStage";

const project = (stage = "AUDIO_APPROVED") => ({ id: "p1", title: "Dawn Gate", current_stage: stage, rights_status: "AUTHORIZED_WEB", stale_stages: [] }) as unknown as Project;
const panels = [{ id: "pn1", sequence: 1 }, { id: "pn2", sequence: 2 }] as Panel[];
const plan = (status = "DRAFT", shots: any[] = SHOTS) => ({
  id: "m1", project_id: "p1", status, total_duration: 370, total_shots: shots.length, style_preset: "cinematic", warnings_count: 0,
  timeline: { scenes: [{ sequence: 1, title: "The gate", shots }] }, created_at: "", updated_at: "",
});
const SHOTS = [
  { shot_id: "s1", start_time: 0, end_time: 3, duration_sec: 3, motion_type: "PUSH_IN", provenance: { panel_ids: ["pn1"] }, caption_cues: [{ speaker: "Aria", text: "Hello there" }] },
  { shot_id: "s2", start_time: 3, end_time: 5, duration_sec: 2, motion_type: "PAN", provenance: { panel_ids: ["pn2"] } },
];

interface Calls { plan: Array<[string, string]>; approve: number; getProject: number; preview: any[][] }
function stub(over: Record<string, unknown> = {}, motion: unknown = null, panelList: Panel[] = panels) {
  const calls: Calls = { plan: [], approve: 0, getProject: 0, preview: [] };
  Object.assign(api as any, {
    getMotionTimeline: async () => { if (!motion) throw new Error("404"); return motion; },
    listPanels: async () => panelList,
    planMotion: async (id: string, preset: string) => { calls.plan.push([id, preset]); return plan(); },
    approveMotion: async () => { calls.approve++; return { approved: true, message: "" }; },
    getProject: async () => { calls.getProject++; return project("MOTION_APPROVED"); },
    previewShotVideo: async (...args: any[]) => { calls.preview.push(args); return { video_url: "/preview/s1.mp4" }; },
    getPanelImageUrl: (_p: string, id: string) => `/panel/${id}.png`,
    ...over,
  });
  return calls;
}
const text = (d: Document) => d.body.textContent ?? "";
const button = (d: Document, label: string | RegExp) => [...d.querySelectorAll("button")].find((b) => (typeof label === "string" ? b.textContent?.trim() === label : label.test(b.textContent ?? ""))) as HTMLButtonElement | undefined;
const card = (d: Document, key: string) => d.querySelector(`[data-shot-key="${key}"]`) as HTMLElement;
const within = (el: Element, label: string) => el.querySelector(`[aria-label="${label}"]`) as HTMLElement;

async function show(p = project(), onApproved: (u: Project) => void = () => {}, onContinue: (p: Project) => void = () => {}) {
  const view = await mountPage(<MotionStage project={p} onApproved={onApproved} onContinue={onContinue} />);
  await view.settle();
  return view;
}

test("no plan yet: it invites planning and offers no Approve", async () => {
  stub();
  const view = await show();
  assert.equal(view.document.querySelectorAll("h1").length, 0);
  assert.ok(text(view.document).includes("No camera plan yet"));
  assert.ok(button(view.document, "Plan motion"));
  assert.equal(button(view.document, /Approve motion/), undefined);
  await view.cleanup();
});

test("planning uses the chosen style once, even on a double click, and then shows the shots", async () => {
  const calls = stub();
  const view = await show();
  await view.clickTwice(button(view.document, "Plan motion")!);
  await view.settle();
  assert.deepEqual(calls.plan, [["p1", "cinematic"]]);
  assert.ok(card(view.document, "s1") && card(view.document, "s2"));
  await view.cleanup();
});

test("the style select decides which preset is planned", async () => {
  const calls = stub();
  const view = await show();
  await view.setSelect(view.document.querySelector("select")!, "slow_burn");
  await view.click(button(view.document, "Plan motion")!);
  await view.settle();
  assert.deepEqual(calls.plan, [["p1", "slow_burn"]]);
  await view.cleanup();
});

test("an existing plan is replaced only after asking", async () => {
  const calls = stub({}, plan());
  const view = await show();
  assert.ok(card(view.document, "s1"));
  await view.click(button(view.document, "Re-plan motion")!);
  const dialog = () => view.document.querySelector('[role="dialog"]')!;
  assert.ok(text(view.document).includes("Replace the current plan?"));
  await view.click([...dialog().querySelectorAll("button")].find((b) => b.textContent === "Cancel")!);
  assert.deepEqual(calls.plan, []);
  await view.click(button(view.document, "Re-plan motion")!);
  await view.click([...dialog().querySelectorAll("button")].find((b) => b.textContent === "Replace plan")!);
  await view.settle();
  assert.equal(calls.plan.length, 1);
  await view.cleanup();
});

test("a failed plan says what happened without the raw exception", async () => {
  stub({ planMotion: async () => { throw new Error("CUDA at C:\\engine\\x.py"); } });
  const view = await show();
  await view.click(button(view.document, "Plan motion")!);
  await view.settle();
  assert.ok(text(view.document).includes("Couldn't plan the motion"));
  assert.ok(!text(view.document).includes("x.py"));
  await view.cleanup();
});

test("the summary shows length, shots, style and continuity", async () => {
  stub({}, plan());
  const view = await show();
  const body = text(view.document);
  assert.ok(body.includes("6:10"));
  assert.ok(body.includes("2 shots"));
  assert.ok(body.includes("cinematic"));
  assert.ok(body.includes("Clean"));
  await view.cleanup();
});

test("each shot shows its scene, motion, timing and caption", async () => {
  stub({}, plan());
  const view = await show();
  const first = card(view.document, "s1").textContent!;
  for (const piece of ["The gate", "PUSH_IN", "0.00s", "3.00s", "Aria", "Hello there", "Shot 1"]) assert.ok(first.includes(piece), piece);
  await view.cleanup();
});

test("Approve motion approves once, reloads the project and hands it over", async () => {
  const calls = stub({}, plan());
  const handed: Project[] = [];
  const view = await show(project(), (u) => handed.push(u));
  await view.clickTwice(button(view.document, "Approve motion")!);
  await view.settle();
  assert.equal(calls.approve, 1);
  assert.equal(calls.getProject, 1);
  assert.equal(handed.length, 1);
  assert.equal(handed[0].current_stage, "MOTION_APPROVED");
  await view.cleanup();
});

test("a refused approval shows the reason, does not move on, and can be tried again", async () => {
  stub({ approveMotion: async () => { throw new Error("Audio must be approved first."); } }, plan());
  let moved = 0;
  const view = await show(project(), () => { moved++; });
  await view.click(button(view.document, "Approve motion")!);
  await view.settle();
  assert.ok(text(view.document).includes("Motion can't be approved yet. Audio must be approved first."));
  assert.equal(moved, 0);
  assert.equal(button(view.document, "Approve motion")!.disabled, false);
  await view.cleanup();
});

test("an approved plan cannot be approved again and offers Continue to render", async () => {
  stub({}, plan("APPROVED"));
  let continued = 0;
  const view = await show(project("MOTION_APPROVED"), () => {}, () => { continued++; });
  assert.equal(button(view.document, "Motion approved")!.disabled, true);
  await view.click(button(view.document, "Continue to render")!);
  assert.equal(continued, 1);
  await view.cleanup();
});

test("a shot with no panel to show cannot be previewed, and says why", async () => {
  stub({}, plan("DRAFT", [{ shot_id: "lonely", duration_sec: 2 }]), []);
  const view = await show();
  const c = card(view.document, "lonely");
  assert.equal(button(c as unknown as Document, "Generate preview")!.disabled, true);
  assert.ok(c.textContent!.includes("No panel found for this shot"));
  await view.cleanup();
});

test("Generate preview sends the shot's choices and shows the returned video, labelled as preview only", async () => {
  const calls = stub({}, plan());
  const view = await show();
  const c = card(view.document, "s1");
  assert.ok(c.textContent!.includes("Preview only. These choices are not saved to the plan."));
  await view.setSelect(within(c, "Camera move") as HTMLSelectElement, "orbit");
  await view.setSelect(within(c, "Intensity") as HTMLSelectElement, "action");
  await view.setSelect(within(c, "Effect") as HTMLSelectElement, "film_grain");
  await view.click([...c.querySelectorAll("button")].find((b) => b.textContent === "Glowing aura")!);
  await view.clickTwice(button(c as unknown as Document, "Generate preview")!);
  await view.settle();
  assert.equal(calls.preview.length, 1, "one preview request");
  assert.deepEqual(calls.preview[0], ["p1", "pn1", "orbit", "Glowing aura", "fast_h3", "action", "film_grain"]);
  assert.equal(card(view.document, "s1").querySelector("video")!.getAttribute("src"), "/preview/s1.mp4");
  await view.cleanup();
});

test("the video engine select applies to previews", async () => {
  const calls = stub({}, plan());
  const view = await show();
  const selects = [...view.document.querySelectorAll("select")];
  const engine = selects.find((s) => [...s.options].some((o) => o.value === "ken_burns"))!;
  await view.setSelect(engine, "ken_burns");
  await view.click(button(card(view.document, "s2") as unknown as Document, "Generate preview")!);
  await view.settle();
  assert.equal(calls.preview[0][4], "ken_burns");
  await view.cleanup();
});

test("a failed preview says so and keeps the controls", async () => {
  stub({ previewShotVideo: async () => { throw new Error("boom C:\\engine\\h3.py"); } }, plan());
  const view = await show();
  const c = card(view.document, "s1");
  await view.click(button(c as unknown as Document, "Generate preview")!);
  await view.settle();
  assert.ok(card(view.document, "s1").textContent!.includes("Couldn't make the preview"));
  assert.ok(!text(view.document).includes("h3.py"));
  assert.equal(button(card(view.document, "s1") as unknown as Document, "Generate preview")!.disabled, false);
  await view.cleanup();
});
