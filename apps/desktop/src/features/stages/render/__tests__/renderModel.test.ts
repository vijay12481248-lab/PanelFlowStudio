import test from "node:test";
import assert from "node:assert/strict";
import type { RenderJob } from "@panelflow/shared-types";
import { DEFAULT_SETTINGS, activeRender, clampSettings, formatBytes, isRunning, outputName, profileChoices, renderStatus, startOptions, validationSummary } from "../renderModel";

const job = (status: string, over: Partial<RenderJob> = {}) => ({ render_id: status, project_id: "p", status, current_stage: "", progress: 0, frames_done: 0, frames_total: 0, output_profile: "standard_1080p", output_path: "", created_at: "2026-11-08T10:00:00Z", ...over }) as RenderJob;

// The engine's real profile list, trimmed.
const REAL_PROFILES = [
  { id: "standard_1080p", name: "Full HD 1080p (Landscape 16:9)", width: 1920, height: 1080, fps: 30, description: "Recommended for YouTube." },
  { id: "vertical_shorts", name: "Vertical 1080p (Portrait 9:16)", width: 1080, height: 1920, fps: 30 },
  { id: "square_feed", name: "Square 1080p (Feed 1:1)", width: 1080, height: 1080, fps: 30 },
  { id: "draft_720p", name: "Fast Draft 720p (Ultra Fast)", width: 1280, height: 720, fps: 30 },
];

// The real report of a COMPLETE render: production ready, but sync_valid is false.
const REAL_REPORT = {
  is_valid: true, gate_status: "PRODUCTION_READY", file_size_bytes: 92299740, planned_duration_sec: 137.87, actual_duration_sec: 137.866667, duration_diff_sec: 0.003,
  black_frames_count: 0, timeline_gaps_count: 0, clipping_samples_count: 0, sync_valid: false, duration_sec: 137.866667, warnings: [], frame_samples: [{}, {}, {}, {}, {}],
};

test("only the engine's running statuses count as running; STALE never does", () => {
  for (const s of ["QUEUED", "PREPARING", "COMPOSING", "ENCODING", "MUXING", "VALIDATING"]) assert.equal(isRunning(job(s)), true, s);
  for (const s of ["COMPLETE", "FAILED", "CANCELLED", "STALE", "SOMETHING_NEW"]) assert.equal(isRunning(job(s)), false, s);
});

test("the active render is the newest running one and skips stale and finished renders", () => {
  const renders = [job("STALE", { created_at: "2026-11-08T12:00:00Z" }), job("COMPLETE", { created_at: "2026-11-08T11:00:00Z" }), job("ENCODING", { render_id: "old", created_at: "2026-11-08T09:00:00Z" }), job("COMPOSING", { render_id: "new", created_at: "2026-11-08T10:30:00Z" })];
  assert.equal(activeRender(renders)?.render_id, "new");
  assert.equal(activeRender([job("STALE"), job("COMPLETE"), job("FAILED")]), null);
  assert.equal(activeRender([]), null);
});

test("statuses are words", () => {
  assert.deepEqual(renderStatus("COMPLETE"), { word: "Done", tone: "ok" });
  assert.deepEqual(renderStatus("FAILED"), { word: "Failed", tone: "bad" });
  assert.deepEqual(renderStatus("CANCELLED"), { word: "Cancelled", tone: "warn" });
  assert.deepEqual(renderStatus("STALE"), { word: "Out of date", tone: "warn" });
  assert.deepEqual(renderStatus("QUEUED"), { word: "Waiting", tone: "neutral" });
  assert.equal(renderStatus("VALIDATING").word, "Checking");
  assert.equal(renderStatus("ENCODING").word, "Encoding");
  assert.deepEqual(renderStatus("SOME_NEW_STATE"), { word: "Some new state", tone: "neutral" });
});

test("profiles come from the engine, with a size hint, and are never invented", () => {
  const choice = profileChoices(REAL_PROFILES);
  assert.deepEqual(choice.options.map((o) => o.id), ["standard_1080p", "vertical_shorts", "square_feed", "draft_720p"]);
  assert.equal(choice.options[0].label, "Full HD 1080p (Landscape 16:9)");
  assert.equal(choice.options[0].hint, "1920x1080 · 30 fps");
  assert.equal(choice.defaultId, "standard_1080p");
  assert.equal(choice.fromEngine, true);
  assert.equal(profileChoices(REAL_PROFILES.slice(1)).defaultId, "vertical_shorts", "the first profile when there is no standard one");
  for (const none of [null, undefined, []]) assert.deepEqual(profileChoices(none as any), { options: [], defaultId: null, fromEngine: false });
});

