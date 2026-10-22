import React, { act, useCallback, useState } from "react";
import assert from "node:assert/strict";
import test from "node:test";
import { createRequire } from "node:module";
import type { StoryEditorState } from "@panelflow/shared-types";
import { StoryEditorTimeline } from "../StoryEditorTimeline";
import { VideoCompositionCanvas } from "../VideoCompositionCanvas";

const require = createRequire(import.meta.url);
const { JSDOM } = require("jsdom");

function fixture(): StoryEditorState {
  const layer = (id: string, start: number, duration: number) => ({ id, name: id, image_url: "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7", start_offset_sec: start, duration_sec: duration,
    transform: { x: 0, y: 0, scale: 1, rotation: 0, opacity: 1, z_index: 1 } });
  return {
    mode: "advanced", zoom_level: 100, playhead_sec: 0, is_playing: false, snapping: false, ripple_edit: true,
    scenes: [
      { id: "a", title: "Scene A", sequence: 1, start_time_sec: 0, duration_sec: 6, layers: [layer("layer-a", 1, 4)] },
      { id: "b", title: "Scene B", sequence: 2, start_time_sec: 6, duration_sec: 4, layers: [layer("layer-b", 0, 4)] },
      { id: "c", title: "Scene C", sequence: 3, start_time_sec: 10, duration_sec: 3, layers: [] },
    ],
    narration_clips: [
      { id: "linked", text: "Linked voice", scene_id: "b", linked_to_scene: true, scene_offset_sec: 0.5, start_time_sec: 6.5, duration_sec: 1, status: "READY" },
      { id: "free", text: "Free voice", scene_id: "b", linked_to_scene: false, start_time_sec: 9, duration_sec: 1, status: "READY" },
    ],
    bgm_tracks: [{ id: "music", title: "QA music", start_time_sec: 2, duration_sec: 3, volume: 0.5, loop: false }],
    sfx_cues: [{ id: "sfx", name: "QA effect", category: "magic", start_time_sec: 3, duration_sec: 1, volume: 1 }],
  } as StoryEditorState;
}

