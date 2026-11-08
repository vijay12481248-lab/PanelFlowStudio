import { mountPage } from "../../../__tests__/pageHarness"; // first: installs jsdom before Radix loads
import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { act } from "react";
import { api } from "@panelflow/api-client";
import type { Project } from "@panelflow/shared-types";
import { ScriptStage } from "../ScriptStage";

const project = () => ({ id: "p1", title: "Dawn Gate", current_stage: "SCRIPT_GENERATED", rights_status: "AUTHORIZED_WEB", stale_stages: [], settings: {} }) as unknown as Project;

const seg = (n: number, over: Record<string, unknown> = {}) => ({
  segment_id: `s${n}`, scene_id: "sc", sequence: n, type: n === 2 ? "DIALOGUE" : "NARRATOR", speaker_character_id: n === 2 ? "c1" : null, text: `Line number ${n}`,
  emotion: "NEUTRAL", intensity: 0.5, estimated_duration: 2, estimated_start: n * 2, estimated_end: n * 2 + 2, motion_intent: "PUSH", music_intent: "CALM", sfx_intent: null,
  source_evidence: { panel_ids: [`pn${n}`], text_region_ids: [`r${n}1`] }, faithfulness_status: n === 2 ? "UNSUPPORTED" : n === 3 ? "WEAKLY_SUPPORTED" : "SUPPORTED", manual_override: n === 3, ...over,
});
const scriptDoc = () => ({ script_id: "sc1", project_id: "p1", version: "1", adaptation_profile: "FAITHFUL", segments: [seg(1), seg(2), seg(3)], estimated_duration: 130, language: "en", status: "DRAFT", quality_metrics: {}, created_at: "", updated_at: "" });
const reportDoc = () => ({ script_id: "sc1", total_segments: 3, supported_segments: 1, weakly_supported_segments: 1, unsupported_segments: 1, coverage_score: 0.7, passed: false, issues: [{ segment_id: "s2", status: "UNSUPPORTED", text: "Line number 2", reasons: ["No panel shows this."] }] });
const panelRef = (id: string, order: number, type: string, intensity: number) => ({ panel_id: id, reading_order: order, role: "ESTABLISHING", crop_bounds: { x: 0, y: 0, width: 1, height: 1 }, sub_duration_sec: 1.5, camera_motion: { type, intensity }, crop_filename: `${id}.png` });
const storyboardDoc = () => ({
  project_id: "p1", script_id: "sc1", version: "1", total_duration_sec: 130, created_at: "", updated_at: "",
  segments: [1, 2, 3].map((n) => ({
    segment_id: `s${n}`, scene_id: "sc", sequence: n, text: `Line number ${n}`, emotion: "NEUTRAL", intensity: 0.5, audio_clip_path: n === 1 ? "audio/1.wav" : null, measured_duration_sec: 2,
    supporting_panels: [panelRef(`pn${n}`, 1, "SLOW_PUSH", 0.5), panelRef(`pn${n}b`, 2, "PAN", 0.2)], music_cue: { intent: "CALM", ducking_gain_db: -14 }, sfx_cue: { type: "NONE", offset_sec: 0 }, manual_override: n === 3,
  })),
});