test("settings are held inside the ranges of the controls", () => {
  const low = clampSettings({ ...DEFAULT_SETTINGS, minPanelDuration: 0, bgmVolumeDb: -99, dialogueGainDb: -50, narrationSpeed: 0.1, panelZoomMode: "x" as any, videoEngine: "x" as any, motionFx: "x" });
  assert.deepEqual([low.minPanelDuration, low.bgmVolumeDb, low.dialogueGainDb, low.narrationSpeed], [1.5, -30, -6, 0.85]);
  assert.deepEqual([low.panelZoomMode, low.videoEngine, low.motionFx], ["fit", "fast_h3", "none"]);
  const high = clampSettings({ ...DEFAULT_SETTINGS, minPanelDuration: 99, bgmVolumeDb: 5, dialogueGainDb: 50, narrationSpeed: 9 });
  assert.deepEqual([high.minPanelDuration, high.bgmVolumeDb, high.dialogueGainDb, high.narrationSpeed], [8, 0, 6, 1.2]);
  assert.equal(clampSettings({ ...DEFAULT_SETTINGS, minPanelDuration: 3.2 }).minPanelDuration, 3, "panel time moves in half seconds");
  assert.deepEqual([DEFAULT_SETTINGS.bgmVolumeDb, DEFAULT_SETTINGS.dialogueGainDb, DEFAULT_SETTINGS.minPanelDuration, DEFAULT_SETTINGS.narrationSpeed], [-10, 0, 4, 1]);
});

test("the start options use the client's names; only the draft profile is a draft; an empty location is left out", () => {
  const standard = startOptions({ ...DEFAULT_SETTINGS, profile: "standard_1080p", subtitles: true, saveLocation: "  " });
  assert.deepEqual(standard, {
    profileName: "standard_1080p", customOutputPath: undefined, subtitleEnabled: true, bgmVolumeDb: -10, dialogueGainDb: 0, isDraft: false,
    minPanelDuration: 4, panelZoomMode: "fit", narrationSpeed: 1, videoEngine: "fast_h3", motionFx: "none",
  });
  assert.equal(startOptions({ ...DEFAULT_SETTINGS, profile: "draft_720p" }).isDraft, true);
  assert.equal(startOptions({ ...DEFAULT_SETTINGS, profile: "x", saveLocation: " D:\\Videos " }).customOutputPath, "D:\\Videos");
  assert.equal(startOptions({ ...DEFAULT_SETTINGS, profile: "" }).profileName, undefined);
});

test("the real report reads as production ready, with the unexplained sync flag explained", () => {
  const s = validationSummary(REAL_REPORT);
  assert.deepEqual(s.verdict, { word: "Ready for production", tone: "ok" });
  const row = (label: string) => s.rows.find((r) => r.label === label)!;
  assert.equal(row("Sync").value, "Not confirmed");
  assert.equal(row("Sync").tone, "warn");
  assert.ok(row("Sync").note!.includes("still passed the render as production ready"));
  assert.equal(row("Black frames").value, "0");
  assert.ok(row("Duration").value.includes("137.87s") && row("Duration").value.includes("0.003s"));
  assert.equal(row("File size").value, "88.0 MiB");
  assert.equal(s.rows.find((r) => r.label === "Video"), undefined, "a field the report lacks is omitted, not shown as a pass");
});

test("a typed-only passing report, an absent report and a failing report", () => {
  const typed = validationSummary({ is_valid: true, video_valid: true, audio_valid: true, sync_valid: true, black_frames_count: 2, timeline_gaps_count: 0, clipping_samples_count: 0, duration_sec: 370, warnings: ["Two black frames"] });
  assert.deepEqual(typed.verdict, { word: "Passed", tone: "ok" });
  assert.equal(typed.rows.find((r) => r.label === "Video")!.value, "Pass");
  assert.equal(typed.rows.find((r) => r.label === "Sync")!.note, undefined);
  assert.deepEqual(typed.warnings, ["Two black frames"]);
  assert.deepEqual(validationSummary(null).verdict, { word: "No checks yet", tone: "neutral" });
  const bad = validationSummary({ is_valid: false, video_valid: true, audio_valid: false, sync_valid: false, black_frames_count: 0, timeline_gaps_count: 0, clipping_samples_count: 0, duration_sec: 10, warnings: [] });
  assert.deepEqual(bad.verdict, { word: "Did not pass", tone: "bad" });
  assert.equal(bad.rows.find((r) => r.label === "Audio")!.value, "Fail");
  assert.equal(bad.rows.find((r) => r.label === "Sync")!.value, "Fail", "a sync failure on a failing render is a failure, not a note");
});

test("bytes and file names", () => {
  assert.equal(formatBytes(92299740), "88.0 MiB");
  assert.equal(formatBytes(2048), "2.0 KiB");
  assert.equal(formatBytes(12), "12 B");
  assert.equal(outputName("C:\\Users\\user\\renders\\a_b.mp4"), "a_b.mp4");
  assert.equal(outputName("/home/u/renders/a_b.mp4"), "a_b.mp4");
  assert.equal(outputName(""), "");
});

test("a report that arrives as a JSON string is read, and unreadable text is treated as no report", () => {
  assert.deepEqual(validationSummary(JSON.stringify(REAL_REPORT)).verdict, { word: "Ready for production", tone: "ok" });
  assert.deepEqual(validationSummary("not json").verdict, { word: "No checks yet", tone: "neutral" });
});
