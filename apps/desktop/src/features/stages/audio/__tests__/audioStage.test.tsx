import { mountPage } from "../../../__tests__/pageHarness"; // first: installs jsdom before Radix loads
import React from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { api } from "@panelflow/api-client";
import type { Project } from "@panelflow/shared-types";
import { AudioStage } from "../AudioStage";
import type { AudioLike } from "../useIntervalPlayback";

const project = (stage = "SCRIPT_APPROVED") => ({ id: "p1", title: "Dawn Gate", current_stage: stage, rights_status: "AUTHORIZED_WEB", stale_stages: [] }) as unknown as Project;

const INTERVALS = [
  { interval_id: "i1", audio_file_uri: "one.wav", start_time: 0, end_time: 2, duration: 2, gain_db: 0, script_segment_id: "seg1", cue_text: "Hello there", character_id: "c1", is_voice: true },
  { interval_id: "i2", start_time: 2, end_time: 3, duration: 1, gain_db: 0, is_voice: false },
  { interval_id: "i3", audio_file_uri: "two.wav", start_time: 3, end_time: 5, duration: 2, gain_db: -1, script_segment_id: "seg2", cue_text: "Goodbye", is_voice: true },
];
const timeline = (status = "DRAFT") => ({
  id: "t1", project_id: "p1", status, total_duration: 5, voice_casting: {}, warnings: ["Line 3 is slightly long"],
  timeline: { timeline_id: "t", project_id: "p1", total_duration_sec: 5, sample_rate_hz: 24000, channels: 1, speech_intervals_count: 2, intervals: INTERVALS },
  created_at: "", updated_at: "",
});
const VOICES = [{ id: "vx1", name: "Voice X1", gender: "Female" }, { id: "vx2", name: "Voice X2", gender: "Male" }];
const CHARACTERS = [{ character_id: "c1", canonical_name: "Zed", display_name: "Zed", aliases: [], role: "protagonist" }];

class FakeAudio implements AudioLike {
  src = ""; playbackRate = 1; muted = false; volume = 1; currentTime = 0; played: string[] = []; pauses = 0;
  play() { this.played.push(this.src); return Promise.resolve(); }
  pause() { this.pauses++; }
  addEventListener() {} removeEventListener() {}
}

interface Calls { generate: Array<Record<string, string> | undefined>; regen: string[]; approve: number; getProject: number; getJob: number }
function stub(opts: { timeline?: any; jobs?: any[]; over?: Record<string, unknown> } = {}) {
  const calls: Calls = { generate: [], regen: [], approve: 0, getProject: 0, getJob: 0 };
  let current = opts.timeline ?? null;
  Object.assign(api as any, {
    getAudioTimeline: async () => { if (!current) throw new Error("404"); return current; },
    listCharacters: async () => CHARACTERS,
    getAudioProviders: async () => ({ primary_provider: "tts", providers: [{ id: "tts", voices: VOICES }] }),
    listProjectJobs: async () => opts.jobs ?? [],
    generateAudioJob: async (_id: string, casting?: Record<string, string>) => { calls.generate.push(casting); current = timeline(); return { job_id: "ja" }; },
    getJob: async (id: string) => { calls.getJob++; return (opts.jobs ?? []).find((j) => j.job_id === id) ?? { job_id: id, job_type: "AUDIO_GENERATION", status: "SUCCEEDED", progress: 1, message: "Done", error: null }; },
    regenerateAudioSegment: async (_id: string, seg: string) => { calls.regen.push(seg); return { status: "ok" }; },
    approveAudio: async () => { calls.approve++; return { approved: true, message: "" }; },
    getProject: async () => { calls.getProject++; return project("AUDIO_APPROVED"); },
    getAudioFileUrl: (_p: string, uri: string) => `/audio/${uri}`,
    ...opts.over,
  });
  return calls;
}
const text = (d: Document) => d.body.textContent ?? "";
const button = (d: Document | Element, label: string | RegExp) => [...d.querySelectorAll("button")].find((b) => (typeof label === "string" ? b.textContent?.trim() === label || b.getAttribute("aria-label") === label : label.test(b.textContent ?? "") || label.test(b.getAttribute("aria-label") ?? ""))) as HTMLButtonElement | undefined;
const dialogButton = (d: Document, label: string) => [...d.querySelectorAll('[role="dialog"] button')].find((b) => b.textContent?.trim() === label) as HTMLButtonElement | undefined;

