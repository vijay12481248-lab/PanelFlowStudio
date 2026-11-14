import test from "node:test";
import assert from "node:assert/strict";
import { FG } from "../fusionGraph";
import { REF_HEIGHT, changesPicture, grainPixels, isFusionActive, newEffect, newFusion, refScale, scaledNode } from "../effects";

const flat = (w: number, h: number, v = 128) => {
  const d = new Uint8ClampedArray(w * h * 4);
  for (let i = 0; i < d.length; i += 4) d.set([v, v, v, 255], i);
  return d;
};

test("ChronoFlow's Fusion renderer is loaded and exposes processNode", () => {
  assert.equal(typeof FG.processNode, "function");
});

test("every effect type starts with sensible parameters and its own id", () => {
  const types = ["glow", "vignette", "grain", "blur", "text"] as const;
  const ids = new Set(types.map((t) => newEffect(t).id));
  assert.equal(ids.size, 5);
  for (const t of types) {
    const e = newEffect(t);
    assert.equal(e.enabled, true);
    assert.ok(Object.keys(e.params).length > 0, t);
  }
  assert.equal(newEffect("text").params.text, "TITLE");
  assert.equal(isFusionActive(newFusion()), false, "an empty stack changes nothing");
});

test("an effect that would change nothing is not baked", () => {
  assert.equal(changesPicture({ ...newEffect("text"), params: { ...newEffect("text").params, text: "   " } }), false);
  assert.equal(changesPicture({ ...newEffect("blur"), params: { radius: 0 } }), false);
  assert.equal(changesPicture({ ...newEffect("grain"), params: { intensity: 0, size: 1, seed: 1 } }), false);
  assert.equal(changesPicture({ ...newEffect("vignette"), params: { ...newEffect("vignette").params, opacity: 0 } }), false);
  assert.equal(changesPicture({ ...newEffect("glow"), enabled: false }), false, "a switched-off effect is skipped");
  assert.equal(isFusionActive({ effects: [{ ...newEffect("glow"), enabled: false }, newEffect("text")] }), true);
});

test("pixel sizes are written for a 720 high frame and scaled to the picture", () => {
  assert.equal(refScale(REF_HEIGHT), 1);
  assert.equal(refScale(2160), 3);
  const blur = { ...newEffect("blur"), params: { radius: 5 } };
  assert.equal(scaledNode(blur, 1440).params.radius, 10);
  assert.equal(scaledNode(blur, 1440).type, "blur");
  const glow = { ...newEffect("glow"), params: { size: 10, intensity: 1 } };
  assert.equal(scaledNode(glow, 2160).params.size, 30);
  assert.equal(scaledNode(newEffect("text"), 720).type, "text_plus", "text is ChronoFlow's Text+");
  const text = { ...newEffect("text"), params: { ...newEffect("text").params, glowSize: 4, fontSize: 40 } };
  const node = scaledNode(text, 1440);
  assert.equal(node.params.glowSize, 8);
  assert.equal(node.params.fontSize, 40, "the renderer scales the font itself, so it is left alone");
  assert.equal(node.params.enabled, true);
  assert.equal(blur.params.radius, 5, "the stored effect is not changed");
});

test("grain is deterministic, adds no overall brightness, and a bigger size gives coarser grain", () => {
  const w = 64, h = 48;
  const a = flat(w, h), b = flat(w, h);
  grainPixels(a, w, h, 0.4, 1, 7);
  grainPixels(b, w, h, 0.4, 1, 7);
  assert.deepEqual(a, b, "same seed, same picture");
  const c = flat(w, h);
  grainPixels(c, w, h, 0.4, 1, 8);
  assert.notDeepEqual(a, c, "another seed, another grain");
  let sum = 0, max = 0;
  for (let i = 0; i < a.length; i += 4) { sum += a[i] - 128; max = Math.max(max, Math.abs(a[i] - 128)); }
  assert.ok(Math.abs(sum / (w * h)) < 3, `mean shift ${sum / (w * h)}`);
  assert.ok(max > 8 && max <= 0.4 * 64 + 1, `largest step ${max}`);
  for (let i = 0; i < a.length; i += 4) assert.ok(a[i] === a[i + 1] && a[i] === a[i + 2], "the same noise on all channels");

  const none = flat(w, h);
  grainPixels(none, w, h, 0, 1, 7);
  assert.deepEqual(none, flat(w, h), "zero amount changes nothing");

  const coarse = flat(w, h);
  grainPixels(coarse, w, h, 0.4, 4, 7);
  assert.equal(coarse[0], coarse[4 * 3], "pixels in one 4 x 4 cell share a value");
  assert.equal(coarse[0], coarse[(w * 3) * 4], "also down the column");
  const fine = flat(w, h);
  grainPixels(fine, w, h, 0.4, 1, 7);
  let differing = 0;
  for (let x = 0; x < 15; x++) if (fine[x * 4] !== fine[(x + 1) * 4]) differing++;
  assert.ok(differing >= 10, `single-pixel grain should differ between most neighbours, got ${differing} of 15`);
});

test("white stays inside 0..255 under heavy grain", () => {
  const d = flat(16, 16, 250);
  grainPixels(d, 16, 16, 1, 1, 3);
  for (let i = 0; i < d.length; i += 4) assert.ok(d[i] >= 0 && d[i] <= 255);
});
