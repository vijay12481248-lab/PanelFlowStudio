import test from "node:test";
import assert from "node:assert/strict";
import {
  applyAspect, aspectRatio, cropForAspect, cutGeometry, dragCrop, effectiveCrop, fitCropInside, flipCut, isCutIdentity, newCut, orientedSize,
  rotatedFits, turnCut, type Crop,
} from "../geometry";

const near = (a: number, b: number, tol = 1e-6) => assert.ok(Math.abs(a - b) <= tol, `${a} is not within ${tol} of ${b}`);
const ratioOf = (c: Crop, fw: number, fh: number) => (c.w * fw) / (c.h * fh);

test("a new cut changes nothing, and any edit makes it count", () => {
  assert.equal(isCutIdentity(newCut()), true);
  assert.equal(isCutIdentity(null), true);
  for (const edit of [{ turns: 1 as const }, { flipH: true }, { flipV: true }, { angle: 2 }, { longEdge: 1024 }, { crop: { x: 0, y: 0, w: 0.5, h: 0.5 } }]) {
    assert.equal(isCutIdentity({ ...newCut(), ...edit }), false, JSON.stringify(edit));
  }
});

test("quarter turns swap width and height", () => {
  assert.deepEqual(orientedSize(1792, 2368, 0), [1792, 2368]);
  assert.deepEqual(orientedSize(1792, 2368, 1), [2368, 1792]);
  assert.deepEqual(orientedSize(1792, 2368, 2), [1792, 2368]);
  assert.deepEqual(orientedSize(1792, 2368, 3), [2368, 1792]);
});

test("the largest centred crop of an aspect has that aspect and fits the frame", () => {
  for (const [id, fw, fh] of [["16:9", 2000, 1000], ["9:16", 2000, 1000], ["1:1", 1792, 2368], ["4:5", 1000, 1000], ["original", 800, 600]] as const) {
    const c = cropForAspect(fw, fh, 0, aspectRatio(id, fw, fh));
    near(ratioOf(c, fw, fh), aspectRatio(id, fw, fh)!, 1e-9);
    assert.ok(c.x >= 0 && c.y >= 0 && c.x + c.w <= 1 + 1e-9 && c.y + c.h <= 1 + 1e-9, id);
    near(c.x + c.w / 2, 0.5); near(c.y + c.h / 2, 0.5);
    assert.ok(Math.abs(c.w - 1) < 1e-9 || Math.abs(c.h - 1) < 1e-9, `${id} uses the full width or the full height`);
  }
  assert.equal(aspectRatio("free", 10, 10), null);
});

test("a straightened picture never keeps its empty corners: the crop is shrunk to fit inside the rotated content", () => {
  const full: Crop = { x: 0, y: 0, w: 1, h: 1 };
  assert.equal(rotatedFits(full, 1000, 1000, 0), true);
  assert.equal(rotatedFits(full, 1000, 1000, 10), false, "the full frame has empty corners once rotated");
  const c = effectiveCrop({ ...newCut(), angle: 10 }, 1000, 1000);
  assert.equal(rotatedFits(c, 1000, 1000, 10), true);
  assert.ok(c.w < 1 && c.h < 1 && c.w > 0.6, `inscribed crop ${c.w}`);
  const same = fitCropInside(c, 1000, 1000, 10);
  assert.equal(same, c, "a crop that already fits is returned as it is");
  const big = fitCropInside({ x: 0.1, y: 0.1, w: 0.8, h: 0.8 }, 1000, 1000, 30);
  assert.equal(rotatedFits(big, 1000, 1000, 30), true);
  near(big.w / big.h, 1, 1e-9); // shape kept
  for (const angle of [-45, -20, 5, 45]) assert.equal(rotatedFits(cropForAspect(1600, 900, angle, 16 / 9), 1600, 900, angle), true, `angle ${angle}`);
});

test("dragging moves a crop inside the frame and never past its edges", () => {
  const start: Crop = { x: 0.2, y: 0.2, w: 0.4, h: 0.4 };
  const moved = dragCrop(start, "move", 0.1, -0.1, null);
  near(moved.x, 0.3); near(moved.y, 0.1); near(moved.w, 0.4); near(moved.h, 0.4);
  const far = dragCrop(start, "move", 5, 5, null);
  near(far.x + far.w, 1); near(far.y + far.h, 1);
  const e = dragCrop(start, "e", 0.2, 0.9, null);
  near(e.x, 0.2); near(e.y, 0.2); near(e.h, 0.4);
  near(e.w, 0.6);
  const tooSmall = dragCrop(start, "w", 5, 0, null);
  assert.ok(tooSmall.w >= 0.04 - 1e-9, "a crop cannot collapse");
});

