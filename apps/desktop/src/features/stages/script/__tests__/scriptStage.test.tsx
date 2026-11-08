import { mountPage } from "../../../__tests__/pageHarness"; // first: installs jsdom before Radix loads
import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { api } from "@panelflow/api-client";
import type { Project } from "@panelflow/shared-types";
import { ScriptStage } from "../ScriptStage";

const project = (stage = "STORY_APPROVED", settings: Record<string, any> = {}) => ({ id: "p1", title: "Dawn Gate", current_stage: stage, rights_status: "AUTHORIZED_WEB", stale_stages: [], settings }) as unknown as Project;

const seg = (n: number, over: Record<string, unknown> = {}) => ({
  segment_id: `s${n}`, scene_id: "sc", sequence: n, type: n === 2 ? "DIALOGUE" : "NARRATOR", speaker_character_id: n === 2 ? "c1" : null, text: `Line number ${n}`,
  emotion: "NEUTRAL", intensity: 0.5, estimated_duration: 2, estimated_start: n * 2, estimated_end: n * 2 + 2,
  source_evidence: { panel_ids: [`pn${n}`], text_region_ids: [`r${n}`] }, faithfulness_status: n === 2 ? "UNSUPPORTED" : "SUPPORTED", manual_override: false, ...over,
});
const scriptDoc = (over: Record<string, unknown> = {}) => ({
  script_id: "sc1", project_id: "p1", version: "1", adaptation_profile: "DRAMATIC_NARRATION", segments: [seg(1), seg(2), seg(3)], estimated_duration: 130, language: "en",
  status: "DRAFT", quality_metrics: {}, created_at: "", updated_at: "", ...over,
});
const reportDoc = (over: Record<string, unknown> = {}) => ({
  script_id: "sc1", total_segments: 3, supported_segments: 2, weakly_supported_segments: 0, unsupported_segments: 1, coverage_score: 0.753, passed: false,
  issues: [{ segment_id: "s2", status: "UNSUPPORTED", text: "Line number 2", reasons: ["No panel shows this."] }], ...over,
});
const storyboardDoc = (n = 3) => ({
  project_id: "p1", script_id: "sc1", version: "1", total_duration_sec: 130, created_at: "", updated_at: "",
  segments: Array.from({ length: n }, (_, i) => ({ segment_id: `s${i + 1}`, scene_id: "sc", sequence: i + 1, text: `Line number ${i + 1}`, emotion: "NEUTRAL", intensity: 0.5, audio_clip_path: null, measured_duration_sec: 2, supporting_panels: [], music_cue: { intent: "CALM", ducking_gain_db: -14 }, sfx_cue: { type: "NONE", offset_sec: 0 }, manual_override: false })),
});
const genJob = (status: string, over: Record<string, unknown> = {}) => ({ job_id: "jg", project_id: "p1", job_type: "SCRIPT_GENERATION", status, progress: 0.5, message: "Adapting", input: {}, output: {}, error: null, created_at: null, started_at: null, finished_at: null, ...over });

interface Calls { generate: Array<string | undefined>; validate: number; approve: number; getProject: number; getJob: number }
function stub(opts: { script?: any; storyboard?: any; report?: any; jobs?: any[]; jobResult?: any; over?: Record<string, unknown> } = {}) {
  const calls: Calls = { generate: [], validate: 0, approve: 0, getProject: 0, getJob: 0 };
  let script = opts.script ?? null;
  Object.assign(api as any, {
    getScript: async () => { if (!script) throw new Error("No script generated yet for this project."); return script; },
    getStoryboard: async () => { if (!opts.storyboard) throw new Error("none"); return opts.storyboard; },
    getNarrative: async () => ({ characters: [{ character_id: "c1", display_name: "Shangguan Yulin", canonical_name: null, aliases: [] }], utterances: [] }),
    listCharacters: async () => [],
    listProjectJobs: async () => opts.jobs ?? [],
    generateScriptJob: async (_id: string, profile?: string) => { calls.generate.push(profile); script = scriptDoc({ script_id: "sc2" }); return { job_id: "jg" }; },
    getJob: async (id: string) => { calls.getJob++; return opts.jobResult ?? (opts.jobs ?? []).find((j) => j.job_id === id) ?? genJob("SUCCEEDED", { progress: 1 }); },
    validateScript: async () => { calls.validate++; if (opts.over?.validateScript) return (opts.over.validateScript as any)(); return opts.report ?? reportDoc(); },
    approveScript: async () => { calls.approve++; return { script_id: "sc1", status: "APPROVED", message: "" }; },
    getProject: async () => { calls.getProject++; return project("SCRIPT_APPROVED"); },
    getPanelImageUrl: (_p: string, id: string) => `/panel/${id}.png`,
    ...Object.fromEntries(Object.entries(opts.over ?? {}).filter(([k]) => k !== "validateScript")),
  });
  return calls;
}
const text = (d: Document) => d.body.textContent ?? "";
const button = (d: Document | Element, label: string | RegExp) => [...d.querySelectorAll("button")].find((b) => (typeof label === "string" ? b.textContent?.trim() === label : label.test(b.textContent ?? ""))) as HTMLButtonElement | undefined;
const dialogButton = (d: Document, label: string) => [...d.querySelectorAll('[role="dialog"] button')].find((b) => b.textContent?.trim() === label) as HTMLButtonElement | undefined;
const tab = (d: Document, label: RegExp) => [...d.querySelectorAll('[role="tab"]')].find((t) => label.test(t.textContent ?? "")) as HTMLElement;
const ids = (d: Document) => [...d.querySelectorAll("[data-segment-id]")].map((e) => e.getAttribute("data-segment-id"));
async function until(cond: () => boolean, ms = 4000) { for (let i = 0; i < ms / 25 && !cond(); i++) await new Promise((r) => setTimeout(r, 25)); }

