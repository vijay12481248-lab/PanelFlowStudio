import test from "node:test";
import assert from "node:assert/strict";
import React from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { readFileSync } from "node:fs";
import { createEmptyEditorState, fitCompositionFrame, resetLayerTransform } from "../editorWorkspace";
import { VideoCompositionCanvas } from "../VideoCompositionCanvas";
import { ContextualInspector } from "../ContextualInspector";

const state = () => createEmptyEditorState("project-test");
test("new editor state never inserts demo music or effects into a user's project", () => {
  const first = state(); const second = state();
  assert.deepEqual(first.bgm_tracks, []);
  assert.deepEqual(first.sfx_cues, []);
  first.scenes.push({ id: "scene", title: "Opening", sequence: 1, start_time_sec: 0, duration_sec: 5, layers: [] });
  assert.equal(second.scenes.length, 0);
});

test("composition fit honors square, landscape and portrait without overflowing available area", () => {
  for (const [ratio, expected] of [["16:9", 16 / 9], ["9:16", 9 / 16], ["1:1", 1]] as const) {
    const result = fitCompositionFrame(ratio, 1000, 480);
    assert.ok(result.width <= 1000 && result.height <= 480);
    assert.ok(Math.abs(result.width / result.height - expected) < 0.0001);
  }
  const normal = fitCompositionFrame("16:9", 1000, 480);
  const half = fitCompositionFrame("16:9", 1000, 480, 50);
  assert.equal(half.width, normal.width / 2);
});

test("reset transform preserves stacking order while resetting presentation", () => {
  assert.deepEqual(resetLayerTransform({ x: 20, y: -10, scale: 2, rotation: 45, opacity: 0.5, z_index: 4 }), { x: 0, y: 0, scale: 1, rotation: 0, opacity: 1, z_index: 4 });
});

test("canvas exposes labeled view zoom rather than an inert fit select", () => {
  const html = renderToStaticMarkup(<VideoCompositionCanvas state={state()} onUpdateState={() => {}} onSelectLayer={() => {}} />);
  assert.match(html, /aria-label="Canvas view zoom"/);
  assert.match(html, /pf-composition-workspace/);
});

test("selected image inspector includes reset and labeled transform inputs", () => {
  const input = state();
  input.scenes = [{ id: "scene", title: "Opening", sequence: 1, start_time_sec: 0, duration_sec: 5, layers: [{ id: "layer", source_page_id: "page", image_url: "test.png", page_sequence: 1, crop: { x: 0, y: 0, width: 100, height: 100 }, transform: { x: 0, y: 0, scale: 1, rotation: 0, opacity: 1, z_index: 1 }, motion_preset: "none", name: "Opening image" }] }];
  input.selected_object = { type: "layer", id: "layer", sceneId: "scene" };
  const html = renderToStaticMarkup(<ContextualInspector state={input} onUpdateState={() => {}} />);
  assert.match(html, /Reset transform/);
  for (const label of ["Position X", "Position Y", "Layer scale", "Layer rotation", "Layer opacity"]) assert.ok(html.includes(`aria-label="${label}"`), label);
});

test("the bootstrap does not install a second job monitor outside App's error provider", () => {
  const source = readFileSync(new URL("../../../main.tsx", import.meta.url), "utf8");
  assert.doesNotMatch(source, /<ErrorProvider>/);
});

test("composition fits 4:5 and explicit custom canvas dimensions without changing source transforms", () => {
  const portrait = fitCompositionFrame("4:5", 1000, 500);
  assert.equal(portrait.width / portrait.height, .8);
  const custom = fitCompositionFrame("custom", 1000, 500, 100, 1410, 789);
  assert.ok(Math.abs(custom.width / custom.height - 1410 / 789) < .0001);
});