async function show(p = project(), onApproved: (u: Project) => void = () => {}, onContinue: (p: Project) => void = () => {}, audio = new FakeAudio()) {
  const view = await mountPage(<AudioStage project={p} onApproved={onApproved} onContinue={onContinue} playback={{ createAudio: () => audio }} />);
  await view.settle();
  return { view, audio };
}

test("no timeline yet: it invites generating, with no player and no Approve", async () => {
  stub();
  const { view } = await show();
  assert.equal(view.document.querySelectorAll("h1").length, 0);
  assert.ok(text(view.document).includes("No voice track yet"));
  assert.ok(button(view.document, "Generate audio"));
  assert.equal(button(view.document, "Approve audio"), undefined);
  assert.equal(button(view.document, "Play all"), undefined);
  await view.cleanup();
});

test("generating sends the default casting from the engine's voices once, even on a double click, and then shows the takes", async () => {
  const calls = stub();
  const { view } = await show();
  await view.clickTwice(button(view.document, "Generate audio")!);
  await view.settle();
  assert.equal(calls.generate.length, 1);
  assert.deepEqual(calls.generate[0], { c1: "vx1", Zed: "vx1" });
  assert.ok(text(view.document).includes("Hello there"));
  assert.ok(text(view.document).includes("Goodbye"));
  await view.cleanup();
});

test("a generation already running when the stage opens is followed, not restarted, and polling stops after leaving", async () => {
  const running = { job_id: "jx", job_type: "AUDIO_GENERATION", status: "RUNNING", progress: 0.4, message: "Line 2 of 5", error: null };
  const calls = stub({ jobs: [running] });
  const { view } = await show();
  assert.equal(calls.generate.length, 0);
  assert.ok(text(view.document).includes("Line 2 of 5"));
  await view.cleanup();
  const after = calls.getJob;
  await new Promise((resolve) => setTimeout(resolve, 1300));
  assert.equal(calls.getJob, after, "no polling after the stage unmounted");
});

test("with an existing timeline, regenerating asks first", async () => {
  const calls = stub({ timeline: timeline() });
  const { view } = await show();
  await view.click(button(view.document, "Regenerate audio")!);
  assert.ok(text(view.document).includes("Replace the voice track?"));
  await view.click(dialogButton(view.document, "Cancel")!);
  assert.equal(calls.generate.length, 0);
  await view.click(button(view.document, "Regenerate audio")!);
  await view.click(dialogButton(view.document, "Replace voice track")!);
  await view.settle();
  assert.equal(calls.generate.length, 1);
  await view.cleanup();
});

test("the casting dialog lists the engine's voices and a changed choice is sent with the next generation", async () => {
  const calls = stub();
  const { view } = await show();
  await view.click(button(view.document, "Voice casting")!);
  const select = view.document.querySelector('[aria-label="Voice for Zed"]') as HTMLSelectElement;
  assert.deepEqual([...select.options].map((o) => o.textContent), ["Automatic", "Voice X1", "Voice X2"]);
  assert.equal(select.value, "vx1", "starts from the default casting");
  await view.setSelect(select, "vx2");
  await view.click(dialogButton(view.document, "Save and generate")!);
  await view.settle();
  assert.deepEqual(calls.generate[0], { c1: "vx2", Zed: "vx2" });
  await view.cleanup();
});

test("choosing Automatic leaves the character out of the casting", async () => {
  const calls = stub();
  const { view } = await show();
  await view.click(button(view.document, "Voice casting")!);
  await view.setSelect(view.document.querySelector('[aria-label="Voice for Zed"]') as HTMLSelectElement, "");
  await view.click(dialogButton(view.document, "Save and generate")!);
  await view.settle();
  assert.deepEqual(calls.generate[0], {});
  await view.cleanup();
});

test("if the voice list cannot be loaded, generation still works with the engine's defaults and the dialog says so", async () => {
  const calls = stub({ over: { getAudioProviders: async () => { throw new Error("down"); } } });
  const { view } = await show();
  await view.click(button(view.document, "Voice casting")!);
  assert.ok(text(view.document).includes("Couldn't load the voice list"));
  await view.click(dialogButton(view.document, "Cancel")!);
  await view.click(button(view.document, "Generate audio")!);
  await view.settle();
  assert.deepEqual(calls.generate, [{}]);
  await view.cleanup();
});

