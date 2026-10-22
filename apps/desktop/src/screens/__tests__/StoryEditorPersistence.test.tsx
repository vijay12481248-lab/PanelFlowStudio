import React, { act } from "react";
import assert from "node:assert/strict";
import test from "node:test";
import { createRequire } from "node:module";

import { api } from "@panelflow/api-client";
import type { Project, StoryEditorState } from "@panelflow/shared-types";

// jsdom is a pinned desktop dev dependency; tests do not rely on Hermes scratch.
const require = createRequire(import.meta.url);
const { JSDOM } = require("jsdom");
// The Node renderer does not consume styles; all screen/child components remain real.
require.extensions[".css"] = () => {};
const { StoryEditorScreen } = require("../StoryEditorScreen");
const { ErrorProvider } = require("../../context/ErrorContext");

function deferred() {
  let resolve!: () => void;
  let reject!: (reason: Error) => void;
  const promise = new Promise<void>((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

async function mountScreen(initial?: StoryEditorState, options: { recovery?: StoryEditorState; backendFailure?: boolean; seedPanels?: boolean; serverHistory?: boolean } = {}) {
  const dom = new JSDOM("<!doctype html><div id='root'></div>", { url: "http://localhost/", pretendToBeVisual: true });
  const globals = ["window", "document", "navigator", "HTMLElement", "HTMLInputElement", "SVGElement", "localStorage", "requestAnimationFrame", "cancelAnimationFrame", "IS_REACT_ACT_ENVIRONMENT"];
  const previous = new Map(globals.map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  for (const key of globals) {
    const value = key === "IS_REACT_ACT_ENVIRONMENT" ? true :
      ["requestAnimationFrame", "cancelAnimationFrame"].includes(key) ? dom.window[key].bind(dom.window) : dom.window[key];
    Object.defineProperty(globalThis, key, { value, configurable: true, writable: true });
  }
  if (options.recovery) dom.window.localStorage.setItem("panelflow_story_editor_test-persistence-only", JSON.stringify(options.recovery));
  const recoveryWrites: string[] = [];
  const setItem = dom.window.Storage.prototype.setItem;
  dom.window.Storage.prototype.setItem = function (key: string, value: string) {
    if (key === "panelflow_story_editor_test-persistence-only") recoveryWrites.push(value);
    setItem.call(this, key, value);
  };
  const originals = new Map<string, unknown>();
  const stub = (key: string, value: unknown) => { originals.set(key, (api as any)[key]); (api as any)[key] = value; };
  stub("checkHealth", async () => ({ status: "ok" }));
  stub("listJobs", async () => []);
  let persisted = initial ?? null;
  let historyRevision = 0;
  const past: (StoryEditorState | null)[] = [], future: (StoryEditorState | null)[] = [];
  const moves: string[] = [];
  const history = () => ({ scope: "project:test-persistence-only", revision: historyRevision, undoCount: past.length, redoCount: future.length,
    canUndo: past.length > 0, canRedo: future.length > 0, undoLabel: "Edit", redoLabel: "Edit", busy: false, conflicted: false, recoveryRequired: false, error: null, fingerprint: "f".repeat(64) });
  stub("getCachedProjectHistory", () => options.serverHistory ? history() : null);
  stub("moveProjectHistory", async (_project: string, direction: string) => {
    moves.push(direction);
    if (direction === "undo") { future.push(persisted); persisted = past.pop() ?? null; }
    else { past.push(persisted); persisted = future.pop() ?? null; }
    historyRevision++;
    return { state: persisted, history: history() };
  });
  for (const key of ["listCharacters", "listTextRegions"]) stub(key, async () => []);
  stub("listPages", async () => options.seedPanels ? [{ id: "recovery-page", sequence: 1, width: 1200, height: 1800 }] : []);
  stub("listPanels", async () => options.seedPanels ? [{ id: "recovery-panel", page_id: "recovery-page", page_sequence: 1, x: 0, y: 0, width: 1200, height: 1800 }] : []);
  const panelWrites: unknown[][] = [];
  stub("updatePanel", async (...args: unknown[]) => {
    panelWrites.push(args);
    return { id: args[1], page_id: "recovery-page", page_sequence: 1, x: args[2], y: args[3], width: args[4], height: args[5] };
  });
  for (const key of ["getScript", "getStoryboard"]) stub(key, async () => null);
  stub("getStoryEditorState", async () => {
    if (options.backendFailure) throw new Error("test-only offline recovery");
    return { state: initial ?? null, ...(options.serverHistory ? { history: history() } : {}) };
  });
  const writes: StoryEditorState[] = [];
  const requests: ReturnType<typeof deferred>[] = [];
  stub("saveStoryEditorState", (_id: string, snapshot: StoryEditorState) => {
    writes.push(snapshot);
    const request = deferred();
    requests.push(request);
    return request.promise.then(() => {
      if (options.serverHistory) { past.push(persisted); future.length = 0; persisted = structuredClone(snapshot); historyRevision++; }
      return { state: snapshot, history: options.serverHistory ? history() : undefined, updated_at: "fixture" };
    });
  });
  const { createRoot } = await import("react-dom/client");
  const container = dom.window.document.getElementById("root")!;
  const root = createRoot(container);
  let navigations = 0;
  await act(async () => root.render(<ErrorProvider><StoryEditorScreen project={{ id: "test-persistence-only", title: "Test fixture" } as Project}
    onBack={() => { navigations++; }} onExport={() => {}} /></ErrorProvider>));
  assert.doesNotMatch(container.textContent!, /Loading saved scenes/);
  const button = (name: string) => {
    const element = Array.from(container.querySelectorAll("button")).find((el: any) =>
      el.getAttribute("aria-label") === name || el.textContent?.trim() === name);
    assert.ok(element, `Expected visible screen control: ${name}`);
    return element as HTMLButtonElement;
  };
  const click = async (name: string) => { await act(async () => button(name).click()); };
  return {
    container, writes, requests, recoveryWrites, panelWrites, moves, click, navigations: () => navigations,
    async duration(value: number) {
      const label = Array.from(container.querySelectorAll("label")).find(el => el.textContent === "Scene Total Duration");
      const input = label?.parentElement?.querySelector("input");
      assert.ok(input, "mounted inspector duration input");
      await act(async () => {
        Object.getOwnPropertyDescriptor(dom.window.HTMLInputElement.prototype, "value")!.set!.call(input, String(value));
        input.dispatchEvent(new dom.window.Event("input", { bubbles: true }));
        input.dispatchEvent(new dom.window.Event("change", { bubbles: true }));
      });
    },
    async close() {
      await act(async () => root.unmount());
      for (const [key, original] of originals) (api as any)[key] = original;
      dom.window.close();
      for (const [key, descriptor] of previous) {
        if (descriptor) Object.defineProperty(globalThis, key, descriptor);
        else delete (globalThis as any)[key];
      }
    },
  };
}

test("Undo flushes the pending checkpoint before asking the server; redo restores the saved result without another autosave", async () => {
  const { createEmptyEditorState } = await import("../../components/story-editor/editorWorkspace");
  const initial = createEmptyEditorState("test-persistence-only");
  initial.scenes = [
    { id: "a", title: "Scene A", sequence: 1, duration_sec: 4, start_time_sec: 0, layers: [] },
    { id: "b", title: "Scene B", sequence: 2, duration_sec: 4, start_time_sec: 4, layers: [] },
  ];
  initial.selected_object = { type: "scene", id: "a" };
  const screen = await mountScreen(initial, { serverHistory: true });
  try {
    await screen.click("Delete Selected Clip (Del)"); await screen.click("Undo");
    assert.equal(screen.writes.length, 1); assert.deepEqual(screen.moves, []);
    await act(async () => screen.requests[0].resolve());
    assert.deepEqual(screen.moves, ["undo"]);
    assert.deepEqual(JSON.parse(screen.recoveryWrites.at(-1)!).scenes.map((scene: any) => scene.id), ["a", "b"]);
    await screen.click("Redo");
    assert.deepEqual(screen.moves, ["undo", "redo"]);
    assert.deepEqual(JSON.parse(screen.recoveryWrites.at(-1)!).scenes.map((scene: any) => scene.id), ["b"]);
    assert.equal(screen.writes.length, 1, "canonical undo/redo replies must not enter autosave as new edits");
  } finally { await screen.close(); }
});

for (const ripple of [false, true]) {
  test(`mounted inspector duration obeys Ripple ${ripple ? "ON" : "OFF"} and saves fixed timing`, async () => {
    const { createEmptyEditorState } = await import("../../components/story-editor/editorWorkspace");
    const initial = createEmptyEditorState("test-persistence-only");
    initial.ripple_edit = ripple;
    initial.scenes = [
      { id: "a", sequence: 1, title: "Scene A", duration_sec: 6, start_time_sec: 0, layers: [] },
      { id: "b", sequence: 2, title: "Scene B", duration_sec: 4, start_time_sec: 6, layers: [] },
    ];
    initial.selected_object = { type: "scene", id: "a" };
    const screen = await mountScreen(initial);
    try {
      await screen.click("timing");
      await screen.duration(8);
      await screen.click("Return to Projects Dashboard");
      assert.equal(screen.writes.length, 1);
      assert.deepEqual(screen.writes[0].scenes.map(scene => [scene.duration_sec, scene.start_time_sec]), ripple ? [[8, 0], [4, 8]] : [[6, 0], [4, 6]]);
      await act(async () => screen.requests[0].resolve());
    } finally { await screen.close(); }
  });
}

for (const action of ["Delete Selected Clip (Del)", "Split Scene at Playhead (Scissors)", "Duplicate Selected Scene"]) {
  test(`Ripple OFF ${action} preserves existing later scene anchors`, async () => {
    const { createEmptyEditorState } = await import("../../components/story-editor/editorWorkspace");
    const initial = createEmptyEditorState("test-persistence-only");
    initial.ripple_edit = false; initial.playhead_sec = 2;
    initial.scenes = [
      { id: "a", sequence: 1, title: "Scene A", duration_sec: 4, start_time_sec: 0, layers: [] },
      { id: "b", sequence: 2, title: "Scene B", duration_sec: 4, start_time_sec: 6, layers: [] },
    ];
    initial.selected_object = { type: "scene", id: "a" };
    const screen = await mountScreen(initial);
    try {
      await screen.click(action);
      await screen.click("Return to Projects Dashboard");
      const scenes = screen.writes[0].scenes;
      assert.equal(scenes.find(scene => scene.id === "b")!.start_time_sec, 6);
      if (action.startsWith("Split")) assert.deepEqual(scenes.map(scene => [scene.start_time_sec, scene.duration_sec]), [[0, 2], [2, 2], [6, 4]]);
      if (action.startsWith("Duplicate")) assert.deepEqual(scenes.map(scene => [scene.start_time_sec, scene.duration_sec]), [[0, 4], [6, 4], [10, 4]]);
      await act(async () => screen.requests[0].resolve());
    } finally { await screen.close(); }
  });
}

for (const control of ["Return to Projects Dashboard", "My Projects"]) {
  test(`${control}: immediate Back flushes the latest edit and waits for engine save before navigation`, async () => {
    const screen = await mountScreen();
    try {
      await screen.click("Advanced");
      assert.equal(screen.writes.length, 0, "edit is still inside the debounce window");
      await screen.click(control);
      assert.equal(screen.writes.length, 1, "Back must flush immediately, not wait for autosave");
      assert.equal(screen.writes[0].mode, "advanced");
      assert.equal(screen.navigations(), 0, "do not leave while the engine save is unresolved");
      await act(async () => screen.requests[0].resolve());
      assert.equal(screen.navigations(), 1);
    } finally { await screen.close(); }
  });
}

test("failed Back stays in the editor, exposes a save error, and retries the retained edit without another edit", async () => {
  const screen = await mountScreen();
  try {
    await screen.click("Advanced");
    await screen.click("Return to Projects Dashboard");
    await act(async () => screen.requests[0].reject(new Error("test-only engine save failure")));
    assert.equal(screen.navigations(), 0, "a failed save must not navigate");
    const alert = screen.container.querySelector('[role="alert"]');
    assert.ok(alert, "the screen must render its save failure visibly");
    assert.match(alert.textContent!, /Could not save this project/);
    await screen.click("Retry save");
    assert.equal(screen.writes.length, 2, "retry flushes without waiting for another edit or debounce");
    assert.deepEqual(screen.writes[1], screen.writes[0], "retry retains the failed snapshot");
    assert.equal(screen.navigations(), 0);
    await act(async () => screen.requests[1].resolve());
    assert.equal(screen.container.querySelector('[role="alert"]'), null, "success clears the failure");
    await screen.click("My Projects");
    assert.equal(screen.navigations(), 1, "navigation succeeds after retry with no additional edit");
    assert.equal(screen.writes.length, 2, "the saved revision need not be written again");
  } finally { await screen.close(); }
});

async function recoveryFixture() {
  const { createEmptyEditorState } = await import("../../components/story-editor/editorWorkspace");
  const state = createEmptyEditorState("test-persistence-only");
  state.scenes = [{ id: "recovery-scene", sequence: 1, title: "Recovery", start_time_sec: 0, duration_sec: 5, layers: [{
    id: "recovery-layer", name: "Recovery image", source_page_id: "recovery-page", page_sequence: 1,
    image_url: "http://127.0.0.1:8765/api/projects/test-persistence-only/pages/recovery-page/file;pf-token=expired-recovery-session?v=7",
    crop: { x: 0, y: 0, width: 1200, height: 1800 }, motion_preset: "none",
    transform: { x: 0, y: 0, scale: 1.4, rotation: 0, opacity: 1, z_index: 1 },
  }] }];
  state.selected_object = { type: "layer", id: "recovery-layer", sceneId: "recovery-scene" };
  return state;
}

test("offline local recovery hydrates old page images with the current session", async () => {
  api.setEngineToken("current-recovery-session");
  const initial = await recoveryFixture();
  const screen = await mountScreen(undefined, { recovery: initial, backendFailure: true });
  try {
    const images = [...screen.container.querySelectorAll("img")].map(image => image.getAttribute("src"));
    assert.ok(images.includes("http://127.0.0.1:8765/api/projects/test-persistence-only/pages/recovery-page/file;pf-token=current-recovery-session?v=7"));
    assert.ok(images.every(src => !src?.includes("expired-recovery-session")));
    await screen.click("Advanced"); await screen.click("My Projects");
    assert.equal(screen.writes[0].scenes[0].layers[0].transform.scale, 1.4);
    await act(async () => screen.requests[0].resolve());
  } finally { await screen.close(); api.setEngineToken(""); }
});

test("a failed engine save keeps a credential-free local recovery snapshot", async () => {
  api.setEngineToken("current-recovery-session");
  const screen = await mountScreen(await recoveryFixture());
  try {
    await screen.click("Advanced"); await screen.click("My Projects");
    await act(async () => screen.requests[0].reject(new Error("test-only backend failure")));
    assert.ok(screen.recoveryWrites.length > 0);
    for (const value of screen.recoveryWrites) {
      assert.doesNotMatch(value, /pf-token|expired-recovery-session|current-recovery-session/);
      assert.equal(JSON.parse(value).scenes[0].layers[0].image_url, "/api/projects/test-persistence-only/pages/recovery-page/file?v=7");
    }
    assert.equal(screen.navigations(), 0);
  } finally { await screen.close(); api.setEngineToken(""); }
});

test("initial panel-derived recovery snapshots do not store engine capabilities", async () => {
  api.setEngineToken("current-recovery-session");
  const screen = await mountScreen(undefined, { seedPanels: true });
  try {
    assert.ok(screen.recoveryWrites.length > 0);
    for (const value of screen.recoveryWrites) assert.doesNotMatch(value, /pf-token|current-recovery-session/);
  } finally { await screen.close(); api.setEngineToken(""); }
});

test("source page clicks open Setup even for the current page; Play returns to the video preview", async () => {
  const screen = await mountScreen(await recoveryFixture(), { seedPanels: true });
  try {
    assert.ok(screen.container.querySelector('[aria-label="Video composition workspace"]'));
    await screen.click("Select page 1");
    assert.ok(screen.container.querySelector('[aria-label="Source page setup"]'));
    assert.equal(screen.container.querySelector('[aria-label="Video composition workspace"]'), null);
    assert.ok(screen.container.querySelector('[aria-label="Edit panel 1"]'));
    await act(async () => (screen.container.querySelector('[aria-label="Edit panel 1"]') as unknown as HTMLElement)
      .dispatchEvent(new window.MouseEvent("click", { bubbles: true })));
    assert.ok(screen.container.querySelector('[aria-label="Selector se handle"]'), "existing panel has working Setup handles");
    assert.equal(screen.container.querySelector('[aria-label="Source tools"]'), null, "tools have moved out of the sidebar");
    await screen.click("Player");
    assert.ok(screen.container.querySelector('[aria-label="Video composition workspace"]'));
    assert.equal(screen.container.querySelector('[title="Resize Corner (NW)"]'), null, "Player does not expose Setup handles");
    await screen.click("Select page 1");
    assert.ok(screen.container.querySelector('[aria-label="Source page setup"]'), "same page reopens Setup");
    await screen.click("Play video");
    assert.equal(screen.container.querySelector('[aria-label="Source page setup"]'), null);
    assert.ok(screen.container.querySelector('[aria-label="Video composition workspace"]'));
    assert.equal(screen.container.querySelector('[aria-label="Canvas mode"] button[aria-pressed="true"]')?.textContent, "Player");
    await screen.click("Select page 1");
    assert.ok(screen.container.querySelector('[aria-label="Source page setup"]'));
    assert.ok(screen.container.querySelector('[aria-label="Play video"]'), "source selection pauses playback");
  } finally { await screen.close(); }
});

test("unsaved Setup selectors survive switching to Player and back", async () => {
  const screen = await mountScreen(await recoveryFixture(), { seedPanels: true });
  try {
    await screen.click("Select page 1");
    const handle = screen.container.querySelector('[aria-label="Selector nw handle"]')!;
    await act(async () => handle.dispatchEvent(new window.KeyboardEvent("keydown", { key: "ArrowRight", bubbles: true })));
    const saveButton = () => Array.from(screen.container.querySelectorAll("button")).find(el => el.textContent === "Save selectors")!;
    assert.equal(saveButton().disabled, false);
    await screen.click("Player"); await screen.click("Select page 1");
    assert.equal(saveButton().disabled, false, "the resized draft was retained without modifying the timeline");
    assert.equal(screen.writes.length, 0);
  } finally { await screen.close(); }
});

test("Setup selection does not create scenes; adding the existing panel explicitly appends one scene", async () => {
  const screen = await mountScreen(await recoveryFixture(), { seedPanels: true });
  try {
    await screen.click("Select page 1");
    await act(async () => screen.container.querySelector('[aria-label="Edit panel 1"]')!
      .dispatchEvent(new window.MouseEvent("click", { bubbles: true })));
    assert.equal(screen.writes.length, 0, "browsing panels does not change saved timeline state");
    await screen.click("Add panel to timeline");
    assert.ok(screen.container.querySelector('[aria-label="Video composition workspace"]'));
    await screen.click("My Projects");
    assert.equal(screen.writes[0].scenes.length, 2);
    assert.equal(screen.writes[0].scenes[1].layers[0].source_panel_id, "recovery-panel");
    assert.equal(screen.writes[0].is_playing, false);
    await act(async () => screen.requests[0].resolve());
  } finally { await screen.close(); }
});

