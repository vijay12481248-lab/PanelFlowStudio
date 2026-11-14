import test from "node:test";
import assert from "node:assert/strict";
import { MIN_DRAW, MIN_SIZE, boxesOverlap, clampBox, drawBox, hitTest, isDrawable, moveBox, normalizeBox, nudgeBox, pointToImage, resizeBox, type Box, type Handle } from "../geometry";

const IMG = { w: 1000, h: 2000 };
const box = (x: number, y: number, w: number, h: number): Box => ({ x, y, w, h });

test("a pointer maps to image pixels at any zoom, even when the image is scrolled partly out of view", () => {
  // 100%: the image is drawn 1000 x 2000 at (100, 50)
  assert.deepEqual(pointToImage({ left: 100, top: 50, width: 1000, height: 2000 }, IMG, { x: 350, y: 250 }), { x: 250, y: 200 });
  // 25%: drawn 250 x 500; the same screen distance is four times as far in the image
  assert.deepEqual(pointToImage({ left: 100, top: 50, width: 250, height: 500 }, IMG, { x: 150, y: 100 }), { x: 200, y: 200 });
  // 400%: drawn 4000 x 8000, scrolled so its top-left is off screen
  assert.deepEqual(pointToImage({ left: -1200, top: -3000, width: 4000, height: 8000 }, IMG, { x: 400, y: 1000 }), { x: 400, y: 1000 });
  // a very tall strip: 1920 x 22528 drawn at 10%
  assert.deepEqual(pointToImage({ left: 0, top: 0, width: 192, height: 2252.8 }, { w: 1920, h: 22528 }, { x: 96, y: 1126.4 }), { x: 960, y: 11264 });
});

test("a pointer outside the image is held on its edge, and a zero-size rectangle does not divide by zero", () => {
  assert.deepEqual(pointToImage({ left: 0, top: 0, width: 1000, height: 2000 }, IMG, { x: -50, y: 99999 }), { x: 0, y: 2000 });
  assert.deepEqual(pointToImage({ left: 0, top: 0, width: 0, height: 0 }, IMG, { x: 10, y: 10 }), { x: 0, y: 0 });
});

test("a box is kept inside the image and at least the minimum size", () => {
  assert.deepEqual(clampBox(box(-20, -30, 400, 400), IMG), box(0, 0, 400, 400));
  assert.deepEqual(clampBox(box(900, 1900, 400, 400), IMG), box(600, 1600, 400, 400));
  assert.deepEqual(clampBox(box(10, 10, 5, 5), IMG), box(10, 10, MIN_SIZE, MIN_SIZE));
  assert.deepEqual(clampBox(box(0, 0, 5000, 5000), IMG), box(0, 0, 1000, 2000));
});

test("moving stops at every edge", () => {
  const start = box(100, 100, 300, 200);
  assert.deepEqual(moveBox(start, 50, 25, IMG), box(150, 125, 300, 200));
  assert.deepEqual(moveBox(start, -500, -500, IMG), box(0, 0, 300, 200));
  assert.deepEqual(moveBox(start, 5000, 5000, IMG), box(700, 1800, 300, 200));
});

const START = box(200, 300, 400, 500);
const resize = (handle: Handle, dx: number, dy: number) => resizeBox(START, handle, dx, dy, IMG);

test("each handle resizes only its own edges", () => {
  assert.deepEqual(resize("e", 50, 999), box(200, 300, 450, 500));
  assert.deepEqual(resize("s", 999, 60), box(200, 300, 400, 560));
  assert.deepEqual(resize("w", -50, 999), box(150, 300, 450, 500));
  assert.deepEqual(resize("n", 999, -40), box(200, 260, 400, 540));
  assert.deepEqual(resize("se", 10, 20), box(200, 300, 410, 520));
  assert.deepEqual(resize("nw", -10, -20), box(190, 280, 410, 520));
  assert.deepEqual(resize("ne", 10, -20), box(200, 280, 410, 520));
  assert.deepEqual(resize("sw", -10, 20), box(190, 300, 410, 520));
});

test("resizing never leaves the image", () => {
  assert.deepEqual(resize("e", 5000, 0), box(200, 300, 800, 500));
  assert.deepEqual(resize("s", 0, 5000), box(200, 300, 400, 1700));
  assert.deepEqual(resize("w", -5000, 0), box(0, 300, 600, 500));
  assert.deepEqual(resize("n", 0, -5000), box(200, 0, 400, 800));
});