test("a failed generation explains itself without paths or product names", async () => {
  stub({ over: { generateAudioJob: async () => { throw new Error("Chatterbox missing at C:\\Tools\\Chatterbox\\run.py"); } } });
  const { view } = await show();
  await view.click(button(view.document, "Generate audio")!);
  await view.settle();
  const body = text(view.document);
  assert.ok(body.includes("Couldn't generate the audio"));
  assert.ok(!body.includes("C:\\") && !body.includes("Chatterbox"));
  assert.ok(button(view.document, "Generate audio"), "can try again");
  await view.cleanup();
});

test("a generation job that ends in failure is reported the same way", async () => {
  const failed = { job_id: "ja", job_type: "AUDIO_GENERATION", status: "FAILED", progress: 0.2, message: "x", error: "Speech provider is not ready." };
  stub({ jobs: [], over: { getJob: async () => failed } });
  const { view } = await show();
  await view.click(button(view.document, "Generate audio")!);
  await view.settle();
  assert.ok(text(view.document).includes("Couldn't generate the audio. Speech provider is not ready."));
  await view.cleanup();
});

test("Regenerate take regenerates that one line once and reloads the timeline", async () => {
  const calls = stub({ timeline: timeline() });
  const { view } = await show();
  await view.clickTwice(button(view.document, "Regenerate take 1")!);
  await view.settle();
  assert.deepEqual(calls.regen, ["seg1"]);
  await view.cleanup();
});

test("Approve audio approves once, reloads the project and hands it over", async () => {
  const calls = stub({ timeline: timeline() });
  const handed: Project[] = [];
  const { view } = await show(project(), (u) => handed.push(u));
  await view.clickTwice(button(view.document, "Approve audio")!);
  await view.settle();
  assert.equal(calls.approve, 1);
  assert.equal(calls.getProject, 1);
  assert.equal(handed.length, 1);
  assert.equal(handed[0].current_stage, "AUDIO_APPROVED");
  await view.cleanup();
});

test("a refused approval shows the reason and does not move on", async () => {
  stub({ timeline: timeline(), over: { approveAudio: async () => { throw new Error("A line has no audio file."); } } });
  let moved = 0;
  const { view } = await show(project(), () => { moved++; });
  await view.click(button(view.document, "Approve audio")!);
  await view.settle();
  assert.ok(text(view.document).includes("Audio can't be approved yet. A line has no audio file."));
  assert.equal(moved, 0);
  assert.equal(button(view.document, "Approve audio")!.disabled, false);
  await view.cleanup();
});

test("an approved timeline cannot be approved again and offers Continue to motion", async () => {
  stub({ timeline: timeline("APPROVED") });
  let continued = 0;
  const { view } = await show(project("AUDIO_APPROVED"), () => {}, () => { continued++; });
  assert.equal(button(view.document, "Audio approved")!.disabled, true);
  await view.click(button(view.document, "Continue to motion")!);
  assert.equal(continued, 1);
  await view.cleanup();
});

test("the player plays the first take, pauses, and releases the audio when the stage is left", async () => {
  stub({ timeline: timeline() });
  const { view, audio } = await show();
  assert.ok(text(view.document).includes("Line 3 is slightly long"), "engine warnings are shown");
  await view.click(button(view.document, "Play all")!);
  assert.deepEqual(audio.played, ["/audio/one.wav"]);
  assert.ok(button(view.document, "Pause"));
  await view.click(button(view.document, "Pause")!);
  assert.ok(audio.pauses >= 1);
  await view.cleanup();
  assert.equal(audio.src, "");
});

test("Play take starts that line, and a silent gap is shown as silence", async () => {
  stub({ timeline: timeline() });
  const { view, audio } = await show();
  assert.ok(text(view.document).includes("Silence"));
  await view.click(button(view.document, "Play take 3")!);
  assert.deepEqual(audio.played, ["/audio/two.wav"]);
  await view.cleanup();
});

test("the summary shows length, lines, sample rate and how many characters are cast", async () => {
  stub({ timeline: timeline() });
  const { view } = await show();
  const body = text(view.document);
  assert.ok(body.includes("0:05"));
  assert.ok(body.includes("2 takes"));
  assert.ok(body.includes("24,000 Hz"));
  assert.ok(body.includes("1 of 1 characters"));
  await view.cleanup();
});

