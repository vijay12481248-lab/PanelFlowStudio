import React, { act } from "react";
import test from "node:test";
import assert from "node:assert/strict";
import { renderToStaticMarkup } from "react-dom/server";
import { createRequire } from "node:module";
import { api } from "@panelflow/api-client";
import { createBackgroundPreset } from "../backgroundSettings";
import type { StoryEditorState, VideoScene, VisualLayer } from "@panelflow/shared-types";
import { BackgroundInspector } from "../BackgroundInspector";
import { BackgroundPreview, resolveBackgroundSource, foregroundSize } from "../BackgroundPreview";

const layer = (id: string, more = {}): VisualLayer => ({ id, image_url: `${id}.png`, source_page_id: "p", page_sequence: 1, crop: { x: 0, y: 0, width: 100, height: 200 }, transform: { x: 0, y: 0, scale: 1, rotation: 0, opacity: 1, z_index: 0 }, ...more });
const scene = { id: "scene", start_time_sec: 0, duration_sec: 4, layers: [layer("hidden", { visible: false }), layer("late", { start_offset_sec: 2 }), layer("visible")] } as VideoScene;
const state = { scenes: [scene], playhead_sec: 1, track_states: {} } as StoryEditorState;

test("background follows active visible visual while explicit pins remain independent of timing", () => {
  assert.equal(resolveBackgroundSource(state, scene, { source_mode: "follow_active_visual" } as any)?.id, "visible");
  assert.equal(resolveBackgroundSource(state, scene, { source_mode: "pinned_layer", source_layer_id: "late" } as any)?.id, "late");
  assert.equal(resolveBackgroundSource(state, scene, { source_mode: "pinned_layer", source_layer_id: "missing" } as any), undefined);
  assert.equal(resolveBackgroundSource({ ...state, track_states: { Visuals: { visible: false, locked: false } } }, scene, { source_mode: "follow_active_visual" } as any), undefined);
  assert.equal(resolveBackgroundSource(state, { ...scene, layers: [layer("zero", { transform: { ...layer("a").transform, opacity: 0 } })] }, { source_mode: "follow_active_visual" } as any), undefined);
});

test("foreground contain and cover preserve aspect across landscape and portrait canvases", () => {
  assert.deepEqual(foregroundSize(600, 1200, 1920, 1080, "contain"), { width: 540, height: 1080 });
  assert.deepEqual(foregroundSize(600, 1200, 1920, 1080, "cover"), { width: 1920, height: 3840 });
  assert.deepEqual(foregroundSize(1920, 1080, 1080, 1920, "contain"), { width: 1080, height: 607.5 });
});

test("inspector exposes supported presets, accessible controls and explicit scope actions", () => {
  const html = renderToStaticMarkup(<BackgroundInspector state={state} scene={scene} onUpdateState={() => {}} />);
  for (const label of ["Duplicate Blur", "Solid Color", "Gradient", "Mirror", "Edge Stretch", "Custom Image", "Use project default", "Set as project default", "Copy to all scenes", "Reset preset", "Before / After", "Enable background", "Blur (1080p)", "Foreground fit"]) assert.ok(html.includes(label), label);
  assert.ok(!html.includes("Custom Video"));
});

test("preview is inert for disabled settings and scales blur by canvas height", () => {
  const base = { enabled: true, preset: "duplicate_blur", source_mode: "follow_active_visual", blur_sigma: 32, zoom: 1, opacity: 1, focal_x: .5, focal_y: .5, brightness: 0, saturation: 1, color: "#09090b", tint_opacity: 0, motion: "none" } as any;
  assert.equal(renderToStaticMarkup(<BackgroundPreview settings={{ ...base, enabled: false }} sourceUrl="panel.png" width={960} height={540} progress={0} />), "");
  const html = renderToStaticMarkup(<BackgroundPreview settings={base} sourceUrl="panel.png" width={960} height={540} progress={0} />);
  assert.ok(html.includes('stdDeviation="16"'));
  assert.ok(html.includes('edgeMode="duplicate"'));
  assert.ok(html.includes("panel.png"));
  assert.ok(html.includes('aria-hidden="true"'));
});