async function show(p = project(), onApproved: (u: Project) => void = () => {}, onContinue: (p: Project) => void = () => {}) {
  const view = await mountPage(<ScriptStage project={p} onApproved={onApproved} onContinue={onContinue} onProjectUpdated={() => {}} />);
  await view.settle();
  return view;
}

test("no script (the real project's state, with a storyboard still on file): it invites generating and shows nothing it cannot back up", async () => {
  const calls = stub({ storyboard: storyboardDoc(36) });
  const view = await show();
  assert.equal(view.document.querySelectorAll("h1").length, 0);
  assert.equal(view.document.querySelectorAll("h2").length, 1);
  assert.ok(text(view.document).includes("No script yet"));
  assert.ok(button(view.document, "Generate script"));
  assert.equal(ids(view.document).length, 0, "the orphaned storyboard is not shown");
  assert.equal(button(view.document, "Validate faithfulness"), undefined);
  assert.equal(button(view.document, "Approve script"), undefined);
  assert.ok(!text(view.document).includes("Coverage"), "no coverage is shown without a script");
  assert.equal(calls.validate, 0, "nothing is validated when there is no script");
  await view.cleanup();
});

test("generating sends the chosen profile once on a double click, follows the job, then loads and validates the new script once", async () => {
  const calls = stub();
  const view = await show(project("STORY_APPROVED", { visual_storytelling: true }));
  assert.equal((view.document.querySelector('[aria-label="Adaptation profile"]') as HTMLSelectElement).value, "DRAMATIC_NARRATION");
  await view.clickTwice(button(view.document, "Generate script")!);
  await until(() => ids(view.document).length === 3 && calls.validate >= 1);
  await new Promise((r) => setTimeout(r, 200));
  assert.deepEqual(calls.generate, ["DRAMATIC_NARRATION"]);
  assert.equal(calls.validate, 1, "validated once for the new script");
  await view.cleanup();
});

test("the profile defaults to Faithful for a normal project", async () => {
  stub();
  const view = await show();
  assert.equal((view.document.querySelector('[aria-label="Adaptation profile"]') as HTMLSelectElement).value, "FAITHFUL");
  await view.cleanup();
});

test("a generation already running when the stage opens is followed, not restarted, and polling stops after leaving", async () => {
  const running = genJob("RUNNING", { message: "Adapting scene 2 of 7" });
  const calls = stub({ jobs: [running] });
  const view = await show();
  assert.equal(calls.generate.length, 0);
  assert.ok(text(view.document).includes("Adapting scene 2 of 7"));
  await view.cleanup();
  const after = calls.getJob;
  await new Promise((r) => setTimeout(r, 1300));
  assert.equal(calls.getJob, after, "no polling after the stage unmounted");
});

test("re-adapting asks first, and Cancel starts nothing", async () => {
  const calls = stub({ script: scriptDoc() });
  const view = await show();
  await view.click(button(view.document, "Re-adapt script")!);
  assert.ok(text(view.document).includes("Replace the current script?"));
  await view.click(dialogButton(view.document, "Cancel")!);
  assert.equal(calls.generate.length, 0);
  await view.click(button(view.document, "Re-adapt script")!);
  await view.click(dialogButton(view.document, "Re-adapt script")!);
  await view.settle();
  assert.equal(calls.generate.length, 1);
  await view.cleanup();
});

test("a loaded script is validated once, not on every render, and coverage comes from the report", async () => {
  const calls = stub({ script: scriptDoc() });
  const view = await show();
  await new Promise((r) => setTimeout(r, 300));
  assert.equal(calls.validate, 1);
  const body = text(view.document);
  assert.ok(body.includes("75%"));
  assert.ok(body.includes("Dramatic narration"));
  assert.ok(body.includes("3 lines"));
  assert.ok(body.includes("2:10"));
  assert.ok(!body.includes("Milestone 4"), "the stale boundary banner is gone");
  await view.cleanup();
});

test("when validation fails, coverage says Not checked and Validate tries again", async () => {
  let fail = true;
  const calls = stub({ script: scriptDoc(), over: { validateScript: () => { if (fail) throw new Error("boom C:\\engine\\x.py"); return reportDoc(); } } });
  const view = await show();
  assert.ok(text(view.document).includes("Not checked"));
  assert.ok(text(view.document).includes("Validation unavailable"));
  assert.ok(!text(view.document).includes("x.py"));
  fail = false;
  await view.click(button(view.document, "Validate faithfulness")!);
  await until(() => text(view.document).includes("75%"));
  assert.equal(calls.validate, 2);
  assert.ok(!text(view.document).includes("Validation unavailable"));
  await view.cleanup();
});