test("the space bar plays and pauses, except when a button or field has the focus", async () => {
  stub({ timeline: timeline() });
  const { view, audio } = await show();
  const { act } = await import("react");
  const press = (target: Element) => act(async () => { target.dispatchEvent(new KeyboardEvent("keydown", { code: "Space", key: " ", bubbles: true, cancelable: true })); });
  await press(view.document.body);
  assert.deepEqual(audio.played, ["/audio/one.wav"], "space on the page starts playback");
  const pausesBefore = audio.pauses;
  await press(button(view.document, "Voice casting")!);
  assert.equal(audio.pauses, pausesBefore, "space on a button does not pause playback");
  assert.ok(button(view.document, "Pause"), "still playing");
  await view.cleanup();
});

// The engine's real shapes, taken from a saved project: `text` and `speaker_character_id` on intervals, `sample_rate`,
// no speech_intervals_count, and characters that have an `id` and a null canonical_name.
const REAL_TIMELINE = {
  id: "t1", project_id: "p1", status: "DRAFT", total_duration: 137.87, voice_casting: { Narrator: "am_michael" }, warnings: [],
  timeline: {
    timeline_id: "t", total_duration_sec: 137.87, sample_rate: 24000, channels: 1,
    intervals: [
      { interval_id: "r1", script_segment_id: "s1", speaker_character_id: "abc", text: "A glowing object streaks across the sky.", start_time: 0.12, end_time: 3.92, is_speech: true, audio_file_uri: "C:\p\one.wav" },
      { interval_id: "r2", start_time: 3.92, end_time: 4.4, is_speech: false },
      { interval_id: "r3", script_segment_id: "s2", speaker_character_id: null, text: "He looked up.", start_time: 4.4, end_time: 6, is_speech: true, audio_file_uri: "C:\p\two.wav" },
    ],
  },
};
const REAL_CHARACTERS = [{ id: "abc", canonical_name: null, display_name: "Shangguan Yulin", aliases: [], role: "UNKNOWN" }, { id: "def", canonical_name: null, display_name: "Luo Yunhai", aliases: [], role: "UNKNOWN" }];

test("the engine's real field names are read: speech count, sample rate, speaker, text, duration", async () => {
  stub({ timeline: REAL_TIMELINE, over: { listCharacters: async () => REAL_CHARACTERS } });
  const { view } = await show();
  const body = text(view.document);
  assert.ok(body.includes("2 takes"), "speech takes are counted when the engine sends no count");
  assert.ok(body.includes("24,000 Hz"), "sample_rate is read");
  assert.ok(body.includes("Shangguan Yulin"), "the speaker is found by id");
  assert.ok(body.includes("A glowing object streaks across the sky."), "text is shown");
  assert.ok(body.includes("3.80s"), "duration comes from the start and end");
  assert.ok(body.includes("2:18"));
  await view.cleanup();
});

test("a timeline with no sample rate says it was not reported instead of inventing one", async () => {
  const noRate = JSON.parse(JSON.stringify(REAL_TIMELINE));
  delete noRate.timeline.sample_rate;
  stub({ timeline: noRate });
  const { view } = await show();
  assert.ok(text(view.document).includes("Not reported"));
  assert.ok(!text(view.document).includes("48,000"));
  await view.cleanup();
});

test("characters that have only an id are cast, and the saved narrator voice is shown in the dialog", async () => {
  const calls = stub({ timeline: REAL_TIMELINE, over: { listCharacters: async () => REAL_CHARACTERS } });
  const { view } = await show();
  assert.ok(text(view.document).includes("2 of 2 characters"), "both are cast by default");
  await view.click(button(view.document, "Voice casting")!);
  const narrator = view.document.querySelector('[aria-label="Narrator voice"]') as HTMLSelectElement;
  assert.equal(narrator.value, "am_michael", "a saved voice the engine no longer lists is kept");
  assert.ok([...narrator.options].some((o) => o.textContent === "am_michael (saved)"));
  assert.ok(view.document.querySelector('[aria-label="Voice for Shangguan Yulin"]'));
  await view.click(dialogButton(view.document, "Save and generate")!);
  await view.settle();
  assert.equal(calls.generate.length, 1);
  assert.equal(calls.generate[0]!.Narrator, "am_michael", "the saved narrator voice is sent unchanged");
  assert.equal(calls.generate[0]!.abc, "vx1");
  assert.equal(calls.generate[0]!.def, "vx2");
  await view.cleanup();
});