test("an east or south edge never shrinks the box below the minimum; a west or north edge that would stays where it was", () => {
  assert.deepEqual(resize("e", -5000, 0), box(200, 300, MIN_SIZE, 500));
  assert.deepEqual(resize("s", 0, -5000), box(200, 300, 400, MIN_SIZE));
  assert.deepEqual(resize("w", 390, 0), START, "shrinking from the west past the minimum is ignored");
  assert.deepEqual(resize("n", 0, 490), START, "shrinking from the north past the minimum is ignored");
  assert.deepEqual(resize("w", 300, 0), box(500, 300, 100, 500), "shrinking from the west within the limit works");
});

test("a drag draws the same box from any corner", () => {
  assert.deepEqual(drawBox({ x: 100, y: 100 }, { x: 300, y: 250 }), box(100, 100, 200, 150));
  assert.deepEqual(drawBox({ x: 300, y: 250 }, { x: 100, y: 100 }), box(100, 100, 200, 150));
  assert.deepEqual(drawBox({ x: 300, y: 100 }, { x: 100, y: 250 }), box(100, 100, 200, 150));
});

test("only boxes bigger than the minimum draw size can be drawn", () => {
  assert.equal(isDrawable(box(0, 0, MIN_DRAW + 1, MIN_DRAW + 1)), true);
  assert.equal(isDrawable(box(0, 0, MIN_DRAW, 100)), false);
  assert.equal(isDrawable(box(0, 0, 100, MIN_DRAW)), false);
  assert.equal(isDrawable(box(0, 0, 0, 0)), false);
});

test("arrow keys move the box and shifted arrows resize its south-east corner, inside the image", () => {
  const b = box(100, 100, 300, 200);
  assert.deepEqual(nudgeBox(b, "ArrowRight", 10, false, IMG), box(110, 100, 300, 200));
  assert.deepEqual(nudgeBox(b, "ArrowLeft", 10, false, IMG), box(90, 100, 300, 200));
  assert.deepEqual(nudgeBox(b, "ArrowDown", 10, false, IMG), box(100, 110, 300, 200));
  assert.deepEqual(nudgeBox(b, "ArrowUp", 10, false, IMG), box(100, 90, 300, 200));
  assert.deepEqual(nudgeBox(b, "ArrowRight", 10, true, IMG), box(100, 100, 310, 200));
  assert.deepEqual(nudgeBox(b, "ArrowLeft", 10, true, IMG), box(100, 100, 290, 200));
  assert.deepEqual(nudgeBox(b, "ArrowDown", 10, true, IMG), box(100, 100, 300, 210));
  assert.deepEqual(nudgeBox(b, "ArrowUp", 10, true, IMG), box(100, 100, 300, 190));
  assert.deepEqual(nudgeBox(box(0, 0, 300, 200), "ArrowLeft", 10, false, IMG), box(0, 0, 300, 200), "held at the edge");
  assert.deepEqual(nudgeBox(box(100, 100, MIN_SIZE, MIN_SIZE), "ArrowLeft", 10, true, IMG), box(100, 100, MIN_SIZE, MIN_SIZE), "held at the minimum");
});

test("a box is normalised to fractions of the image, rounded to four places", () => {
  assert.deepEqual(normalizeBox(box(100, 500, 250, 1000), IMG), { x: 0.1, y: 0.25, w: 0.25, h: 0.5 });
  assert.deepEqual(normalizeBox(box(1, 1, 1, 1), { w: 3, h: 3 }), { x: 0.3333, y: 0.3333, w: 0.3333, h: 0.3333 });
});

test("overlap is the shared area over the smaller box", () => {
  assert.equal(boxesOverlap(box(0, 0, 100, 100), box(0, 0, 100, 100)), 1);
  assert.equal(boxesOverlap(box(0, 0, 100, 100), box(20, 20, 40, 40)), 1, "a box inside another overlaps completely");
  assert.equal(boxesOverlap(box(0, 0, 100, 100), box(200, 200, 50, 50)), 0);
  assert.equal(boxesOverlap(box(0, 0, 100, 100), box(50, 0, 100, 100)), 0.5);
  assert.equal(boxesOverlap(box(0, 0, 0, 0), box(0, 0, 10, 10)), 0);
});

test("the smallest box under the pointer is chosen, so a small box inside a big one stays reachable", () => {
  const boxes = [{ id: "big", ...box(0, 0, 500, 500) }, { id: "small", ...box(100, 100, 50, 50) }, { id: "far", ...box(800, 800, 100, 100) }];
  assert.equal(hitTest(boxes, { x: 120, y: 120 }), "small");
  assert.equal(hitTest(boxes, { x: 300, y: 300 }), "big");
  assert.equal(hitTest(boxes, { x: 850, y: 850 }), "far");
  assert.equal(hitTest(boxes, { x: 700, y: 100 }), null);
});