async function mountTimeline(initial: StoryEditorState = fixture(), manualClock = false) {
  const dom = new JSDOM("<!doctype html><div id='root'></div>", { url: "http://localhost/", pretendToBeVisual: true });
  const globals = ["window", "document", "navigator", "HTMLElement", "requestAnimationFrame", "cancelAnimationFrame", "IS_REACT_ACT_ENVIRONMENT"];
  const previous = new Map(globals.map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  for (const key of globals) Object.defineProperty(globalThis, key, { configurable: true, writable: true,
    value: key === "IS_REACT_ACT_ENVIRONMENT" ? true : key.endsWith("AnimationFrame") ? dom.window[key].bind(dom.window) : dom.window[key] });
  const frames = new Map<number, FrameRequestCallback>();
  let frameId = 0;
  let clockTime = performance.now();
  if (manualClock) {
    globalThis.requestAnimationFrame = callback => { frames.set(++frameId, callback); return frameId; };
    globalThis.cancelAnimationFrame = id => { frames.delete(id); };
  }
  let current = initial;
  let updates = 0;
  function Harness() {
    const [state, setState] = useState(initial);
    current = state;
    const update = useCallback((updater: (prev: StoryEditorState) => StoryEditorState) => { updates++; setState(updater); }, []);
    return <><VideoCompositionCanvas state={state} onUpdateState={update} onSelectLayer={() => {}} /><StoryEditorTimeline state={state} onUpdateState={update}
      onSelectScene={id => update(s => ({ ...s, selected_object: { type: "scene", id } }))}
      onSelectLayer={(id, sceneId) => update(s => ({ ...s, selected_object: { type: "layer", id, sceneId } }))}
      onAddBlankScene={() => {}} onSplitScene={() => {}} onDuplicateScene={() => {}} onDeleteScene={() => {}} /></>;
  }
  const { createRoot } = await import("react-dom/client");
  const container = dom.window.document.getElementById("root")!;
  const root = createRoot(container);
  await act(async () => root.render(<Harness />));
  const find = (selector: string, within: ParentNode = container): HTMLElement => {
    const element = within.querySelector(selector);
    assert.ok(element, `Expected timeline element: ${selector}`);
    return element as HTMLElement;
  };
  const lane = (name: string) => find(`[data-timeline-lane="${name}"]`);
  const mouse = async (target: EventTarget, type: string, x: number, button = 0) => {
    await act(async () => { target.dispatchEvent(new dom.window.MouseEvent(type, { bubbles: true, cancelable: true, clientX: x, button, buttons: type === "mouseup" ? 0 : 1 })); });
  };
  const drag = async (target: HTMLElement, delta: number, button = 0) => {
    // Native bubbling DOM events, with a React render/effect flush between each.
    await mouse(target, "mousedown", 200, button);
    await mouse(dom.window, "mousemove", 200 + delta);
    await mouse(dom.window, "mouseup", 200 + delta);
  };
  const transfer = () => {
    const data = new Map<string, string>();
    return { setData: (key: string, value: string) => data.set(key, value), getData: (key: string) => data.get(key) || "", get types() { return [...data.keys()]; }, effectAllowed: "all", dropEffect: "none" };
  };
  const dnd = async (target: HTMLElement, type: string, dataTransfer: ReturnType<typeof transfer>) => {
    const event = new dom.window.Event(type, { bubbles: true, cancelable: true });
    Object.defineProperty(event, "dataTransfer", { value: dataTransfer });
    await act(async () => { target.dispatchEvent(event); });
    return event;
  };
  return { container, find, lane, drag, mouse, transfer, dnd, state: () => current, updates: () => updates,
    async tick(seconds: number) {
      clockTime = Math.max(clockTime, performance.now()) + seconds * 1000;
      const callbacks = [...frames.values()]; frames.clear();
      await act(async () => callbacks.forEach(callback => callback(clockTime)));
    },
    async close() {
      await act(async () => root.unmount());
      dom.window.close();
      for (const [key, descriptor] of previous) {
        if (descriptor) Object.defineProperty(globalThis, key, descriptor);
        else delete (globalThis as any)[key];
      }
    },
  };
}

for (const edge of ["left", "right"] as const) {
  test(`Ripple OFF ${edge} 6→4 trim preserves later start 6 and preview gap`, async () => {
    const initial = fixture(); initial.ripple_edit = false; initial.playhead_sec = 5;
    const ui = await mountTimeline(initial);
    try {
      await ui.drag(ui.find(`[title="Drag to trim ${edge} boundary"]`), edge === "right" ? -80 : 80);
      assert.deepEqual(ui.state().scenes.map(s => [s.duration_sec, s.start_time_sec]), [[4, 0], [4, 6], [3, 10]]);
      assert.deepEqual(ui.state().narration_clips.map(n => n.start_time_sec), [6.5, 9]);
      assert.equal(ui.find('[title="Scene B"]').style.left, "240px");
      assert.equal((ui.lane("Layer 2").children[1] as HTMLElement).style.left, "240px");
      assert.equal((ui.lane("Layer 2").children[0] as HTMLElement).style.width, "120px", "layer's visible interval is clipped to its shortened parent without destroying stored timing");
      assert.equal(ui.state().scenes[0].layers[0].duration_sec, 4);
      assert.equal(ui.container.querySelector('img[alt="layer-b"]'), null, "no scene is visible during the 4–6 gap");
      assert.doesNotMatch(ui.container.textContent!, /Scene #1: Scene A/);
      await ui.drag(ui.find('[title^="Double-click to open Narration"]'), 40);
      assert.deepEqual([ui.state().narration_clips[0].start_time_sec, ui.state().narration_clips[0].scene_offset_sec], [7.5, 1.5]);
      await ui.drag(ui.find('[title="Drag to trim right boundary"]'), 800);
      assert.equal(ui.state().scenes[0].duration_sec, 6, "expansion stops at the next fixed scene, not an overlap");
      assert.equal(ui.state().scenes[1].start_time_sec, 6);
      assert.match(ui.container.textContent!, /00:13/, "timecode total includes the retained two-second gap");
    } finally { await ui.close(); }
  });
}

test("preview playback clock includes gaps rather than stopping at summed durations", async () => {
  const initial = fixture(); initial.ripple_edit = false; initial.playhead_sec = 12; initial.is_playing = true;
  const ui = await mountTimeline(initial, true);
  try {
    await ui.drag(ui.find('[title="Drag to trim right boundary"]'), -80);
    await ui.tick(0.2);
    assert.equal(ui.state().is_playing, true);
    assert.ok(ui.state().playhead_sec > 12 && ui.state().playhead_sec < 13);
    await ui.tick(1);
    assert.equal(ui.state().is_playing, false);
    assert.equal(ui.state().playhead_sec, 0);
  } finally { await ui.close(); }
});

for (const legacy of [false, true]) {
  test(`preview selects fixed later scene at its half-open start (legacy missing starts: ${legacy})`, async () => {
    const initial = fixture(); initial.ripple_edit = false; initial.playhead_sec = 6;
    if (legacy) initial.scenes.forEach(scene => { delete (scene as Partial<typeof scene>).start_time_sec; });
    const ui = await mountTimeline(initial);
    try {
      await ui.drag(ui.find('[title="Drag to trim right boundary"]'), -80);
      assert.ok(ui.container.querySelector('img[alt="layer-b"]'));
      assert.match(ui.container.textContent!, /Scene #2: Scene B/);
      assert.equal(ui.find('[title="Scene B"]').style.left, "240px");
      assert.deepEqual(ui.state().scenes.map(scene => scene.start_time_sec), [0, 6, 10]);
    } finally { await ui.close(); }
  });
}

test("Ripple OFF audio snapping uses fixed scene starts after a gap", async () => {
  const initial = fixture(); initial.ripple_edit = false; initial.snapping = true;
  const ui = await mountTimeline(initial);
  try {
    await ui.drag(ui.find('[title="Drag to trim right boundary"]'), -80);
    await ui.drag(ui.find('[title^="BGM:"]'), 156);
    assert.equal(ui.state().bgm_tracks[0].start_time_sec, 6);
  } finally { await ui.close(); }
});

for (const edge of ["left", "right"] as const) {
  test(`scene ${edge} trim ripples subsequent scenes and only linked narration; mouseup ends gesture`, async () => {
    const ui = await mountTimeline();
    try {
      await ui.drag(ui.find(`[title="Drag to trim ${edge} boundary"]`), edge === "right" ? 80 : -80);
      assert.deepEqual(ui.state().scenes.map(s => [s.duration_sec, s.start_time_sec, s.sequence]), [[8, 0, 1], [4, 8, 2], [3, 12, 3]]);
      assert.deepEqual(ui.state().narration_clips.map(n => n.start_time_sec), [8.5, 9]);
      assert.equal(ui.find('[title="Scene B"]').style.left, "320px");
      const snapshot = ui.state();
      await ui.mouse(window, "mousemove", 800);
      assert.equal(ui.state(), snapshot, "no updates after mouseup");
    } finally { await ui.close(); }
  });
}

for (const edge of ["left", "right"]) {
  test(`scene ${edge} trim clamps to its positive minimum and keeps ripple starts aligned`, async () => {
    const ui = await mountTimeline();
    try {
      await ui.drag(ui.find(`[title="Drag to trim ${edge} boundary"]`), edge === "left" ? 1000 : -1000);
      assert.deepEqual(ui.state().scenes.map(s => [s.duration_sec, s.start_time_sec]), [[0.8, 0], [4, 0.8], [3, 4.8]]);
      assert.equal(ui.state().narration_clips[0].start_time_sec, 1.3);
    } finally { await ui.close(); }
  });
}

for (const zoom of [50, 250]) {
  test(`mouse gestures honor the ${zoom}% timeline zoom scale`, async () => {
    const initial = fixture(); initial.zoom_level = zoom;
    const ui = await mountTimeline(initial);
    try {
      await ui.drag(ui.find('[title="Drag to trim right boundary"]'), 80);
      const seconds = 80 / (40 * zoom / 100);
      assert.equal(ui.state().scenes[0].duration_sec, 6 + seconds);
      await ui.drag(ui.find('[title^="BGM:"]'), 80);
      assert.equal(ui.state().bgm_tracks[0].start_time_sec, 2 + seconds);
    } finally { await ui.close(); }
  });
}

test("unlinked narration moves independently even when it retains an old scene reference", async () => {
  const ui = await mountTimeline();
  try {
    const clips = ui.lane("Narration").children;
    await ui.drag(clips[1] as HTMLElement, -1000);
    assert.equal(ui.state().narration_clips[1].start_time_sec, 0);
    assert.equal(ui.state().narration_clips[1].linked_to_scene, false);
    assert.equal(ui.state().narration_clips[0].start_time_sec, 6.5);
  } finally { await ui.close(); }
});

test("Ripple OFF native reorder moves only the dragged scene into a free gap", async () => {
  const initial = fixture(); initial.ripple_edit = false;
  initial.scenes[0].duration_sec = 4; initial.scenes[1].start_time_sec = 8; initial.scenes[2].start_time_sec = 12;
  initial.narration_clips[0].start_time_sec = 8.5;
  const ui = await mountTimeline(initial);
  try {
    const data = ui.transfer();
    await ui.dnd(ui.find('[title="Scene C"]'), "dragstart", data);
    await ui.dnd(ui.lane("Visuals").children[2] as HTMLElement, "drop", data);
    assert.deepEqual(ui.state().scenes.map(scene => [scene.id, scene.start_time_sec]), [["a", 0], ["c", 4], ["b", 8]]);
    assert.equal(ui.state().narration_clips[0].start_time_sec, 8.5);
  } finally { await ui.close(); }
});

test("Ripple OFF occupied reorder destination appends rather than shifting fixed scenes", async () => {
  const initial = fixture(); initial.ripple_edit = false;
  const ui = await mountTimeline(initial);
  try {
    const data = ui.transfer();
    await ui.dnd(ui.find('[title="Scene A"]'), "dragstart", data);
    await ui.dnd(ui.lane("Visuals").children[4] as HTMLElement, "drop", data);
    assert.deepEqual(ui.state().scenes.map(scene => [scene.id, scene.start_time_sec]), [["b", 6], ["c", 10], ["a", 13]]);
    assert.equal(ui.state().narration_clips[0].start_time_sec, 6.5);
  } finally { await ui.close(); }
});

test("native scene drag/drop before another scene reorders, renumbers, and aligns linked narration", async () => {
  const ui = await mountTimeline();
  try {
    const data = ui.transfer();
    await ui.dnd(ui.find('[title="Scene C"]'), "dragstart", data);
    const target = ui.lane("Visuals").children[0] as HTMLElement;
    await ui.dnd(target, "dragover", data);
    assert.equal(data.effectAllowed, "move");
    assert.equal(data.dropEffect, "move", "the browser rejects copy on a move-only scene drag");
    await ui.dnd(target, "drop", data);
    assert.deepEqual(ui.state().scenes.map(s => [s.id, s.start_time_sec, s.sequence]), [["c", 0, 1], ["a", 3, 2], ["b", 9, 3]]);
    assert.deepEqual(ui.state().narration_clips.map(n => n.start_time_sec), [9.5, 9]);
  } finally { await ui.close(); }
});

test("native scene drag/drop after the last scene moves it to the end", async () => {
  const ui = await mountTimeline();
  try {
    const data = ui.transfer();
    await ui.dnd(ui.find('[title="Scene A"]'), "dragstart", data);
    await ui.dnd(ui.lane("Visuals").lastElementChild as HTMLElement, "dragover", data);
    await ui.dnd(ui.lane("Visuals").lastElementChild as HTMLElement, "drop", data);
    assert.deepEqual(ui.state().scenes.map(s => [s.id, s.start_time_sec]), [["b", 0], ["c", 4], ["a", 7]]);
    assert.deepEqual(ui.state().narration_clips.map(n => n.start_time_sec), [0.5, 9]);
  } finally { await ui.close(); }
});

for (const edge of ["start", "duration"]) {
  test(`layer ${edge} trim respects its parent and positive minimum duration`, async () => {
    const ui = await mountTimeline();
    try {
      await ui.drag(ui.find(`[title="Trim layer ${edge}"]`), 1000);
      const ly = ui.state().scenes[0].layers[0];
      assert.deepEqual([ly.start_offset_sec, ly.duration_sec], edge === "start" ? [4.6, 0.4] : [1, 5]);
      assert.ok(ly.start_offset_sec! + ly.duration_sec! <= 6);
      await ui.drag(ui.find(`[title="Trim layer ${edge}"]`), -1000);
      const bounded = ui.state().scenes[0].layers[0];
      assert.deepEqual([bounded.start_offset_sec, bounded.duration_sec], edge === "start" ? [0, 5] : [1, 0.4]);
    } finally { await ui.close(); }
  });
}

test("native layer drag/drop moves the existing layer to its destination scene and fits its bounds", async () => {
  const ui = await mountTimeline();
  try {
    const data = ui.transfer();
    await ui.dnd(ui.lane("Layer 2").firstElementChild as HTMLElement, "dragstart", data);
    await ui.dnd(ui.find('[title="Scene C"]'), "dragover", data);
    assert.equal(data.dropEffect, "move", "the browser rejects copy on a move-only layer drag");
    await ui.dnd(ui.find('[title="Scene C"]'), "drop", data);
    assert.equal(ui.state().scenes[0].layers.length, 0);
    const ly = ui.state().scenes[2].layers[0];
    assert.deepEqual([ly.id, ly.start_offset_sec, ly.duration_sec], ["layer-a", 0, 3]);
    assert.deepEqual(ui.state().selected_object, { type: "layer", id: "layer-a", sceneId: "c" });
  } finally { await ui.close(); }
});

test("a locked individual layer cannot be trimmed", async () => {
  const state = fixture(); state.scenes[0].layers[0].locked = true;
  const ui = await mountTimeline(state);
  try {
    await ui.drag(ui.find('[title="Trim layer duration"]'), -80);
    assert.equal(ui.state().scenes[0].layers[0].duration_sec, 4);
    assert.equal(ui.updates(), 0, "a locked layer must not even start an edit");
  } finally { await ui.close(); }
});

for (const [name, selector, collection, minimum] of [
  ["Music", '[title^="BGM:"]', "bgm_tracks", 0.5],
  ["SFX", '[title^="SFX:"]', "sfx_cues", 0.3],
] as const) {
  test(`${name} moves from its body, clamps at zero, and respects both trim bounds`, async () => {
    const ui = await mountTimeline();
    try {
      const clip = () => ui.find(selector);
      await ui.drag(clip(), 80);
      assert.equal(ui.state()[collection]![0].start_time_sec, name === "Music" ? 4 : 5);
      await ui.drag(clip(), -1000);
      assert.equal(ui.state()[collection]![0].start_time_sec, 0);
      const end = ui.state()[collection]![0].duration_sec;
      await ui.drag(ui.find('[title="Drag to trim start"]', clip()), 1000);
      assert.equal(ui.state()[collection]![0].duration_sec, minimum);
      assert.equal(ui.state()[collection]![0].start_time_sec, end - minimum);
      await ui.drag(ui.find('[title="Drag to trim duration"]', clip()), 80);
      assert.equal(ui.state()[collection]![0].duration_sec, minimum + 2);
      await ui.drag(ui.find('[title="Drag to trim duration"]', clip()), -1000);
      assert.equal(ui.state()[collection]![0].duration_sec, minimum);
      const absoluteEnd = ui.state()[collection]![0].start_time_sec + minimum;
      await ui.drag(ui.find('[title="Drag to trim start"]', clip()), -1000);
      assert.equal(ui.state()[collection]![0].start_time_sec, 0);
      assert.equal(ui.state()[collection]![0].duration_sec, absoluteEnd, "left trim preserves the absolute end when clamped to zero");
    } finally { await ui.close(); }
  });
}

for (const name of ["Music", "SFX"] as const) {
  test(`${name} body drag snaps to scene boundaries and the playhead when enabled`, async () => {
    const state = fixture(); state.snapping = true; state.playhead_sec = 4.5;
    const ui = await mountTimeline(state);
    try {
      const selector = name === "Music" ? '[title^="BGM:"]' : '[title^="SFX:"]';
      const read = () => name === "Music" ? ui.state().bgm_tracks[0] : ui.state().sfx_cues![0];
      await ui.drag(ui.find(selector), (5.9 - read().start_time_sec) * 40);
      assert.equal(read().start_time_sec, 6);
      await ui.drag(ui.find(selector), -56);
      assert.equal(read().start_time_sec, 4.5);
    } finally { await ui.close(); }
  });
}

for (const mode of ["locked", "hidden"] as const) {
  for (const [lane, selector] of [["Visuals", '[title="Scene A"]'], ["Layer 2", '[title="Trim layer duration"]'], ["Narration", '[title^="Double-click to open Narration"]'], ["Music", '[title^="BGM:"]'], ["SFX", '[title^="SFX:"]']] as const) {
    test(`${mode} ${lane} track blocks actual mouse edits and native drops`, async () => {
      const state = fixture(); state.track_states = { [lane]: { visible: mode !== "hidden", locked: mode === "locked" } };
      const ui = await mountTimeline(state);
      try {
        const before = ui.state();
        await ui.drag(ui.find(selector), 80);
        const data = ui.transfer();
        if (lane === "Music" || lane === "SFX") {
          data.setData("application/panelflow-audio-contract", JSON.stringify({ reference: { asset_id: "qa-asset", name: "QA drop", target_track: lane === "Music" ? "BGM" : "SFX", duration_sec: 2 } }));
        } else {
          data.setData("application/panelflow-panel", JSON.stringify({ panelId: "qa-panel", pageId: "qa-page", imageUrl: "qa.jpg" }));
        }
        await ui.dnd(ui.find(selector), "drop", data);
        assert.equal(ui.state(), before);
        assert.equal(ui.updates(), 0);
      } finally { await ui.close(); }
    });
  }
}

for (const [name, selector] of [["scene", '[title="Drag to trim right boundary"]'], ["layer", '[title="Trim layer duration"]']] as const) {
  test(`${name} trimming cancels native HTML drag rather than losing the mouse gesture`, async () => {
    const ui = await mountTimeline();
    try {
      const handle = ui.find(selector);
      const down = new window.MouseEvent("mousedown", { bubbles: true, cancelable: true, clientX: 200, button: 0 });
      await act(async () => { handle.dispatchEvent(down); });
      assert.equal(down.defaultPrevented, true, "trim handles must suppress the browser's native drag default");
      const start = await ui.dnd(handle.parentElement!, "dragstart", ui.transfer());
      assert.equal(start.defaultPrevented, true, "a trim is not an HTML reorder/move");
      await ui.mouse(window, "mousemove", 160);
      await ui.mouse(window, "mouseup", 160);
      assert.equal(name === "scene" ? ui.state().scenes[0].duration_sec : ui.state().scenes[0].layers[0].duration_sec, name === "scene" ? 5 : 3);
    } finally { await ui.close(); }
  });
}

for (const [name, selector] of [["scene", '[title="Drag to trim right boundary"]'], ["layer", '[title="Trim layer duration"]'], ["narration", '[title^="Double-click to open Narration"]'], ["music", '[title^="BGM:"]'], ["sfx", '[title^="SFX:"]']] as const) {
  test(`secondary mouse button does not edit ${name}`, async () => {
    const ui = await mountTimeline();
    try {
      const before = ui.state();
      await ui.drag(ui.find(selector), 80, 2);
      assert.equal(ui.state(), before);
    } finally { await ui.close(); }
  });
}

test("linked narration drag retains its parent-relative offset and cannot move before its parent", async () => {
  const ui = await mountTimeline();
  try {
    const clip = () => ui.find('[title^="Double-click to open Narration"]');
    await ui.drag(clip(), 40);
    assert.deepEqual([ui.state().narration_clips[0].start_time_sec, ui.state().narration_clips[0].scene_offset_sec], [7.5, 1.5]);
    await ui.drag(clip(), -1000);
    assert.deepEqual([ui.state().narration_clips[0].start_time_sec, ui.state().narration_clips[0].scene_offset_sec], [6, 0]);
  } finally { await ui.close(); }
});