interface Calls { edit: any[][]; update: any[][]; board: any[][]; realign: number; validate: number; getProject: number }
function stub(opts: { storyboard?: boolean; over?: Record<string, unknown> } = {}) {
  const calls: Calls = { edit: [], update: [], board: [], realign: 0, validate: 0, getProject: 0 };
  let script: any = scriptDoc();
  Object.assign(api as any, {
    getScript: async () => script,
    getStoryboard: async () => { if (!opts.storyboard) throw new Error("none"); return storyboardDoc(); },
    getNarrative: async () => ({ characters: [{ character_id: "c1", display_name: "Shangguan Yulin", canonical_name: null, aliases: [] }], utterances: [] }),
    listCharacters: async () => [],
    listProjectJobs: async () => [],
    getJob: async () => ({ status: "SUCCEEDED", progress: 1 }),
    validateScript: async () => { calls.validate++; return reportDoc(); },
    editScriptSegment: async (...a: any[]) => { calls.edit.push(a); return script; },
    updateScriptSegment: async (...a: any[]) => { calls.update.push(a); script = { ...script, segments: script.segments.map((s: any) => (s.segment_id === a[2] ? { ...s, text: a[3].text ?? s.text } : s)) }; return {}; },
    updateStoryboardSegment: async (...a: any[]) => { calls.board.push(a); return { ...storyboardDoc().segments[0], segment_id: a[1], ...a[2] }; },
    realignStoryboard: async () => { calls.realign++; return storyboardDoc(); },
    getProject: async () => { calls.getProject++; return project(); },
    getPanelImageUrl: (_p: string, id: string) => `/panel/${id}.png`,
    ...opts.over,
  });
  return calls;
}
const text = (d: Document) => d.body.textContent ?? "";
const button = (d: Document | Element, label: string | RegExp) => [...d.querySelectorAll("button")].find((b) => (typeof label === "string" ? b.textContent?.trim() === label || b.getAttribute("aria-label") === label : label.test(b.textContent ?? "") || label.test(b.getAttribute("aria-label") ?? ""))) as HTMLButtonElement | undefined;
const dialogButton = (d: Document, label: string) => [...d.querySelectorAll('[role="dialog"] button')].find((b) => b.textContent?.trim() === label) as HTMLButtonElement | undefined;
const card = (d: Document, id: string) => d.querySelector(`[data-segment-id="${id}"]`) as HTMLElement;
const byLabel = (root: ParentNode, label: string) => root.querySelector(`[aria-label="${label}"]`) as any;
const tab = (d: Document, label: RegExp) => [...d.querySelectorAll('[role="tab"]')].find((t) => label.test(t.textContent ?? "")) as HTMLElement;
const menuItem = (d: Document, label: string) => [...d.querySelectorAll('[role="menuitem"]')].find((i) => i.textContent?.trim() === label) as HTMLElement;
async function openMenu(view: { press: (el: Element) => Promise<void>; document: Document }, n: number) {
  await view.press(byLabel(view.document, `Line actions for line ${n}`));
}
async function until(cond: () => boolean, ms = 3000) { for (let i = 0; i < ms / 25 && !cond(); i++) await new Promise((r) => setTimeout(r, 25)); }

async function show() {
  const view = await mountPage(<ScriptStage project={project()} onApproved={() => {}} onContinue={() => {}} onProjectUpdated={() => {}} />);
  await view.settle();
  await until(() => Boolean(card(view.document, "s1")));
  return view;
}

test("editing a line saves exactly the edited fields, once on a double click", async () => {
  const calls = stub();
  const view = await show();
  await view.click(button(card(view.document, "s1"), "Edit line 1")!);
  const save = () => button(view.document, "Save line")!;
  assert.equal(save().disabled, true, "nothing changed yet");
  await view.setSelect(byLabel(view.document, "Emotion"), "TENSE");
  await view.setValue(byLabel(view.document, "Intensity"), "0.8");
  await view.setValue(byLabel(view.document, "Estimated seconds"), "3.5");
  assert.equal(save().disabled, false);
  await view.clickTwice(save());
  await until(() => calls.update.length > 0);
  await view.settle();
  assert.equal(calls.update.length, 1);
  assert.deepEqual(calls.update[0], ["p1", "sc1", "s1", { text: "Line number 1", emotion: "TENSE", intensity: 0.8, estimated_duration: 3.5 }]);
  assert.equal(calls.getProject, 1, "the project is reloaded");
  assert.equal(byLabel(view.document, "Line text"), null, "the editor closes");
  await view.cleanup();
});

test("a blank line cannot be saved", async () => {
  const calls = stub();
  const view = await show();
  await view.click(button(card(view.document, "s1"), "Edit line 1")!);
  const area = byLabel(view.document, "Line text") as HTMLTextAreaElement;
  await act(async () => {
    Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value")!.set!.call(area, "   ");
    area.dispatchEvent(new window.Event("input", { bubbles: true }));
  });
  assert.equal(button(view.document, "Save line")!.disabled, true);
  assert.equal(calls.update.length, 0);
  await view.cleanup();
});

