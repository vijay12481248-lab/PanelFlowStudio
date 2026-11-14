import { mountPage } from "../../__tests__/pageHarness"; // first: installs jsdom before Radix loads
import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { api } from "@panelflow/api-client";
import type { PipelineStage, Project } from "@panelflow/shared-types";
import { PublishStage } from "../PublishStage";

const project = (stage: PipelineStage = "QA_APPROVED", over: Partial<Project> = {}) =>
  ({ id: "p1", title: "Dawn Gate", current_stage: stage, rights_status: "AUTHORIZED_WEB", stale_stages: [], ...over }) as Project;

const REPORT = { is_valid: true, video_valid: true, audio_valid: true, sync_valid: true, black_frames_count: 2, timeline_gaps_count: 0, clipping_samples_count: 0, duration_sec: 370, warnings: ["Two black frames near 0:12"] };
const RENDER = { render_id: "r1", project_id: "p1", status: "COMPLETE", current_stage: "", progress: 1, frames_done: 1, frames_total: 1, output_profile: "youtube_1080p", output_path: "", created_at: "2026-11-08T10:00:00Z", validation_report: REPORT };
const PACKAGING = {
  project_id: "p1", titles: ["The Duke Strikes Back", "Why The Assassin Waited"], selected_title: "The Duke Strikes Back", description: "A short recap.\nSubscribe for more.",
  tags: ["manga", "recap"], tags_string: "manga, recap", hashtags: ["#manga"], hashtags_string: "#manga", chapters: [{ timestamp: "0:00", seconds: 0, title: "Intro" }, { timestamp: "1:05", seconds: 65, title: "The fight" }],
  thumbnail: { aspect_ratio: "16:9", recommended_width: 1280, recommended_height: 720, prompt: "A duke in rain, dramatic", negative_prompt: "text", workflow_id: "w", seed: 1, text_hooks: ["HE LIED"], composition_guidance: "Face left" },
};

function stub(over: Record<string, unknown> = {}, renders: unknown[] = [RENDER]) {
  const calls = { packaging: [] as boolean[], generate: 0, folder: 0 };
  Object.assign(api as any, {
    listRenders: async () => renders,
    getRenderValidation: async () => REPORT,
    getRenderVideoUrl: (_p: string, id: string) => `/output/${id}.mp4`,
    getYoutubePackaging: async (_id: string, refresh = false) => { calls.packaging.push(refresh); return PACKAGING; },
    generateYoutubePackaging: async () => { calls.generate++; return PACKAGING; },
    openProjectFolder: async () => { calls.folder++; return { opened: true, path: "" }; },
    ...over,
  });
  return calls;
}
const text = (d: Document) => d.body.textContent ?? "";
const button = (d: Document, label: string) => [...d.querySelectorAll("button")].find((b) => b.textContent?.trim() === label || b.getAttribute("aria-label") === label) as HTMLButtonElement | undefined;

async function show(p: Project, copy?: (t: string) => Promise<void>) {
  const view = await mountPage(<PublishStage project={p} {...(copy ? { copy } : {})} />);
  await view.settle();
  return view;
}

test("opening Publish asks for nothing to be generated, and the checks never offer to upload or publish", async () => {
  const calls = stub();
  const view = await show(project());
  assert.deepEqual(calls.packaging, [], "no packaging request on open");
  assert.equal(calls.generate, 0);
  const body = text(view.document);
  assert.ok(!/Upload now|Publish now|Schedule/.test(body));
  for (const label of ["Rights", "Approved", "Render", "Up to date", "Render checks"]) assert.ok(body.includes(label), label);
  assert.equal(view.document.querySelectorAll('[data-check][data-state="pass"]').length, 5);
  await view.cleanup();
});

test("it says plainly that PanelFlow does not upload pipeline videos and that uploads should start private", async () => {
  stub();
  const view = await show(project());
  const body = text(view.document);
  assert.ok(body.includes("PanelFlow does not upload pipeline videos yet."));
  assert.ok(body.includes("Private"));
  assert.ok(body.includes("YouTube Studio"));
  await view.cleanup();
});

test("unknown rights fail the rights check, hold the hand-off, and still explain what to do", async () => {
  stub();
  const view = await show(project("QA_APPROVED", { rights_status: "UNKNOWN" as Project["rights_status"] }));
  assert.equal(view.document.querySelector('[data-check="rights"]')!.getAttribute("data-state"), "fail");
  assert.ok(text(view.document).includes("Rights are unknown, so publishing is held"));
  assert.ok(text(view.document).includes("PanelFlow does not upload pipeline videos yet."));
  await view.cleanup();
});

test("the latest render plays from the engine and its checks are shown in words", async () => {
  const calls = stub();
  const view = await show(project());
  const video = view.document.querySelector("video") as HTMLVideoElement;
  assert.equal(video.getAttribute("src"), "/output/r1.mp4");
  assert.equal(video.hasAttribute("controls"), true);
  const body = text(view.document);
  assert.ok(body.includes("6 min 10 s"));
  assert.ok(body.includes("Video valid") && body.includes("Audio valid") && body.includes("Sync valid"));
  assert.ok(body.includes("Two black frames near 0:12"));
  await view.clickTwice(button(view.document, "Open project folder")!);
  await view.settle();
  assert.equal(calls.folder, 1);
  await view.cleanup();
});