test("with a locked aspect a corner drag keeps the shape and stays inside", () => {
  const ratio = 0.5; // normalized w / h
  const start: Crop = { x: 0.1, y: 0.1, w: 0.2, h: 0.4 };
  for (const [handle, dx, dy] of [["se", 0.3, 0.1], ["nw", -0.05, -0.2], ["ne", 0.2, -0.05], ["sw", -0.1, 0.5], ["e", 0.2, 0], ["s", 0, 0.3]] as const) {
    const c = dragCrop(start, handle, dx, dy, ratio);
    near(c.w / c.h, ratio, 1e-9);
    assert.ok(c.x >= -1e-9 && c.y >= -1e-9 && c.x + c.w <= 1 + 1e-9 && c.y + c.h <= 1 + 1e-9, `${handle} stays inside: ${JSON.stringify(c)}`);
  }
  const se = dragCrop(start, "se", 0.2, 0.2, ratio);
  near(se.x, start.x); near(se.y, start.y); // the opposite corner is the anchor
});

test("the output size follows the crop, then the long edge", () => {
  const cut = { ...newCut(), crop: { x: 0, y: 0, w: 0.5, h: 0.5 } };
  const g = cutGeometry(cut, 2000, 1000);
  assert.deepEqual([g.outW, g.outH], [1000, 500]);
  const scaled = cutGeometry({ ...cut, longEdge: 500 }, 2000, 1000);
  assert.deepEqual([scaled.outW, scaled.outH], [500, 250]);
  const turned = cutGeometry({ ...newCut(), turns: 1 }, 2000, 1000);
  assert.deepEqual([turned.fw, turned.fh, turned.outW, turned.outH], [1000, 2000, 1000, 2000]);
  const huge = cutGeometry({ ...newCut(), longEdge: 99999 }, 2000, 1000);
  assert.ok(Math.max(huge.outW, huge.outH) <= 16384, "capped at the largest canvas");
});

test("turning and flipping carry the crop with the picture", () => {
  const crop: Crop = { x: 0.1, y: 0.2, w: 0.3, h: 0.4 };
  const cw = turnCut({ ...newCut(), crop }, 1);
  assert.equal(cw.turns, 1);
  near(cw.crop!.x, 1 - 0.2 - 0.4); near(cw.crop!.y, 0.1); near(cw.crop!.w, 0.4); near(cw.crop!.h, 0.3);
  const back = turnCut(cw, -1);
  assert.equal(back.turns, 0);
  for (const k of ["x", "y", "w", "h"] as const) near(back.crop![k], crop[k]);
  assert.equal(turnCut(newCut(), -1).turns, 3, "turning left from 0 wraps to 3");
  assert.equal(turnCut(turnCut(turnCut(turnCut(newCut(), 1), 1), 1), 1).turns, 0);
  const h = flipCut({ ...newCut(), crop }, "h");
  assert.equal(h.flipH, true); near(h.crop!.x, 1 - 0.1 - 0.3); near(h.crop!.y, 0.2);
  const v = flipCut(flipCut({ ...newCut(), crop }, "v"), "v");
  assert.equal(v.flipV, false); near(v.crop!.y, 0.2);
});

test("choosing an aspect re-fits the crop, Original clears it, Free keeps it inside", () => {
  const c = applyAspect({ ...newCut(), aspect: "1:1" }, 2000, 1000);
  near(ratioOf(c.crop!, 2000, 1000), 1, 1e-9);
  assert.equal(applyAspect({ ...newCut(), aspect: "original", crop: { x: 0.1, y: 0.1, w: 0.5, h: 0.5 } }, 2000, 1000).crop, null);
  const free = applyAspect({ ...newCut(), aspect: "free", angle: 20, crop: { x: 0, y: 0, w: 1, h: 1 } }, 1000, 1000);
  assert.equal(rotatedFits(free.crop!, 1000, 1000, 20), true);
  const turned = applyAspect({ ...newCut(), aspect: "16:9", turns: 1 }, 2000, 1000); // frame is 1000 x 2000 after the turn
  near(ratioOf(turned.crop!, 1000, 2000), 16 / 9, 1e-9);
});