test("unsupported statements are listed with their reasons, and the toggle shows only those lines", async () => {
  stub({ script: scriptDoc() });
  const view = await show();
  const banner = view.document.querySelector('[data-unsupported-banner]')!;
  assert.ok(banner);
  assert.ok(banner.textContent!.includes("1 unsupported statement blocks approval"));
  assert.ok(banner.textContent!.includes("No panel shows this."));
  assert.deepEqual(ids(view.document), ["s1", "s2", "s3"]);
  const toggle = button(view.document, "Show unsupported only")!;
  assert.equal(toggle.getAttribute("aria-pressed"), "false");
  await view.click(toggle);
  assert.deepEqual(ids(view.document), ["s2"]);
  assert.equal(button(view.document, "Show unsupported only")!.getAttribute("aria-pressed"), "true");
  await view.cleanup();
});

test("Approve script is blocked, with the reason, while the report says it did not pass", async () => {
  const calls = stub({ script: scriptDoc() });
  const view = await show();
  const approve = button(view.document, "Approve script")!;
  assert.equal(approve.disabled, true);
  assert.ok(text(view.document).includes("1 unsupported line must be fixed first."));
  await view.click(approve);
  assert.equal(calls.approve, 0);
  await view.cleanup();
});

test("Approve script approves once, reloads the project and hands it over", async () => {
  const calls = stub({ script: scriptDoc(), report: reportDoc({ passed: true, unsupported_segments: 0, issues: [] }) });
  const handed: Project[] = [];
  const view = await show(project(), (u) => handed.push(u));
  await view.clickTwice(button(view.document, "Approve script")!);
  await view.settle();
  assert.equal(calls.approve, 1);
  assert.equal(calls.getProject, 1);
  assert.equal(handed.length, 1);
  assert.equal(handed[0].current_stage, "SCRIPT_APPROVED");
  await view.cleanup();
});

test("a refused approval refetches the report, shows the reason and does not move on", async () => {
  const passed = reportDoc({ passed: true, unsupported_segments: 0, issues: [] });
  const calls = stub({ script: scriptDoc(), report: passed, over: { approveScript: async () => { throw new Error("Line 2 is not grounded in the source."); } } });
  let moved = 0;
  const view = await show(project(), () => { moved++; });
  const before = calls.validate;
  await view.click(button(view.document, "Approve script")!);
  await view.settle();
  assert.ok(text(view.document).includes("Script can't be approved yet. Line 2 is not grounded in the source."));
  assert.equal(moved, 0);
  assert.equal(calls.validate, before + 1, "the report is fetched again so the flagged lines show");
  await view.cleanup();
});

test("an approved script offers Continue to audio and cannot be approved again", async () => {
  stub({ script: scriptDoc({ status: "APPROVED" }), report: reportDoc({ passed: true, unsupported_segments: 0, issues: [] }) });
  let continued = 0;
  const view = await show(project("SCRIPT_APPROVED"), () => {}, () => { continued++; });
  assert.equal(button(view.document, "Script approved")!.disabled, true);
  assert.equal(button(view.document, "Approve script"), undefined);
  await view.click(button(view.document, "Continue to audio")!);
  assert.equal(continued, 1);
  await view.cleanup();
});

test("failed generation, by request or by job, is explained without paths or addresses", async () => {
  stub({ over: { generateScriptJob: async () => { throw new Error("ECONNRESET http://127.0.0.1:11434 at C:\\engine\\x.py"); } } });
  const a = await show();
  await a.click(button(a.document, "Generate script")!);
  await a.settle();
  assert.ok(text(a.document).includes("Couldn't generate the script"));
  assert.ok(!/https?:\/\/|C:\\|x\.py/.test(text(a.document)));
  await a.cleanup();
  stub({ jobResult: genJob("FAILED", { error: "Model returned invalid JSON" }) });
  const b = await show();
  await b.click(button(b.document, "Generate script")!);
  await until(() => text(b.document).includes("Model returned invalid JSON"));
  assert.ok(text(b.document).includes("Couldn't generate the script. Model returned invalid JSON"));
  await b.cleanup();
});

test("with a storyboard the Storyboard view is first, and the Spoken script view is one tab away", async () => {
  stub({ script: scriptDoc(), storyboard: storyboardDoc(3) });
  const view = await show();
  assert.equal(tab(view.document, /^Storyboard/).getAttribute("aria-selected"), "true");
  assert.deepEqual(ids(view.document), ["s1", "s2", "s3"]);
  await view.press(tab(view.document, /^Spoken script/));
  assert.equal(tab(view.document, /^Spoken script/).getAttribute("aria-selected"), "true");
  assert.deepEqual(ids(view.document), ["s1", "s2", "s3"]);
  await view.cleanup();
});