async function mountInspector(initial: StoryEditorState) {
  const { JSDOM } = createRequire(import.meta.url)("jsdom");
  const dom = new JSDOM("<!doctype html><div id='root'></div>", { url: "http://localhost/", pretendToBeVisual: true });
  const keys = ["window", "document", "navigator", "HTMLElement", "HTMLInputElement", "IS_REACT_ACT_ENVIRONMENT"];
  const previous = new Map(keys.map(key => [key, Object.getOwnPropertyDescriptor(globalThis, key)]));
  for (const key of keys) Object.defineProperty(globalThis, key, { configurable: true, writable: true, value: key === "IS_REACT_ACT_ENVIRONMENT" ? true : dom.window[key] });
  const { createRoot } = await import("react-dom/client");
  const container = dom.window.document.getElementById("root")!;
  const root = createRoot(container);
  let current = initial;
  const history: StoryEditorState[] = [];
  function Host() {
    const [value, setValue] = React.useState(initial);
    current = value;
    return <BackgroundInspector state={value} scene={value.scenes[0]} onUpdateState={updater => setValue(previous => { history.push(previous); return updater(previous); })} />;
  }
  await act(async () => root.render(<Host />));
  const click = async (label: string) => {
    const button = Array.from(container.querySelectorAll("button")).find((node: any) => node.textContent.trim() === label) as HTMLButtonElement;
    assert.ok(button, label);
    await act(async () => button.click());
  };
  const select = async (label: string, value: string) => {
    const element = container.querySelector(`[aria-label="${label}"]`) as HTMLSelectElement;
    await act(async () => { element.value = value; element.dispatchEvent(new dom.window.Event("change", { bubbles: true })); });
  };
  return { container, dom, click, select, history, get current() { return current; }, close: async () => {
    await act(async () => root.unmount());
    for (const [key, descriptor] of previous) { if (descriptor) Object.defineProperty(globalThis, key, descriptor); else delete (globalThis as any)[key]; }
    dom.window.close();
  } };
}

test("scene preset changes preserve defaults and other scenes; default inheritance and explicit copy use history updater", async () => {
  const original = { ...state, project_id: "project", background_default: createBackgroundPreset("solid"), scenes: [{ ...scene }, { ...scene, id: "second" }], marker: "preserve" } as StoryEditorState;
  const ui = await mountInspector(original);
  try {
    await ui.click("Duplicate Blur");
    assert.equal(ui.current.scenes[0].background?.preset, "duplicate_blur");
    assert.equal(ui.current.background_default?.preset, "solid");
    assert.equal(ui.current.scenes[1], original.scenes[1]);
    assert.equal(original.scenes[0].background, undefined);
    await ui.click("Set as project default");
    assert.equal(ui.current.background_default?.preset, "duplicate_blur");
    assert.equal(ui.current.scenes[0].background, undefined);
    await ui.click("Gradient");
    await ui.click("Copy to all scenes");
    assert.ok(ui.current.scenes.every(current => current.background?.preset === "gradient"));
    assert.notEqual(ui.current.scenes[0].background, ui.current.scenes[1].background);
    await ui.click("Use project default");
    assert.equal(ui.current.scenes[0].background, undefined);
    assert.equal(ui.current.scenes[1].background?.preset, "gradient");
    assert.equal((ui.current as any).marker, "preserve");
    assert.equal(ui.history.length, 5);
    assert.equal(ui.history[0], original);
  } finally { await ui.close(); }
});

test("before-after is preview-only and pinning can bind a static inactive image", async () => {
  const initial = { ...state, background_default: createBackgroundPreset("duplicate_blur") };
  const ui = await mountInspector(initial);
  try {
    await ui.click("Before / After");
    assert.equal(ui.current.background_preview_disabled, true);
    assert.equal(ui.current.background_default, initial.background_default);
    assert.equal(ui.current.scenes, initial.scenes);
    await ui.click("Before / After");
    assert.equal(ui.current.background_preview_disabled, false);
    await ui.select("Background source", "pinned_layer");
    const options = Array.from(ui.container.querySelectorAll('[aria-label="Pinned visual layer"] option')).map((node: any) => node.value);
    assert.deepEqual(options, ["", "hidden", "late", "visible"]);
    await ui.select("Pinned visual layer", "visible");
    assert.equal(ui.current.scenes[0].background?.source_layer_id, "visible");
    await ui.click("Reset preset");
    assert.equal(ui.current.scenes[0].background?.source_mode, "follow_active_visual");
  } finally { await ui.close(); }
});

test("selecting All Panels in Timeline scope enables and applies background to all panels in a single action", async () => {
  const multi = {
    ...state,
    scenes: [
      { ...scene, id: "scene-1" },
      { ...scene, id: "scene-2" },
      { ...scene, id: "scene-3" },
    ],
  } as StoryEditorState;
  const ui = await mountInspector(multi);
  try {
    await ui.click("All Panels in Timeline");
    assert.ok(ui.current.scenes.every(s => s.background?.enabled));
    assert.equal(ui.current.scenes.length, 3);
    await ui.click("Mirror");
    assert.ok(ui.current.scenes.every(s => s.background?.preset === "mirror"));
    assert.equal(ui.current.background_default?.preset, "mirror");
  } finally { await ui.close(); }
});
