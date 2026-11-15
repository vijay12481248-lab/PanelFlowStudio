import { mountPage } from "../../../__tests__/pageHarness"; // first: installs jsdom before Radix loads
import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { api } from "@panelflow/api-client";
import type { Project } from "@panelflow/shared-types";
import { StoryStage } from "../StoryStage";

const project = (stage = "OCR_APPROVED", settings: Record<string, any> = {}) => ({ id: "p1", title: "Dawn Gate", current_stage: stage, rights_status: "AUTHORIZED_WEB", stale_stages: [], settings }) as unknown as Project;

// Real shapes: narrative characters have character_id but a null canonical_name; scenes have scene_id.
const utterance = (n: number, speaker: string | null = "c1") => ({
  utterance_id: `u${n}`, text_region_id: `r${n}`, panel_id: `pn${n}`, speaker_character_id: speaker, source_text: `Line ${n}`, corrected_text: `Line ${n}`,
  utterance_type: "DIALOGUE", emotion: "NEUTRAL", sequence: n,
});
const narrativeDoc = (over: Record<string, unknown> = {}) => ({
  project_id: "p1", version: "1", language: "en",
  characters: [
    { character_id: "c1", display_name: "Shangguan Yulin", canonical_name: null, aliases: ["Yulin"], description: "A young man", role: "UNKNOWN", status: "LIKELY", manual_override: false },
    { character_id: "c2", display_name: "Red Demon", canonical_name: null, aliases: [], description: "", role: "ANTAGONIST", status: "CONFIRMED", manual_override: true },
  ],
  scenes: [
    { scene_id: "s1", sequence: 1, title: "The gate", summary: "A glowing object falls", boundary_reason: "LOCATION_CHANGE", panel_start: "pn1", panel_end: "pn3", character_ids: [] },
    { scene_id: "s2", sequence: 2, title: "The hall", summary: "The demon speaks", boundary_reason: "TIME_JUMP", panel_start: "pn4", panel_end: "pn6", character_ids: [] },
  ],
  beats: [
    { beat_id: "b1", scene_id: "s1", sequence: 1, panel_ids: ["pn1"], event_ids: ["e1"], summary: "Object streaks across the sky", dramatic_function: "INCITING_INCIDENT", importance: "HIGH", intensity: 0.8, music_intent: "TENSE" },
    { beat_id: "b2", scene_id: "s2", sequence: 1, panel_ids: ["pn4"], event_ids: [], summary: "The demon laughs", dramatic_function: "RISING_ACTION", importance: "MEDIUM", intensity: 0.4 },
  ],
  events: [{ event_id: "e1", event_type: "ACTION", description: "A comet crosses the sky", panel_ids: ["pn1"] }],
  utterances: [utterance(1), utterance(2, null), utterance(3, "ghost")],
  continuity_warnings: [],
  ...over,
});
const providerList = (...ids: Array<[string, boolean, boolean]>) => ids.map(([id, local, healthy]) => ({ provider_id: id, provider_name: id === "mock_llm" ? "Mock Deterministic LLM" : `Model ${id}`, is_local: local, is_multimodal: true, is_healthy: healthy }));
const HEALTHY = providerList(["mock_llm", false, true], ["ollama", true, true]);
const analysisJob = (status: string, over: Record<string, unknown> = {}) => ({ job_id: "ja", project_id: "p1", job_type: "STORY_ANALYSIS", status, progress: 0.4, message: "", input: {}, output: {}, error: null, created_at: "2026-11-08T11:58:00Z", started_at: null, finished_at: null, ...over });

