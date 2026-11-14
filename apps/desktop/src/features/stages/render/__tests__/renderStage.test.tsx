import { mountPage } from "../../../__tests__/pageHarness"; // first: installs jsdom before Radix loads
import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { api } from "@panelflow/api-client";
import type { Project } from "@panelflow/shared-types";
import { RenderStage } from "../RenderStage";

const project = (stage = "MOTION_APPROVED") => ({ id: "p1", title: "Dawn Gate", current_stage: stage, rights_status: "AUTHORIZED_WEB", stale_stages: [] }) as unknown as Project;

const render = (id: string, status: string, over: Record<string, unknown> = {}) => ({
  render_id: id, project_id: "p1", status, current_stage: status, progress: 0.4, frames_done: 400, frames_total: 1000, output_profile: "standard_1080p",
  output_path: `C:\\Users\\user\\renders\\${id}.mp4`, created_at: "2026-11-08T10:00:00Z", error_code: null, error_message: null, validation_report: null, ...over,
});
const PROFILES = { profiles: [
  { id: "standard_1080p", name: "Full HD 1080p (Landscape 16:9)", width: 1920, height: 1080, fps: 30 },
  { id: "vertical_shorts", name: "Vertical 1080p (Portrait 9:16)", width: 1080, height: 1920, fps: 30 },
  { id: "square_feed", name: "Square 1080p (Feed 1:1)", width: 1080, height: 1080, fps: 30 },
  { id: "draft_720p", name: "Fast Draft 720p (Ultra Fast)", width: 1280, height: 720, fps: 30 },
] };
const DESTINATIONS = { destinations: [{ id: "videos", label: "Videos", path: "C:\\Users\\user\\Videos", exists: true, is_default: true }, { id: "desktop", label: "Desktop", path: "C:\\Users\\user\\Desktop", exists: true }], default_directory: "C:\\Users\\user\\Videos" };

interface Calls { start: any[][]; cancel: string[]; getProject: number; listRenders: number; open: any[][] }
function stub(opts: { renders?: any[]; over?: Record<string, unknown> } = {}) {
  const calls: Calls = { start: [], cancel: [], getProject: 0, listRenders: 0, open: [] };
  let list = opts.renders ?? [];
  Object.assign(api as any, {
    listRenders: async () => { calls.listRenders++; return list; },
    getRenderProfiles: async () => PROFILES,
    getQuickDestinations: async () => DESTINATIONS,
    startRender: async (...a: any[]) => { calls.start.push(a); list = [render("new", "QUEUED"), ...list]; return render("new", "QUEUED"); },
    cancelRender: async (_p: string, id: string) => { calls.cancel.push(id); return { cancelled: true, render_id: id }; },
    getProject: async () => { calls.getProject++; return project("RENDERED"); },
    getRenderVideoUrl: (_p: string, id: string) => `/video/${id}.mp4`,
    getRenderContactSheetUrl: (_p: string, id: string) => `/sheet/${id}.jpg`,
    getRenderAuditSampleUrl: (_p: string, id: string, i: number) => `/sample/${id}/${i}.jpg`,
    openPath: async (...a: any[]) => { calls.open.push(a); return { opened: true, path: a[0] }; },
    pickDirectoryNative: async () => ({ selected: true, path: "D:\\Exports" }),
    pickSaveFileNative: async () => ({ selected: true, path: "D:\\Exports\\video.mp4" }),
    ...opts.over,
  });
  return { calls, set: (next: any[]) => { list = next; } };
}
const text = (d: Document) => d.body.textContent ?? "";
const button = (d: Document | Element, label: string | RegExp) => [...d.querySelectorAll("button")].find((b) => (typeof label === "string" ? b.textContent?.trim() === label || b.getAttribute("aria-label") === label : label.test(b.textContent ?? ""))) as HTMLButtonElement | undefined;
const byLabel = (d: Document, label: string) => d.querySelector(`[aria-label="${label}"]`) as any;
async function until(cond: () => boolean, ms = 4000) { for (let i = 0; i < ms / 25 && !cond(); i++) await new Promise((r) => setTimeout(r, 25)); }

async function show(onComplete: (p: Project) => void = () => {}) {
  const view = await mountPage(<RenderStage project={project()} onRenderComplete={onComplete} />);
  await view.settle();
  await until(() => Boolean(byLabel(view.document, "Output profile")) || Boolean(button(view.document, "Cancel render")) || text(view.document).includes("Couldn't load the render profiles"));
  return view;
}

