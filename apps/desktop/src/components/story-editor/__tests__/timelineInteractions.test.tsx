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
  const dnd = async (target: HTMLElement, type: string, dataTransfer: ReturnType<typeof transfer>, clientX = 0, altKey = false) => {
    const event = new dom.window.Event(type, { bubbles: true, cancelable: true });
    Object.defineProperty(event, "dataTransfer", { value: dataTransfer });
    Object.defineProperty(event, "clientX", { value: clientX });
    Object.defineProperty(event, "altKey", { value: altKey });
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

test("native scene drag/drop directly onto another scene swaps their timeline positions", async () => {
  const ui = await mountTimeline();
  try {
    const data = ui.transfer();
    // Drag Scene A (index 0) onto Scene B (index 1)
    await ui.dnd(ui.find('[title="Scene A"]'), "dragstart", data);
    await ui.dnd(ui.find('[title="Scene B"]'), "dragover", data);
    await ui.dnd(ui.find('[title="Scene B"]'), "drop", data);
    assert.deepEqual(ui.state().scenes.map(s => [s.id, s.start_time_sec, s.sequence]), [["b", 0, 1], ["a", 4, 2], ["c", 10, 3]]);
    // Linked narration originally on Scene B shifts with Scene B
    assert.equal(ui.state().narration_clips[0].start_time_sec, 0.5);
  } finally { await ui.close(); }
});

test("dropping a source panel onto a scene inserts exactly once without replacing existing artwork", async () => {
  const ui = await mountTimeline();
  try {
    const data = ui.transfer();
    data.setData("application/panelflow-panel", JSON.stringify({
      panelId: "replacement-panel-1",
      pageId: "page-2",
      pageSequence: 5,
      imageUrl: "https://example.com/new-panel.png",
      name: "New Hero Panel",
      crop: { x: 10, y: 10, width: 100, height: 100 }
    }));
    await ui.dnd(ui.find('[title="Scene A"]'), "drop", data);
    assert.equal(ui.state().scenes.length, 4);
    assert.equal(ui.state().scenes[0].layers[0].source_panel_id, "replacement-panel-1");
    assert.equal(ui.state().scenes.find(s => s.id === "a")!.layers[0].id, "layer-a");
    assert.equal(ui.updates(), 1, "one drop is one undoable state change");
  } finally { await ui.close(); }
});

test("Alt-dropping a panel onto an existing layer chip replaces only that layer's visual", async () => {
  const ui = await mountTimeline();
  try {
    const data = ui.transfer();
    data.setData("application/panelflow-panel", JSON.stringify({
      panelId: "replaced-layer-panel",
      pageId: "page-3",
      imageUrl: "https://example.com/layer-replace.png",
      name: "Replacement Layer Visual"
    }));
    // Drop directly onto the layer chip of Scene A
    const layerChip = ui.lane("Layer 2").firstElementChild as HTMLElement;
    await ui.dnd(layerChip, "drop", data, 0, true);
    const ly = ui.state().scenes[0].layers[0];
    assert.equal(ly.source_panel_id, "replaced-layer-panel");
    assert.equal(ly.name, "Replacement Layer Visual");
    assert.equal(ui.state().scenes.length, 3, "layer replacement does not also append scenes");
    assert.equal(ui.updates(), 1);
  } finally { await ui.close(); }
});

test("dropping a layer onto another layer swaps the two layers between scenes", async () => {
  const ui = await mountTimeline();
  try {
    const data = ui.transfer();
    // Drag layer-a from Scene A and drop onto layer-b in Scene B
    const layerAChip = ui.lane("Layer 2").children[0] as HTMLElement;
    const layerBChip = ui.lane("Layer 2").children[1] as HTMLElement;
    await ui.dnd(layerAChip, "dragstart", data);
    await ui.dnd(layerBChip, "drop", data);
    // In Scene A, layer should now be layer-b
    assert.equal(ui.state().scenes[0].layers[0].id, "layer-b");
    // In Scene B, layer should now be layer-a
    assert.equal(ui.state().scenes[1].layers[0].id, "layer-a");
  } finally { await ui.close(); }
});

test("native narration drag/drop directly onto another narration clip swaps their positions", async () => {
  const ui = await mountTimeline();
  try {
    const data = ui.transfer();
    const narrClips = ui.lane("Narration").children;
    // Drag narration clip 0 onto narration clip 1
    await ui.dnd(narrClips[0] as HTMLElement, "dragstart", data);
    await ui.dnd(narrClips[1] as HTMLElement, "dragover", data);
    assert.equal(data.dropEffect, "move");
    await ui.dnd(narrClips[1] as HTMLElement, "drop", data);
    // Timing swapped: clip "linked" should now be at 9s, and clip "free" at 6.5s
    const linkedNarr = ui.state().narration_clips.find(n => n.id === "linked")!;
    const freeNarr = ui.state().narration_clips.find(n => n.id === "free")!;
    assert.equal(linkedNarr.start_time_sec, 9);
    assert.equal(freeNarr.start_time_sec, 6.5);
  } finally { await ui.close(); }
});

test("dropping narration clip onto a scene attaches and aligns narration to that scene", async () => {
  const ui = await mountTimeline();
  try {
    const data = ui.transfer();
    data.setData("application/panelflow-narration-reorder", JSON.stringify({ narrationId: "free" }));
    // Drop free narration onto Scene A (starts at 0s)
    await ui.dnd(ui.find('[title="Scene A"]'), "drop", data);
    const freeNarr = ui.state().narration_clips.find(n => n.id === "free")!;
    assert.equal(freeNarr.scene_id, "a");
    assert.equal(freeNarr.start_time_sec, 0);
    assert.equal(freeNarr.linked_to_scene, true);
    assert.equal(freeNarr.scene_offset_sec, 0);
  } finally { await ui.close(); }
});

test("motion effect badge drag and drop transfers motion preset to target scene", async () => {
  const initial = fixture();
  initial.scenes[0].layers[0].motion_preset = "pan_right";
  initial.scenes[1].layers[0].motion_preset = "none";
  const ui = await mountTimeline(initial);
  try {
    const data = ui.transfer();
    // Drag motion badge from Scene A
    const motionBadge = ui.lane("Motion / FX").querySelector('[title^="Click to configure in Inspector; Drag"]') as HTMLElement;
    assert.ok(motionBadge, "Motion badge should exist in Track 4");
    await ui.dnd(motionBadge, "dragstart", data);
    // Drop onto Scene B's motion slot in Track 4
    const sceneBMotionSlot = ui.lane("Motion / FX").children[1] as HTMLElement;
    await ui.dnd(sceneBMotionSlot, "drop", data);
    // Scene B should now have pan_right motion
    assert.equal(ui.state().scenes[1].layers[0].motion_preset, "pan_right");
  } finally { await ui.close(); }
});

for (const [x, index] of [[0, 0], [160, 1], [300, 1], [380, 2], [900, 3]]) {
  test(`source batch inserts once at pointer ${x} (index ${index})`, async () => {
    const ui = await mountTimeline();
    try {
      const panels = ["p1", "p2"].map(panelId => ({ panelId, pageId: "page", imageUrl: `${panelId}.png` }));
      const data = ui.transfer();
      data.setData("application/panelflow-panel", JSON.stringify({ ...panels[0], panels: [...panels, panels[0]] }));
      await ui.dnd(ui.lane("Visuals"), "dragover", data, x);
      assert.ok(ui.container.querySelector('[aria-label="Panel insertion position"]'));
      await ui.dnd(ui.lane("Visuals"), "drop", data, x);
      assert.equal(ui.updates(), 1);
      assert.equal(ui.state().scenes.length, 5);
      assert.deepEqual(ui.state().scenes.slice(index, index + 2).map(s => s.layers[0].source_panel_id), ["p1", "p2"]);
      assert.deepEqual(ui.state().scenes.map(s => s.sequence), [1, 2, 3, 4, 5]);
      assert.equal(ui.container.querySelector('[aria-label="Panel insertion position"]'), null);
      // A repeated source drop waits for explicit duplicate confirmation.
      const ids = ui.state().scenes.slice(index, index + 2).map(s => s.id);
      await ui.dnd(ui.lane("Visuals"), "drop", data, 900);
      assert.equal(ui.state().scenes.length, 5);
      assert.equal(ui.updates(), 1);
      assert.ok(ui.find('[aria-label="Add duplicate panels?"]'));
      await ui.mouse(ui.find('[data-confirm-duplicate-panels]'), "click", 0);
      assert.equal(ui.state().scenes.length, 7);
      assert.deepEqual(ui.state().scenes.slice(-2).map(s => s.layers[0].source_panel_id), ["p1", "p2"]);
      assert.ok(ui.state().scenes.slice(-2).every(s => !ids.includes(s.id)));
      assert.equal(ui.updates(), 2);
    } finally { await ui.close(); }
  });
}

test("source insertion honors requested boundary even with Ripple OFF and keeps linked narration aligned", async () => {
  const initial = fixture(); initial.ripple_edit = false;
  const ui = await mountTimeline(initial);
  try {
    const data = ui.transfer();
    data.setData("application/panelflow-panel", JSON.stringify({ panelId: "new", imageUrl: "new.png" }));
    await ui.dnd(ui.lane("Visuals"), "drop", data, 160);
    assert.deepEqual(ui.state().scenes.map(s => s.start_time_sec), [0, 6, 10, 14]);
    assert.equal(ui.state().narration_clips[0].start_time_sec, 10.5);
    assert.equal(ui.state().narration_clips[1].start_time_sec, 9);
  } finally { await ui.close(); }
});

test("empty timeline accepts one batch as a single update", async () => {
  const initial = fixture(); initial.scenes = []; initial.narration_clips = [];
  const ui = await mountTimeline(initial);
  try {
    const data = ui.transfer();
    data.setData("application/panelflow-panel", JSON.stringify({ panels: [{ panelId: "a", imageUrl: "a.png" }, { panelId: "b", imageUrl: "b.png" }] }));
    await ui.dnd(ui.lane("Visuals"), "drop", data, 0);
    assert.deepEqual(ui.state().scenes.map(s => s.layers[0].source_panel_id), ["a", "b"]);
    assert.equal(ui.updates(), 1);
  } finally { await ui.close(); }
});

test("insertion uses scrolled ruler coordinates at the current zoom", async () => {
  const initial = fixture(); initial.zoom_level = 200;
  const ui = await mountTimeline(initial);
  try {
    const ruler = ui.lane("Visuals").parentElement!;
    ruler.getBoundingClientRect = () => ({ left: -400, top: 0, width: 2400, height: 300, right: 2000, bottom: 300, x: -400, y: 0, toJSON() {} });
    const data = ui.transfer();
    data.setData("application/panelflow-panel", JSON.stringify({ panelId: "scrolled", imageUrl: "scroll.png" }));
    await ui.dnd(ui.lane("Visuals"), "drop", data, 200); // (200 + 400) / 80 = 7.5 seconds
    assert.equal(ui.state().scenes[1].layers[0].source_panel_id, "scrolled");
    assert.equal(ui.state().scenes.length, 4);
  } finally { await ui.close(); }
});

test("cancelling an existing panel drop preserves the entire timeline", async () => {
  const initial = fixture(); initial.scenes[1].layers[0].source_panel_id = "existing";
  initial.scenes[1].layers[0].motion_preset = "pan_right";
  const ui = await mountTimeline(initial);
  try {
    const data = ui.transfer();
    data.setData("application/panelflow-panel", JSON.stringify({ panelId: "existing", imageUrl: "existing.png" }));
    await ui.dnd(ui.lane("Visuals"), "drop", data, 0);
    assert.equal(ui.state().scenes.length, 3);
    assert.ok(ui.find('[aria-label="Add duplicate panels?"]'));
    assert.equal(ui.updates(), 0);
    await ui.mouse(ui.find('[data-cancel-duplicate-panels]'), "click", 0);
    assert.equal(ui.state(), initial);
    assert.equal(ui.container.querySelector('[aria-label="Add duplicate panels?"]'), null);
  } finally { await ui.close(); }
});

test("cancelling a source drag clears the insertion marker", async () => {
  const ui = await mountTimeline();
  try {
    const data = ui.transfer();
    data.setData("application/panelflow-panel", JSON.stringify({ panelId: "cancelled" }));
    await ui.dnd(ui.lane("Visuals"), "dragover", data, 100);
    assert.ok(ui.container.querySelector('[aria-label="Panel insertion position"]'));
    const view = ui.container.ownerDocument.defaultView!;
    await act(async () => { view.dispatchEvent(new view.Event("dragend")); });
    assert.equal(ui.container.querySelector('[aria-label="Panel insertion position"]'), null);
    assert.equal(ui.updates(), 0);
  } finally { await ui.close(); }
});

test("mixed batch asks once and adds new copies in order only after confirmation", async () => {
  const initial = fixture(); initial.scenes[1].layers[0].source_panel_id = "existing";
  const ui = await mountTimeline(initial);
  try {
    const data = ui.transfer();
    data.setData("application/panelflow-panel", JSON.stringify({ panels: [
      { panelId: "new", imageUrl: "new.png" }, { panelId: "existing", imageUrl: "existing.png" }
    ] }));
    await ui.dnd(ui.lane("Visuals"), "drop", data, 160);
    assert.equal(ui.state(), initial);
    assert.equal(ui.container.querySelectorAll('[aria-label="Add duplicate panels?"]').length, 1);
    await ui.mouse(ui.find('[data-confirm-duplicate-panels]'), "click", 0);
    assert.deepEqual(ui.state().scenes.map(s => s.layers[0]?.source_panel_id), [undefined, "new", "existing", "existing", undefined]);
    assert.equal(ui.state().scenes[3].id, "b", "existing scene remains present");
    assert.equal(ui.state().narration_clips[0].start_time_sec, 14.5);
    assert.equal(ui.updates(), 1, "whole batch is one undoable action");
  } finally { await ui.close(); }
});

test("Escape cancels a duplicate drop; an unused panel does not prompt", async () => {
  const initial = fixture(); initial.scenes[0].layers[0].source_panel_id = "existing";
  const ui = await mountTimeline(initial);
  try {
    const data = ui.transfer();
    data.setData("application/panelflow-panel", JSON.stringify({ panelId: "existing", imageUrl: "existing.png" }));
    await ui.dnd(ui.lane("Visuals"), "drop", data);
    assert.match(ui.find('dialog').textContent!, /Are you sure you want to add this duplicate panel to the timeline\?/);
    await act(async () => { ui.find('dialog').dispatchEvent(new ui.container.ownerDocument.defaultView!.Event("cancel", { cancelable: true })); });
    assert.equal(ui.state(), initial);
    data.setData("application/panelflow-panel", JSON.stringify({ panelId: "unused", imageUrl: "unused.png" }));
    await ui.dnd(ui.lane("Visuals"), "drop", data);
    assert.equal(ui.container.querySelector('dialog'), null);
    assert.equal(ui.state().scenes.length, 4);
    assert.equal(ui.updates(), 1);
  } finally { await ui.close(); }
});