interface Calls { analyze: Array<string | undefined>; cancel: number; confirm: number; getProject: number; getJob: number; speaker: any[] }
function stub(opts: { narrative?: any; providers?: any[]; jobs?: any[]; jobResult?: any; over?: Record<string, unknown> } = {}) {
  const calls: Calls = { analyze: [], cancel: 0, confirm: 0, getProject: 0, getJob: 0, speaker: [] };
  let current = opts.narrative ?? null;
  Object.assign(api as any, {
    getNarrative: async () => { if (!current) throw new Error("404"); return current; },
    listLLMProviders: async () => opts.providers ?? HEALTHY,
    listPanels: async () => [{ id: "pn1", sequence: 1 }, { id: "pn2", sequence: 2 }, { id: "pn3", sequence: 3 }],
    listCharacters: async () => [],
    listProjectJobs: async () => opts.jobs ?? [],
    analyzeStory: async (_id: string, provider?: string) => { calls.analyze.push(provider); current = narrativeDoc(); return { job_id: "ja", message: "" }; },
    getJob: async (id: string) => { calls.getJob++; return opts.jobResult ?? (opts.jobs ?? []).find((j) => j.job_id === id) ?? analysisJob("SUCCEEDED", { progress: 1 }); },
    cancelJob: async () => { calls.cancel++; return { status: "ok", message: "" }; },
    confirmStory: async () => { calls.confirm++; return { project_id: "p1", current_stage: "STORY_APPROVED", message: "" }; },
    getProject: async () => { calls.getProject++; return project("STORY_APPROVED"); },
    updateTextRegion: async (...args: any[]) => { calls.speaker.push(args); },
    ...opts.over,
  });
  return { calls, setNarrative: (n: any) => { current = n; } };
}
const text = (d: Document) => d.body.textContent ?? "";
const button = (d: Document | Element, label: string | RegExp) => [...d.querySelectorAll("button")].find((b) => (typeof label === "string" ? b.textContent?.trim() === label : label.test(b.textContent ?? ""))) as HTMLButtonElement | undefined;
const dialogButton = (d: Document, label: string) => [...d.querySelectorAll('[role="dialog"] button')].find((b) => b.textContent?.trim() === label) as HTMLButtonElement | undefined;
const tab = (d: Document, label: RegExp) => [...d.querySelectorAll('[role="tab"]')].find((t) => label.test(t.textContent ?? "")) as HTMLElement;
async function until(cond: () => boolean, ms = 4000) { for (let i = 0; i < ms / 25 && !cond(); i++) await new Promise((r) => setTimeout(r, 25)); }

async function show(p = project(), onApproved: (u: Project) => void = () => {}, onContinue: (p: Project) => void = () => {}) {
  const view = await mountPage(<StoryStage project={p} onApproved={onApproved} onContinue={onContinue} />);
  await view.settle();
  return view;
}

test("no analysis yet: it invites running one, with one h2 and no h1", async () => {
  stub();
  const view = await show();
  assert.equal(view.document.querySelectorAll("h1").length, 0);
  assert.equal(view.document.querySelectorAll("h2").length, 1);
  assert.ok(text(view.document).includes("No story analysis yet"));
  assert.ok(button(view.document, "Run story analysis"));
  assert.equal(button(view.document, /Approve story/), undefined);
  await view.cleanup();
});

test("the model select never preselects a mock provider and labels it as test data", async () => {
  stub();
  const view = await show();
  const select = view.document.querySelector('[aria-label="Model"]') as HTMLSelectElement;
  assert.equal(select.value, "ollama");
  const mock = [...select.options].find((o) => o.value === "mock_llm")!;
  assert.ok(mock.textContent!.includes("Test data only"));
  assert.equal(button(view.document, "Run story analysis")!.disabled, false);
  await view.cleanup();
});

test("with no healthy real model, Run is disabled and says why", async () => {
  for (const providers of [providerList(["mock_llm", false, true]), providerList(["ollama", true, false]), []]) {
    stub({ providers });
    const view = await show();
    assert.equal(button(view.document, "Run story analysis")!.disabled, true);
    assert.ok(text(view.document).includes("No healthy local model is available"));
    await view.cleanup();
  }
});

test("running the analysis sends the chosen model once on a double click, follows the job and loads the result", async () => {
  const { calls } = stub();
  const view = await show();
  await view.clickTwice(button(view.document, "Run story analysis")!);
  await until(() => Boolean(button(view.document, /Approve story/)));
  assert.deepEqual(calls.analyze, ["ollama"]);
  assert.ok(button(view.document, /Approve story/), "the finished analysis can be approved");
  await view.cleanup();
});

test("an analysis already running when the stage opens is followed, not restarted, and polling stops after leaving", async () => {
  const running = analysisJob("RUNNING", { message: "Vision analysis: panel 3/40", input: { total_panels: 40 } });
  const { calls } = stub({ jobs: [running] });
  const view = await show();
  assert.equal(calls.analyze.length, 0);
  assert.ok(button(view.document, "Cancel analysis"));
  assert.ok(text(view.document).includes("Panels checked: 3/40"));
  await view.cleanup();
  const after = calls.getJob;
  await new Promise((r) => setTimeout(r, 1300));
  assert.equal(calls.getJob, after, "no polling after the stage unmounted");
});

test("Cancel analysis cancels once", async () => {
  const { calls } = stub({ jobs: [analysisJob("RUNNING")] });
  const view = await show();
  await view.clickTwice(button(view.document, "Cancel analysis")!);
  await view.settle();
  assert.equal(calls.cancel, 1);
  await view.cleanup();
});

