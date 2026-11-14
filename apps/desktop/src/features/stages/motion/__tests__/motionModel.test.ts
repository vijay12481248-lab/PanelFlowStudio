import test from "node:test";
import assert from "node:assert/strict";
import type { Panel } from "@panelflow/shared-types";
import { addTag, extractShots, formatClock, matchPanel, shotView } from "../motionModel";

const panel = (id: string, sequence: number) => ({ id, sequence }) as Panel;
const DEFAULT_CAM = { center_x: 0.5, center_y: 0.5, zoom: 1 };

test("a shot with the engine's main field names is read as is", () => {
  const view = shotView({
    shot_id: "s7", sceneTitle: "Gate", start_time: 1.5, end_time: 4, duration_sec: 2.5,
    camera_start: { center_x: 0.2, center_y: 0.3, zoom: 1 }, camera_end: { center_x: 0.6, center_y: 0.4, zoom: 1.4 },
    motion_type: "PUSH_IN", easing: "EASE_OUT", caption_cues: [{ speaker: "Aria", text: "Hello" }, { speaker: "x", text: "ignored" }], transition_in: "CUT",
    provenance: { panel_ids: ["pn3"] },
  }, 6);
  assert.equal(view.key, "s7");
  assert.equal(view.index, 6);
  assert.equal(view.title, "Gate");
  assert.deepEqual([view.startSec, view.endSec, view.durationSec], [1.5, 4, 2.5]);
  assert.equal(view.endCamera.zoom, 1.4);
  assert.equal(view.motionType, "PUSH_IN");
  assert.equal(view.easing, "EASE_OUT");
  assert.deepEqual(view.caption, { speaker: "Aria", text: "Hello" });
  assert.equal(view.transition, "CUT");
  assert.equal(view.panelId, "pn3");
});

test("the alternative field names and every missing value fall back the way the old screen did", () => {
  const view = shotView({ start_rect: { center_x: 0.1, center_y: 0.1, zoom: 2 }, end_rect: { center_x: 0.9, center_y: 0.9, zoom: 1 }, camera_motion_type: "PAN", easing_function: "LINEAR", duration: 3 }, 0);
  assert.equal(view.key, "0", "no shot_id: the index is the key");
  assert.equal(view.startCamera.zoom, 2);
  assert.equal(view.motionType, "PAN");
  assert.equal(view.easing, "LINEAR");
  assert.equal(view.durationSec, 3);
  const bare = shotView({}, 2);
  assert.deepEqual(bare.startCamera, DEFAULT_CAM);
  assert.deepEqual(bare.endCamera, DEFAULT_CAM);
  assert.equal(bare.motionType, "CINEMATIC");
  assert.equal(bare.easing, "SMOOTHSTEP");
  assert.equal(bare.durationSec, 0);
  assert.equal(bare.caption, null);
  assert.equal(bare.transition, null);
  assert.equal(bare.title, null);
  assert.equal(bare.panelId, null);
});

test("duration comes from the end and start times when no duration is given, and is never negative", () => {
  assert.equal(shotView({ start_time: 2, end_time: 5 }, 0).durationSec, 3);
  assert.equal(shotView({ start_time: 5, end_time: 2 }, 0).durationSec, 0);
});

test("an object transition shows its type and length", () => {
  assert.equal(shotView({ transition_in: { transition_type: "DISSOLVE", duration_sec: 0.5 } }, 0).transition, "DISSOLVE (0.5s)");
  assert.equal(shotView({ transition_in: { transition_type: "WIPE" } }, 0).transition, "WIPE");
});

test("a caption with no speaker is attributed to Speaker", () => {
  assert.deepEqual(shotView({ caption_cues: [{ text: "Hi" }] }, 0).caption, { speaker: "Speaker", text: "Hi" });
});

test("a shot's panel is found by provenance, by source panel id, by panel number, then by wrapping around", () => {
  const panels = [panel("a", 1), panel("b", 2), panel("c", 3)];
  assert.equal(matchPanel({ provenance: { panel_ids: ["b"] } }, 0, panels)?.id, "b");
  assert.equal(matchPanel({ source_panel_id: "c" }, 0, panels)?.id, "c");
  assert.equal(matchPanel({ panel_id: "a" }, 2, panels)?.id, "a");
  assert.equal(matchPanel({ source_panel_id: "Panel_3" }, 0, panels)?.id, "c");
  assert.equal(matchPanel({}, 4, panels)?.id, "b", "index 4 wraps to the second panel");
  assert.equal(matchPanel({ source_panel_id: "panel_99" }, 1, panels)?.id, "b", "an unknown panel number falls back to wrap-around");
  assert.equal(matchPanel({}, 0, []), undefined);
});

test("clock text rounds to whole seconds and never shows 60", () => {
  assert.equal(formatClock(370), "6:10");
  assert.equal(formatClock(0), "0:00");
  assert.equal(formatClock(59.6), "1:00");
  assert.equal(formatClock(65), "1:05");
});

test("shots are read from scenes, then from the timeline or the response", () => {
  const scenes = { timeline: { scenes: [{ sequence: 1, title: "Gate", shots: [{ shot_id: "a" }, { shot_id: "b" }] }, { sequence: 2, shots: [{ shot_id: "c" }] }] } };
  const fromScenes = extractShots(scenes as any);
  assert.deepEqual(fromScenes.map((s: any) => [s.shot_id, s.sceneTitle]), [["a", "Gate"], ["b", "Gate"], ["c", "Scene 2"]]);
  assert.deepEqual(extractShots({ timeline: { shots: [{ shot_id: "x" }] } } as any).map((s: any) => s.shot_id), ["x"]);
  assert.deepEqual(extractShots({ timeline: [{ shot_id: "y" }] } as any).map((s: any) => s.shot_id), ["y"]);
  assert.deepEqual(extractShots({ shots: [{ shot_id: "z" }], timeline: {} } as any).map((s: any) => s.shot_id), ["z"]);
  assert.deepEqual(extractShots(null), []);
  assert.deepEqual(extractShots({ timeline: {} } as any), []);
});

test("a quick tag is added to the prompt after a comma, without its leading symbol", () => {
  assert.equal(addTag("", "Glowing aura"), "Glowing aura");
  assert.equal(addTag("rain", "Bokeh depth"), "rain, Bokeh depth");
  assert.equal(addTag("rain", "✨ Glowing aura"), "rain, Glowing aura");
});