test("a project whose renders are only out of date or finished shows the settings and Start, not a running job (the legacy bug)", async () => {
  stub({ renders: [render("s1", "STALE", { created_at: "2026-11-08T12:00:00Z" }), render("s2", "STALE"), render("c1", "COMPLETE")] });
  const view = await show();
  assert.equal(view.document.querySelectorAll("h1").length, 0);
  assert.equal(view.document.querySelectorAll("h2").length >= 1, true);
  assert.ok(button(view.document, "Start render"));
  assert.equal(button(view.document, "Cancel render"), undefined);
  assert.ok(byLabel(view.document, "Output profile"));
  assert.ok(!text(view.document).includes("Rendering"));
  await view.cleanup();
});

test("the profile select lists exactly the engine's profiles", async () => {
  stub();
  const view = await show();
  const select = byLabel(view.document, "Output profile") as HTMLSelectElement;
  assert.deepEqual([...select.options].map((o) => o.value), ["standard_1080p", "vertical_shorts", "square_feed", "draft_720p"]);
  assert.equal(select.value, "standard_1080p");
  assert.ok(![...select.options].some((o) => o.value === "preview_1080p"));
  await view.cleanup();
});

test("with no profile list Start is disabled with the reason and no profile is invented", async () => {
  const { calls } = stub({ over: { getRenderProfiles: async () => { throw new Error("down"); } } });
  const view = await show();
  assert.ok(text(view.document).includes("Couldn't load the render profiles. Check that the engine is running."));
  assert.equal(button(view.document, "Start render")!.disabled, true);
  assert.equal(byLabel(view.document, "Output profile").options.length, 0);
  await view.click(button(view.document, "Start render")!);
  assert.equal(calls.start.length, 0);
  await view.cleanup();
});

test("Start sends the chosen settings once on a double click, with the client's option names", async () => {
  const { calls } = stub();
  const view = await show();
  await view.click(button(view.document, "Relaxed")!);
  await view.setSelect(byLabel(view.document, "Output profile"), "draft_720p");
  await view.click(button(view.document, "Cinematic zoom")!);
  await view.clickTwice(button(view.document, "Start render")!);
  await view.settle();
  assert.equal(calls.start.length, 1);
  assert.deepEqual(calls.start[0], ["p1", {
    profileName: "draft_720p", customOutputPath: "C:\\Users\\user\\Videos", subtitleEnabled: false, bgmVolumeDb: -10, dialogueGainDb: 0, isDraft: true,
    minPanelDuration: 5.5, panelZoomMode: "motion", narrationSpeed: 1, videoEngine: "fast_h3", motionFx: "none",
  }]);
  await view.cleanup();
});

test("a render running when the stage opens is followed: progress and Cancel, no settings, no restart, and polling stops after leaving", async () => {
  const { calls } = stub({ renders: [render("r1", "ENCODING", { current_stage: "ENCODING", frames_done: 400, frames_total: 1000 })] });
  const view = await show();
  assert.ok(button(view.document, "Cancel render"));
  assert.equal(button(view.document, "Start render"), undefined);
  assert.equal(byLabel(view.document, "Output profile"), null);
  assert.ok(text(view.document).includes("Encoding"));
  assert.ok(text(view.document).includes("400 / 1,000 frames"));
  assert.equal(view.document.querySelector('[role="progressbar"]')!.getAttribute("aria-valuenow"), "40");
  assert.equal(calls.start.length, 0);
  await view.cleanup();
  const after = calls.listRenders;
  await new Promise((r) => setTimeout(r, 1300));
  assert.equal(calls.listRenders, after, "no polling after the stage unmounted");
});

test("Cancel render cancels once", async () => {
  const { calls } = stub({ renders: [render("r1", "ENCODING")] });
  const view = await show();
  await view.clickTwice(button(view.document, "Cancel render")!);
  await view.settle();
  assert.deepEqual(calls.cancel, ["r1"]);
  await view.cleanup();
});

test("when a followed render finishes, the project is reloaded and handed over once", async () => {
  const { calls, set } = stub({ renders: [render("r1", "ENCODING")] });
  let handed = 0;
  const view = await show(() => { handed++; });
  set([render("r1", "COMPLETE", { progress: 1, frames_done: 1000 })]);
  await until(() => handed > 0, 6000);
  await new Promise((r) => setTimeout(r, 300));
  assert.equal(handed, 1);
  assert.equal(calls.getProject, 1);
  await view.cleanup();
});