test("a failed analysis explains itself without paths or addresses", async () => {
  stub({ jobResult: analysisJob("FAILED", { error: "Model output exceeded the limit" }) });
  const view = await show();
  await view.click(button(view.document, "Run story analysis")!);
  await until(() => text(view.document).includes("Couldn't analyse the story"));
  const body = text(view.document);
  assert.ok(body.includes("Couldn't analyse the story. Model output exceeded the limit"));
  assert.ok(!/https?:\/\/|C:\\/.test(body));
  await view.cleanup();
});

test("a failed start explains what to do and never shows the raw exception", async () => {
  stub({ over: { analyzeStory: async () => { throw new Error("ECONNRESET at C:\\engine\\x.py"); } } });
  const view = await show();
  await view.click(button(view.document, "Run story analysis")!);
  await view.settle();
  assert.ok(text(view.document).includes("Couldn't start the story analysis"));
  assert.ok(!text(view.document).includes("x.py"));
  assert.ok(button(view.document, "Run story analysis"));
  await view.cleanup();
});

test("a cancelled analysis is reported as a notice, not as an error", async () => {
  stub({ jobResult: analysisJob("CANCELLED", { message: "Cancelled by user" }) });
  const view = await show();
  await view.click(button(view.document, "Run story analysis")!);
  await until(() => text(view.document).includes("Analysis cancelled."));
  assert.ok(text(view.document).includes("Analysis cancelled."));
  assert.equal(view.document.querySelector('[role="alert"]'), null);
  await view.cleanup();
});

test("losing contact with the engine while following a job is shown, with a way to check again", async () => {
  stub({ jobs: [analysisJob("RUNNING")], over: { getJob: async () => { throw new Error("down"); } } });
  const view = await show();
  await until(() => text(view.document).includes("Lost contact with the engine."));
  assert.ok(text(view.document).includes("Lost contact with the engine."));
  assert.ok(button(view.document, "Check again"));
  await view.cleanup();
});

test("re-analysing asks first and Cancel starts nothing", async () => {
  const { calls } = stub({ narrative: narrativeDoc() });
  const view = await show();
  await view.click(button(view.document, "Re-analyze story")!);
  assert.ok(text(view.document).includes("Replace the current analysis?"));
  await view.click(dialogButton(view.document, "Cancel")!);
  assert.equal(calls.analyze.length, 0);
  await view.click(button(view.document, "Re-analyze story")!);
  await view.click(dialogButton(view.document, "Re-analyze story")!);
  await view.settle();
  assert.equal(calls.analyze.length, 1);
  await view.cleanup();
});

test("approving is blocked, with the reason, while there are unresolved continuity errors", async () => {
  const { calls } = stub({ narrative: narrativeDoc({ continuity_warnings: [{ warning_id: "w1", warning_type: "DEAD_CHARACTER_SPEAKS", severity: "ERROR", message: "Speaks after death", entity_id: "c2", resolved: false }] }) });
  const view = await show();
  const approve = button(view.document, "Approve story")!;
  assert.equal(approve.disabled, true);
  assert.ok(text(view.document).includes("1 continuity error must be resolved first."));
  await view.click(approve);
  assert.equal(calls.confirm, 0);
  await view.cleanup();
});

test("Approve story confirms once, reloads the project and hands it over", async () => {
  const { calls } = stub({ narrative: narrativeDoc() });
  const handed: Project[] = [];
  const view = await show(project(), (u) => handed.push(u));
  await view.clickTwice(button(view.document, "Approve story")!);
  await view.settle();
  assert.equal(calls.confirm, 1);
  assert.equal(calls.getProject, 1);
  assert.equal(handed.length, 1);
  assert.equal(handed[0].current_stage, "STORY_APPROVED");
  await view.cleanup();
});

test("a refused approval shows the engine's reason, does not move on, and can be tried again", async () => {
  stub({ narrative: narrativeDoc(), over: { confirmStory: async () => { throw new Error("Characters still need review."); } } });
  let moved = 0;
  const view = await show(project(), () => { moved++; });
  await view.click(button(view.document, "Approve story")!);
  await view.settle();
  assert.ok(text(view.document).includes("Story can't be approved yet. Characters still need review."));
  assert.equal(moved, 0);
  assert.equal(button(view.document, "Approve story")!.disabled, false);
  await view.cleanup();
});

test("an approved story offers Continue to script and cannot be approved again", async () => {
  stub({ narrative: narrativeDoc() });
  let continued = 0;
  const view = await show(project("SCRIPT_APPROVED"), () => {}, () => { continued++; });
  assert.equal(button(view.document, "Story approved")!.disabled, true);
  assert.equal(button(view.document, "Approve story"), undefined);
  await view.click(button(view.document, "Continue to script")!);
  assert.equal(continued, 1);
  await view.cleanup();
});