test("a failed save keeps the editor open and says so in words", async () => {
  stub({ over: { updateScriptSegment: async () => { throw new Error("Segment is locked by audio."); } } });
  const view = await show();
  await view.click(button(card(view.document, "s1"), "Edit line 1")!);
  await view.setSelect(byLabel(view.document, "Emotion"), "SAD");
  await view.click(button(view.document, "Save line")!);
  await until(() => text(view.document).includes("Couldn't save the line"));
  assert.ok(text(view.document).includes("Couldn't save the line. Segment is locked by audio."));
  assert.ok(byLabel(view.document, "Line text"), "still open");
  await view.cleanup();
});

test("Edit this line on an unsupported statement opens that line's editor", async () => {
  stub();
  const view = await show();
  await until(() => Boolean(button(view.document, "Edit this line")));
  await view.click(button(view.document, "Edit this line")!);
  assert.ok(card(view.document, "s2").querySelector('[aria-label="Line text"]'));
  await view.cleanup();
});

test("Remove asks first, and Cancel sends nothing", async () => {
  const calls = stub();
  const view = await show();
  await openMenu(view, 1);
  await view.press(menuItem(view.document, "Remove"));
  assert.ok(text(view.document).includes("Remove this line from the script?"));
  await view.click(dialogButton(view.document, "Cancel")!);
  assert.equal(calls.edit.length, 0);
  await openMenu(view, 1);
  await view.press(menuItem(view.document, "Remove"));
  await view.clickTwice(dialogButton(view.document, "Remove")!);
  await until(() => calls.edit.length > 0);
  assert.deepEqual(calls.edit, [["p1", "sc1", "s1", "remove"]]);
  await view.cleanup();
});

test("Merge with next also asks first", async () => {
  const calls = stub();
  const view = await show();
  await openMenu(view, 2);
  await view.press(menuItem(view.document, "Merge with next"));
  assert.ok(text(view.document).includes("Join this line with the next one?"));
  assert.equal(calls.edit.length, 0);
  await view.click(dialogButton(view.document, "Cancel")!);
  await view.cleanup();
});

test("a non-destructive action is sent at once, then the old report is dropped and validation runs once more", async () => {
  const calls = stub();
  const view = await show();
  await until(() => calls.validate >= 1);
  const before = calls.validate;
  await openMenu(view, 1);
  await view.press(menuItem(view.document, "Shorten"));
  await until(() => calls.edit.length > 0 && calls.validate > before);
  await new Promise((r) => setTimeout(r, 150));
  assert.deepEqual(calls.edit, [["p1", "sc1", "s1", "shorten"]]);
  assert.equal(calls.validate, before + 1, "revalidated exactly once");
  await view.cleanup();
});

test("while one line action runs, every line's menu is disabled and a second action is not sent", async () => {
  const calls = stub({ over: { editScriptSegment: async (...a: any[]) => { calls.edit.push(a); await new Promise(() => {}); } } });
  const view = await show();
  await openMenu(view, 1);
  await view.press(menuItem(view.document, "Expand"));
  await until(() => calls.edit.length === 1);
  assert.equal(byLabel(view.document, "Line actions for line 1").disabled, true);
  assert.equal(byLabel(view.document, "Line actions for line 2").disabled, true);
  assert.equal(button(view.document, "Approve script")!.disabled, true, "approval waits for the change");
  await view.cleanup();
});

test("a failed action says so and leaves the script as it was", async () => {
  stub({ over: { editScriptSegment: async () => { throw new Error("Cannot split a one-word line."); } } });
  const view = await show();
  await openMenu(view, 1);
  await view.press(menuItem(view.document, "Split"));
  await until(() => text(view.document).includes("Couldn't change that line"));
  assert.ok(text(view.document).includes("Couldn't change that line. Cannot split a one-word line."));
  assert.ok(card(view.document, "s1"));
  await view.cleanup();
});

test("each line shows its faithfulness status in words, its edits and its source panels", async () => {
  stub();
  const view = await show();
  assert.ok(card(view.document, "s1").textContent!.includes("Supported"));
  assert.ok(card(view.document, "s2").textContent!.includes("Unsupported"));
  assert.ok(card(view.document, "s3").textContent!.includes("Weakly supported"));
  assert.ok(card(view.document, "s3").textContent!.includes("Edited"));
  assert.ok(card(view.document, "s1").querySelector('img[src="/panel/pn1.png"]'));
  assert.ok(card(view.document, "s2").textContent!.includes("Shangguan Yulin"));
  assert.ok(card(view.document, "s1").textContent!.includes("Motion PUSH"));
  await view.cleanup();
});