test("with no finished render there is an invitation and no video", async () => {
  stub({}, []);
  const view = await show(project("MOTION_APPROVED"));
  assert.equal(view.document.querySelector("video"), null);
  assert.ok(text(view.document).includes("No finished render yet"));
  assert.ok([...view.document.querySelectorAll("a")].some((a) => a.textContent === "Open the render stage"));
  assert.equal(view.document.querySelector('[data-check="render"]')!.getAttribute("data-state"), "pending");
  await view.cleanup();
});

test("a failed render shows why and points to the render stage", async () => {
  stub({}, [{ ...RENDER, render_id: "bad", status: "FAILED", error_message: "Out of GPU memory", validation_report: null, created_at: "2026-11-09T10:00:00Z" }]);
  const view = await show(project("RENDERED"));
  const check = view.document.querySelector('[data-check="render"]')!;
  assert.equal(check.getAttribute("data-state"), "fail");
  assert.ok(check.textContent!.includes("Out of GPU memory"));
  assert.ok([...view.document.querySelectorAll("a")].some((a) => a.textContent === "Open the render stage"));
  await view.cleanup();
});

test("a stale render says to render again", async () => {
  stub();
  const view = await show(project("QA_APPROVED", { stale_stages: ["render"] }));
  assert.ok(text(view.document).includes("Audio or motion changed after this render. Render again."));
  await view.cleanup();
});

test("packaging starts empty and loads only when asked, once even on a fast double click", async () => {
  const calls = stub();
  const view = await show(project());
  assert.ok(text(view.document).includes("Packaging isn't loaded"));
  await view.clickTwice(button(view.document, "Get packaging")!);
  await view.settle();
  assert.deepEqual(calls.packaging, [false]);
  const body = text(view.document);
  for (const expected of ["The Duke Strikes Back", "Why The Assassin Waited", "Subscribe for more.", "manga, recap", "#manga", "0:00 Intro", "1:05 The fight", "A duke in rain, dramatic", "HE LIED"]) {
    assert.ok(body.includes(expected) || [...view.document.querySelectorAll("textarea")].some((t) => t.value.includes(expected)), expected);
  }
  await view.cleanup();
});

test("each Copy copies exactly what is shown and says Copied", async () => {
  stub();
  const copied: string[] = [];
  const view = await show(project(), async (t) => { copied.push(t); });
  await view.click(button(view.document, "Get packaging")!);
  await view.settle();
  await view.click(button(view.document, "Copy description")!);
  await view.click(button(view.document, "Copy chapters")!);
  await view.click(button(view.document, "Copy tags")!);
  await view.click(button(view.document, "Copy everything")!);
  await view.settle();
  assert.deepEqual(copied, [
    "A short recap.\nSubscribe for more.",
    "0:00 Intro\n1:05 The fight",
    "manga, recap",
    "The Duke Strikes Back\n\nA short recap.\nSubscribe for more.\n\n0:00 Intro\n1:05 The fight\n\nmanga, recap\n#manga",
  ]);
  assert.ok(text(view.document).includes("Copied"));
  await view.cleanup();
});

test("choosing another title changes what Copy everything copies", async () => {
  stub();
  const copied: string[] = [];
  const view = await show(project(), async (t) => { copied.push(t); });
  await view.click(button(view.document, "Get packaging")!);
  await view.settle();
  const second = view.document.querySelector('input[type="radio"][value="Why The Assassin Waited"]') as HTMLInputElement;
  await view.click(second);
  await view.click(button(view.document, "Copy everything")!);
  assert.ok(copied[0].startsWith("Why The Assassin Waited\n\n"));
  await view.cleanup();
});

test("Refresh asks first: Cancel requests nothing and confirming refreshes once", async () => {
  const calls = stub();
  const view = await show(project());
  await view.click(button(view.document, "Get packaging")!);
  await view.settle();
  await view.click(button(view.document, "Refresh packaging")!);
  assert.ok(view.document.querySelector('[role="dialog"]')!.textContent!.includes("It can take a minute and replaces the saved version."));
  await view.click(button(view.document, "Cancel")!);
  assert.deepEqual(calls.packaging, [false]);
  await view.click(button(view.document, "Refresh packaging")!);
  await view.clickTwice(button(view.document, "Write new packaging")!);
  await view.settle();
  assert.deepEqual(calls.packaging, [false, true]);
  await view.cleanup();
});

test("a failed packaging load says what to do without the raw exception, and Retry works", async () => {
  let fail = true;
  const calls = stub({ getYoutubePackaging: async () => { if (fail) throw new Error("ollama traceback C:/secret"); return PACKAGING; } });
  const view = await show(project());
  await view.click(button(view.document, "Get packaging")!);
  await view.settle();
  const body = text(view.document);
  assert.ok(body.includes("Couldn't load packaging. Check that the engine and Ollama are running, then try again."));
  assert.ok(!body.includes("traceback") && !body.includes("C:/secret"));
  fail = false;
  await view.click(button(view.document, "Retry")!);
  await view.settle();
  assert.ok(text(view.document).includes("The Duke Strikes Back"));
  assert.equal(calls.generate, 0);
  await view.cleanup();
});

test("while a check has failed the packaging can be read but not copied", async () => {
  stub();
  const view = await show(project("QA_APPROVED", { rights_status: "UNKNOWN" as Project["rights_status"] }));
  await view.click(button(view.document, "Get packaging")!);
  await view.settle();
  assert.ok(text(view.document).includes("The Duke Strikes Back"));
  assert.equal(button(view.document, "Copy everything")!.disabled, true);
  assert.ok(text(view.document).includes("Copying is held until the failed checks are fixed."));
  await view.cleanup();
});
