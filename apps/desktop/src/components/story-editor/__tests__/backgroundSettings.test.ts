import assert from "node:assert/strict";
import test from "node:test";
import { DEFAULT_BACKGROUND, createBackgroundPreset, normalizeBackground, resolveBackground } from "../backgroundSettings";
import type { StoryEditorState, VideoScene } from "@panelflow/shared-types";

test("old scenes remain unchanged and missing overrides inherit only explicit defaults", () => {
  const scene = { id: "s" } as VideoScene;
  const state = { scenes: [scene] } as StoryEditorState;
  assert.equal(resolveBackground(state, scene), undefined);
  const configured = { ...state, background_default: createBackgroundPreset("duplicate_blur") };
  assert.equal(resolveBackground(configured, scene)?.blur_sigma, 32);
  assert.equal(resolveBackground(configured, { ...scene, background: createBackgroundPreset("none") })?.enabled, false);
  assert.equal(scene.background, undefined);
});

test("preset bundles are independent and finite controls clamp safely", () => {
  const preset = createBackgroundPreset("duplicate_blur");
  preset.blur_sigma = 80;
  assert.equal(DEFAULT_BACKGROUND.blur_sigma, 32);
  assert.equal(createBackgroundPreset("duplicate_blur").blur_sigma, 32);
  const normalized = normalizeBackground({ ...preset, zoom: NaN, focal_x: -1, opacity: 2, color: "invalid", brightness: Infinity });
  assert.equal(normalized.zoom, 1);
  assert.equal(normalized.focal_x, 0);
  assert.equal(normalized.opacity, 1);
  assert.equal(normalized.color, "#09090b");
  assert.equal(normalized.brightness, -.04);
  assert.equal(createBackgroundPreset("custom_image").source_mode, "custom_image");
  assert.equal(createBackgroundPreset("solid").blur_sigma, 0);
});

test("scene and default settings survive JSON history serialization with stable scene ids", () => {
  const state = { background_default: createBackgroundPreset("gradient"), scenes: [{ id: "s", background: createBackgroundPreset("mirror") }] } as StoryEditorState;
  const restored = JSON.parse(JSON.stringify(state));
  assert.deepEqual(restored, state);
  assert.equal(resolveBackground(restored, restored.scenes[0])?.preset, "mirror");
});