test("a source panel that cannot load shows an unavailable state and Retry preview adds a cache-buster", async () => {
  stub();
  const view = await show();
  const img = card(view.document, "s1").querySelector("img")!;
  await view.fire(img, "error");
  assert.ok(card(view.document, "s1").textContent!.includes("Panel preview unavailable"));
  await view.click(button(card(view.document, "s1"), "Retry preview")!);
  assert.ok(card(view.document, "s1").querySelector("img")!.getAttribute("src")!.includes("preview_retry=1"));
  await view.cleanup();
});

test("the unsupported filter applies in the Storyboard view too", async () => {
  stub({ storyboard: true });
  const view = await show();
  assert.equal(tab(view.document, /^Storyboard/).getAttribute("aria-selected"), "true");
  assert.equal(view.document.querySelectorAll("[data-segment-id]").length, 3);
  await view.click(button(view.document, "Show unsupported only")!);
  assert.deepEqual([...view.document.querySelectorAll("[data-segment-id]")].map((e) => e.getAttribute("data-segment-id")), ["s2"]);
  await view.cleanup();
});

test("a beat shows its panels, voice state and cues; changing one panel's camera motion sends the whole list with only that panel changed", async () => {
  const calls = stub({ storyboard: true });
  const view = await show();
  const first = card(view.document, "s1");
  assert.ok(first.textContent!.includes("Voice locked"));
  assert.ok(card(view.document, "s2").textContent!.includes("Estimated"));
  assert.ok(card(view.document, "s3").textContent!.includes("Locked override"));
  assert.ok(first.textContent!.includes("-14 dB"));
  await view.setSelect(byLabel(first, "Camera motion for panel 2 of beat 1"), "STATIC");
  await until(() => calls.board.length > 0);
  assert.equal(calls.board.length, 1);
  const [projectId, segmentId, patch] = calls.board[0];
  assert.deepEqual([projectId, segmentId], ["p1", "s1"]);
  assert.equal(patch.supporting_panels.length, 2);
  assert.deepEqual(patch.supporting_panels[0], storyboardDoc().segments[0].supporting_panels[0], "the first panel is untouched");
  assert.deepEqual(patch.supporting_panels[1].camera_motion, { type: "STATIC", intensity: 0.2 });
  await view.cleanup();
});

test("the beat editor can change intensity, and saving revalidates once", async () => {
  const calls = stub({ storyboard: true });
  const view = await show();
  await until(() => calls.validate >= 1);
  const before = calls.validate;
  await view.click(button(card(view.document, "s1"), "Edit beat 1")!);
  assert.equal(byLabel(view.document, "Estimated seconds"), null, "storyboard beats have no estimated-seconds field");
  await view.setValue(byLabel(view.document, "Intensity"), "0.9");
  await view.clickTwice(button(view.document, "Save beat")!);
  await until(() => calls.board.length > 0 && calls.validate > before);
  assert.equal(calls.board.length, 1);
  assert.deepEqual(calls.board[0], ["p1", "s1", { text: "Line number 1", emotion: "NEUTRAL", intensity: 0.9 }]);
  assert.equal(calls.validate, before + 1);
  await view.cleanup();
});

test("Realign frames runs once on a double click", async () => {
  const calls = stub({ storyboard: true });
  const view = await show();
  await view.clickTwice(button(view.document, /^Realign frames/)!);
  await until(() => calls.realign > 0);
  await view.settle();
  assert.equal(calls.realign, 1);
  await view.cleanup();
});

test("the line menu works from the keyboard: Enter opens it and Escape closes it", async () => {
  stub();
  const view = await show();
  const trigger = byLabel(view.document, "Line actions for line 1") as HTMLElement;
  trigger.focus();
  await act(async () => { trigger.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter", bubbles: true, cancelable: true })); });
  assert.ok(view.document.querySelector('[role="menu"]'), "the menu opens");
  assert.equal(view.document.querySelectorAll('[role="menuitem"]').length, 10);
  await act(async () => { view.document.querySelector('[role="menu"]')!.dispatchEvent(new KeyboardEvent("keydown", { key: "Escape", bubbles: true, cancelable: true })); });
  assert.equal(view.document.querySelector('[role="menu"]'), null, "Escape closes it");
  await view.cleanup();
});