test("Scenes and beats puts each beat and event under its own scene, using the real field names", async () => {
  stub({ narrative: narrativeDoc() });
  const view = await show();
  await view.press(tab(view.document, /^Scenes and beats/));
  const body = text(view.document);
  assert.ok(body.includes("The gate") && body.includes("The hall"));
  const gate = view.document.querySelector('[data-scene-id="s1"]')!.textContent!;
  const hall = view.document.querySelector('[data-scene-id="s2"]')!.textContent!;
  assert.ok(gate.includes("Object streaks across the sky") && gate.includes("A comet crosses the sky"));
  assert.ok(!gate.includes("The demon laughs"));
  assert.ok(hall.includes("The demon laughs"));
  assert.ok(gate.includes("Panel 1"), "events name their panels");
  await view.cleanup();
});

test("each utterance shows its speaker in words and a select to change it", async () => {
  stub({ narrative: narrativeDoc() });
  const view = await show();
  await view.press(tab(view.document, /^Utterances/));
  const rows = [...view.document.querySelectorAll("[data-utterance-id]")];
  assert.equal(rows.length, 3);
  assert.ok(rows[0].textContent!.includes("Shangguan Yulin"));
  assert.ok(rows[1].textContent!.includes("Unknown"));
  assert.ok(rows[2].textContent!.includes("Unknown"), "an id that matches nobody is not shown raw");
  assert.ok(!text(view.document).includes("ghost"));
  const select = rows[0].querySelector("select")!;
  assert.deepEqual([...select.options].map((o) => o.textContent), ["Unknown", "Narrator", "Sound effect", "Shangguan Yulin", "Red Demon"]);
  await view.cleanup();
});

test("changing a speaker sends MANUAL once even if changed again while saving", async () => {
  const { calls } = stub({ narrative: narrativeDoc(), over: { updateTextRegion: async (...args: any[]) => { calls0.push(args); await new Promise(() => {}); } } });
  const calls0: any[] = [];
  void calls;
  const view = await show();
  await view.press(tab(view.document, /^Utterances/));
  const select = () => view.document.querySelector('[data-utterance-id="u1"] select') as HTMLSelectElement;
  await view.setSelect(select(), "c2");
  await view.setSelect(select(), "NARRATOR");
  assert.equal(calls0.length, 1, "the second change is held until the first is saved");
  assert.deepEqual(calls0[0], ["p1", "r1", { speaker_character_id: "c2", speaker_assignment_method: "MANUAL" }]);
  await view.cleanup();
});

test("a failed speaker change restores the previous speaker and says so", async () => {
  stub({ narrative: narrativeDoc(), over: { updateTextRegion: async () => { throw new Error("nope"); } } });
  const view = await show();
  await view.press(tab(view.document, /^Utterances/));
  const select = () => view.document.querySelector('[data-utterance-id="u1"] select') as HTMLSelectElement;
  await view.setSelect(select(), "c2");
  await view.settle();
  assert.equal(select().value, "c1");
  assert.ok(text(view.document).includes("Couldn't change the speaker."));
  await view.cleanup();
});

test("a long utterance list shows 100 rows and Show more reveals the rest", async () => {
  const many = Array.from({ length: 150 }, (_, i) => utterance(i + 1));
  stub({ narrative: narrativeDoc({ utterances: many }) });
  const view = await show();
  await view.press(tab(view.document, /^Utterances/));
  assert.equal(view.document.querySelectorAll("[data-utterance-id]").length, 100);
  await view.click(button(view.document, /^Show more/)!);
  assert.equal(view.document.querySelectorAll("[data-utterance-id]").length, 150);
  assert.equal(button(view.document, /^Show more/), undefined);
  await view.cleanup();
});

test("Continuity shows its warnings in words, or says the story is consistent", async () => {
  stub({ narrative: narrativeDoc({ continuity_warnings: [{ warning_id: "w1", warning_type: "DEAD_CHARACTER_SPEAKS", severity: "WARNING", message: "Speaks after death", entity_id: "c2", resolved: false }] }) });
  const view = await show();
  await view.press(tab(view.document, /^Continuity/));
  assert.ok(text(view.document).includes("Speaks after death"));
  assert.ok(text(view.document).includes("Warning"));
  await view.cleanup();
  stub({ narrative: narrativeDoc() });
  const clean = await show();
  await clean.press(tab(clean.document, /^Continuity/));
  assert.ok(text(clean.document).includes("No continuity warnings"));
  await clean.cleanup();
});

test("Characters show display names when the canonical name is null", async () => {
  stub({ narrative: narrativeDoc() });
  const view = await show();
  const body = text(view.document);
  assert.ok(body.includes("Shangguan Yulin") && body.includes("Red Demon"));
  assert.ok(body.includes("Yulin"), "aliases are shown");
  await view.cleanup();
});