test("a followed render that fails says why without paths, and a cancelled one is a notice", async () => {
  const a = stub({ renders: [render("r1", "ENCODING")] });
  const view = await show();
  a.set([render("r1", "FAILED", { error_message: "The encoder stopped unexpectedly." })]);
  await until(() => text(view.document).includes("Render failed."), 6000);
  assert.ok(text(view.document).includes("Render failed. The encoder stopped unexpectedly."));
  assert.ok(!/C:\\|https?:\/\//.test(view.document.querySelector('[role="alert"]')!.textContent!));
  await view.cleanup();
  const b = stub({ renders: [render("r2", "ENCODING")] });
  const view2 = await show();
  b.set([render("r2", "CANCELLED")]);
  await until(() => text(view2.document).includes("Render cancelled."), 6000);
  assert.ok(text(view2.document).includes("Render cancelled."));
  assert.equal(view2.document.querySelector('[role="alert"]'), null);
  await view2.cleanup();
});

test("a failed start explains itself and keeps the settings", async () => {
  stub({ over: { startRender: async () => { throw new Error("ENOENT C:\\engine\\x.py"); } } });
  const view = await show();
  await view.click(button(view.document, "Start render")!);
  await view.settle();
  assert.ok(text(view.document).includes("Couldn't start the render"));
  assert.ok(!text(view.document).includes("x.py"));
  assert.ok(byLabel(view.document, "Output profile"));
  await view.cleanup();
});

test("the folder and save-as pickers fill the location, a picker failure is shown, and quick folders set it", async () => {
  stub();
  const view = await show();
  const location = () => byLabel(view.document, "Save location") as HTMLInputElement;
  await view.click(button(view.document, "Browse folder")!);
  assert.equal(location().value, "D:\\Exports");
  await view.click(button(view.document, "Save as file")!);
  assert.equal(location().value, "D:\\Exports\\video.mp4");
  await view.click(button(view.document, "Desktop")!);
  assert.equal(location().value, "C:\\Users\\user\\Desktop");
  await view.cleanup();
  stub({ over: { pickDirectoryNative: async () => { throw new Error("no ui"); } } });
  const failing = await show();
  await failing.click(button(failing.document, "Browse folder")!);
  await failing.settle();
  assert.ok(text(failing.document).includes("Couldn't open the folder picker."));
  await failing.cleanup();
});

test("a typed save location is sent", async () => {
  const { calls } = stub();
  const view = await show();
  await view.setValue(byLabel(view.document, "Save location"), "  D:\\Mine  ");
  await view.click(button(view.document, "Start render")!);
  await view.settle();
  assert.equal(calls.start[0][1].customOutputPath, "D:\\Mine");
  await view.cleanup();
});

test("history lists renders newest first; out-of-date renders explain themselves and offer nothing; Open file opens once", async () => {
  const { calls } = stub({ renders: [
    render("old", "COMPLETE", { created_at: "2026-11-01T10:00:00Z" }),
    render("stale", "STALE", { created_at: "2026-11-08T12:00:00Z" }),
    render("done", "COMPLETE", { created_at: "2026-11-05T10:00:00Z" }),
  ] });
  const view = await show();
  const rows = [...view.document.querySelectorAll("[data-render-id]")];
  assert.deepEqual(rows.map((r) => r.getAttribute("data-render-id")), ["stale", "done", "old"]);
  assert.ok(rows[0].textContent!.includes("Out of date"));
  assert.ok(rows[0].textContent!.includes("the project changed after this render"));
  assert.equal(rows[0].querySelectorAll("button").length, 0);
  await view.clickTwice(button(rows[1], "Open file")!);
  assert.deepEqual(calls.open, [["C:\\Users\\user\\renders\\done.mp4", true]]);
  await view.cleanup();
});

test("the latest finished render is shown with its video and checks, and View switches to another", async () => {
  stub({ renders: [
    render("new", "COMPLETE", { created_at: "2026-11-08T12:00:00Z", validation_report: { is_valid: true, gate_status: "PRODUCTION_READY", warnings: [] } }),
    render("old", "COMPLETE", { created_at: "2026-11-01T12:00:00Z", validation_report: { is_valid: false, warnings: ["Black frames"], black_frames_count: 3 } }),
    render("stale", "STALE", { created_at: "2026-11-09T12:00:00Z" }),
  ] });
  const view = await show();
  assert.equal(view.document.querySelector("video")!.getAttribute("src"), "/video/new.mp4");
  assert.ok(text(view.document).includes("Ready for production"));
  const oldRow = view.document.querySelector('[data-render-id="old"]')!;
  await view.click(button(oldRow, "View")!);
  assert.equal(view.document.querySelector("video")!.getAttribute("src"), "/video/old.mp4");
  assert.ok(text(view.document).includes("Did not pass"));
  await view.cleanup();
});

test("Continue to publish goes to the Publish stage", async () => {
  stub({ renders: [render("c1", "COMPLETE")] });
  const view = await show();
  await view.click(button(view.document, "Continue to publish")!);
  await view.settle();
  assert.equal(view.router.state.location.pathname, "/projects/p1/publish");
  await view.cleanup();
});
