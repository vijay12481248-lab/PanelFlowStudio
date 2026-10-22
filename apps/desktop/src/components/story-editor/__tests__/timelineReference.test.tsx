import React from "react";
import assert from "node:assert/strict";
import { test } from "node:test";
import { renderToStaticMarkup } from "react-dom/server";
import { StoryEditorTimeline, getTimelineTrackState, toggleTimelineTrackState } from "../StoryEditorTimeline";
import type { StoryEditorState } from "@panelflow/shared-types";

const state = {
  mode: "simple", scenes: [{ id: "scene-a", sequence: 1, title: "Scene 1 — Opening", start_time_sec: 0, duration_sec: 6,
    layers: [{ id: "layer-a", name: "Page 1 Opening", image_url: "page.jpg", motion_preset: "slow_zoom_in", start_offset_sec: 1, duration_sec: 4,
      transform: { x: 0, y: 0, scale: 1, rotation: 0, opacity: 1, z_index: 1 } }] }],
  narration_clips: [{ id: "voice-a", text: "Opening narration", start_time_sec: 0, duration_sec: 5, status: "READY" }],
  bgm_tracks: [], sfx_cues: [], selected_object: { type: "scene", id: "scene-a" },
  playhead_sec: 0, is_playing: false, zoom_level: 100,
} as unknown as StoryEditorState;
const noop = () => {};
const render = (overrides: Partial<StoryEditorState> = {}) => renderToStaticMarkup(
  <StoryEditorTimeline state={{ ...state, ...overrides }} onUpdateState={noop} onSelectScene={noop}
    onSelectLayer={noop} onAddBlankScene={noop} onSplitScene={noop} onDuplicateScene={noop} onDeleteScene={noop} />
);

test("simple reference timeline has five real, color-coded lanes and no invented SFX", () => {
  const html = render();
  assert.match(html, /pf-editor-timeline/);
  for (const key of ["Narration", "Visuals", "Layer 2", "Motion \/ FX", "Music"]) {
    assert.ok(html.includes(`data-timeline-lane="${key}"`), `missing lane ${key}`);
  }
  assert.match(html, /Page 1 Opening/);
  assert.match(html, /Zoom In/);
  assert.doesNotMatch(html, /data-timeline-lane="SFX"/);
  assert.doesNotMatch(html, /Footsteps|Whoosh|sfx_1/);
});

test("audio presentation distinguishes measured peaks from unmeasured neutral bars", () => {
  const unmeasured = render({ bgm_tracks: [{ id: "music-a", title: "Ambient", volume: 0.6, loop: false, start_time_sec: 0, duration_sec: 20 }] });
  assert.equal((unmeasured.match(/data-waveform="unmeasured"/g) || []).length, 2);
  assert.doesNotMatch(unmeasured, /data-waveform="measured"/);
  const measured = render({ bgm_tracks: [{ id: "music-a", title: "Ambient", volume: 0.6, loop: false, start_time_sec: 0, duration_sec: 20, measured_peaks: [0, 0.25, 1] }] });
  assert.match(measured, /data-waveform="measured"/);
  assert.match(measured, /aria-label="Measured audio waveform"/);
});

test("reference controls are named and track state reaches the actual lanes", () => {
  const html = render({ track_states: { layer2: { visible: false, locked: true }, music: { visible: true, locked: true } },
    bgm_tracks: [{ id: "music-a", title: "Ambient", volume: 0.6, loop: false, start_time_sec: 0, duration_sec: 20 }] });
  assert.ok(/data-timeline-lane="Layer 2"[^>]*data-visible="false"[^>]*data-locked="true"/.test(html), "legacy state must control the Layers lane");
  assert.match(html, /aria-label="Toggle Layers lock" aria-pressed="true"/);
  assert.match(html, /aria-label="Timeline zoom"/);
  assert.doesNotMatch(html, /title="Duplicate BGM Clip"/);
  for (const match of html.matchAll(/<button\b([^>]*)>([\s\S]*?)<\/button>/g)) {
    const visibleText = match[2].replace(/<[^>]*>/g, "").trim();
    assert.ok(visibleText || match[1].includes("aria-label="), `unnamed button: ${match[1]}`);
  }
});

test("advanced details and existing simple-mode SFX remain available", () => {
  const advanced = render({ mode: "advanced" });
  assert.match(advanced, /data-timeline-lane="SFX"/);
  assert.match(advanced, /title="Trim layer start"/);
  const simple = render({ sfx_cues: [{ id: "effect-a", name: "Real effect", category: "magic", start_time_sec: 2, duration_sec: 1, volume: 1 }] });
  assert.match(simple, /data-timeline-lane="SFX"/);
  assert.match(simple, /Real effect/);
  assert.doesNotMatch(simple, /title="Trim layer start"/);
});

test("track toggles preserve persisted keys and keep audio mute keys synchronized", () => {
  const old = { ...state, track_states: { "Layer 2": { visible: true, locked: false }, music: { visible: true, locked: true } } };
  const layer = toggleTimelineTrackState(old, "Layer 2", "locked");
  assert.equal(layer.track_states?.["Layer 2"].locked, true);
  assert.equal(layer.track_states?.["Layers"], undefined);
  assert.equal(old.track_states["Layer 2"].locked, false);
  const muted = toggleTimelineTrackState(old, "Music", "visible");
  assert.deepEqual(muted.track_states?.Music, { visible: false, locked: true });
  assert.deepEqual(muted.track_states?.music, muted.track_states?.Music);
  assert.equal(muted.scenes, old.scenes);
});

test("canonical persisted Layer 2 and legacy aliases resolve without losing locks", () => {
  const locked = { visible: false, locked: true };
  assert.equal(getTimelineTrackState({ "Layer 2": locked }, "Layer 2"), locked);
  assert.equal(getTimelineTrackState({ layer2: locked }, "Layer 2"), locked);
  assert.equal(getTimelineTrackState({ music: locked }, "Music"), locked);
  assert.equal(getTimelineTrackState({ motion: locked }, "Motion / FX"), locked);
  assert.deepEqual(getTimelineTrackState(undefined, "Narration"), { visible: true, locked: false });
});
