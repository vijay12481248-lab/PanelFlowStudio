/** Pure box geometry for the page and panel canvases. Everything is in image pixels. */

export interface Point { x: number; y: number }
export interface Box { x: number; y: number; w: number; h: number }
export interface Size { w: number; h: number }
export type Handle = "n" | "s" | "e" | "w" | "ne" | "nw" | "se" | "sw";

/** The smallest a box may be (the old screen's value), and the smallest a drawn box must exceed. */
export const MIN_SIZE = 30;
export const MIN_DRAW = 20;

const clamp = (n: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, n));

/**
 * A pointer position in image pixels. `rect` is where the image is drawn on screen (from getBoundingClientRect), so this is
 * right at any zoom and however far the image is scrolled. A position off the image is held on its edge.
 */
export function pointToImage(rect: { left: number; top: number; width: number; height: number }, image: Size, client: Point): Point {
  if (rect.width <= 0 || rect.height <= 0) return { x: 0, y: 0 };
  return {
    x: Math.round(clamp(((client.x - rect.left) / rect.width) * image.w, 0, image.w)),
    y: Math.round(clamp(((client.y - rect.top) / rect.height) * image.h, 0, image.h)),
  };
}

/** Keep a box inside the image and at least the minimum size. */
export function clampBox(box: Box, image: Size): Box {
  const w = clamp(box.w, Math.min(MIN_SIZE, image.w), image.w);
  const h = clamp(box.h, Math.min(MIN_SIZE, image.h), image.h);
  return { x: clamp(box.x, 0, image.w - w), y: clamp(box.y, 0, image.h - h), w, h };
}

export function moveBox(start: Box, dx: number, dy: number, image: Size): Box {
  return { ...start, x: clamp(start.x + dx, 0, image.w - start.w), y: clamp(start.y + dy, 0, image.h - start.h) };
}

/**
 * Drag one handle by (dx, dy) from the box as it was when the drag began. An east or south edge stops at the minimum size;
 * a west or north edge that would pass it stays where it was (the old screen's rule).
 */
export function resizeBox(start: Box, handle: Handle, dx: number, dy: number, image: Size): Box {
  let { x, y, w, h } = start;
  if (handle.includes("e")) w = Math.max(MIN_SIZE, Math.min(start.w + dx, image.w - x));
  if (handle.includes("s")) h = Math.max(MIN_SIZE, Math.min(start.h + dy, image.h - y));
  if (handle.includes("w") && start.w - dx > MIN_SIZE) {
    x = Math.max(0, start.x + dx);
    w = Math.min(start.w + (start.x - x), image.w - x);
  }
  if (handle.includes("n") && start.h - dy > MIN_SIZE) {
    y = Math.max(0, start.y + dy);
    h = Math.min(start.h + (start.y - y), image.h - y);
  }
  return { x, y, w, h };
}

/** The box dragged out between two corners, whichever way it was dragged. */
export function drawBox(a: Point, b: Point): Box {
  return { x: Math.min(a.x, b.x), y: Math.min(a.y, b.y), w: Math.abs(a.x - b.x), h: Math.abs(a.y - b.y) };
}

export const isDrawable = (box: Box) => box.w > MIN_DRAW && box.h > MIN_DRAW;

/** An arrow key moves the box; with `resize` it moves the south-east corner instead. */
export function nudgeBox(box: Box, key: "ArrowLeft" | "ArrowRight" | "ArrowUp" | "ArrowDown", step: number, resize: boolean, image: Size): Box {
  const dx = key === "ArrowLeft" ? -step : key === "ArrowRight" ? step : 0;
  const dy = key === "ArrowUp" ? -step : key === "ArrowDown" ? step : 0;
  return clampBox(resize ? { ...box, w: box.w + dx, h: box.h + dy } : { ...box, x: box.x + dx, y: box.y + dy }, image);
}

/** A box as fractions of the image, rounded to four places (the engine's `normalized_*` fields). */
export function normalizeBox(box: Box, image: Size): Box {
  const f = (n: number, of: number) => (of > 0 ? Number((n / of).toFixed(4)) : 0);
  return { x: f(box.x, image.w), y: f(box.y, image.h), w: f(box.w, image.w), h: f(box.h, image.h) };
}

/** The shared area over the smaller box's area: 1 when one box is inside the other, 0 when they do not touch. */
export function boxesOverlap(a: Box, b: Box): number {
  const w = Math.min(a.x + a.w, b.x + b.w) - Math.max(a.x, b.x);
  const h = Math.min(a.y + a.h, b.y + b.h) - Math.max(a.y, b.y);
  const smaller = Math.min(a.w * a.h, b.w * b.h);
  return w > 0 && h > 0 && smaller > 0 ? (w * h) / smaller : 0;
}

/** The id of the smallest box under the point, so a small box inside a big one can still be picked. */
export function hitTest(boxes: Array<Box & { id: string }>, p: Point): string | null {
  let best: (Box & { id: string }) | null = null;
  for (const b of boxes) {
    if (p.x >= b.x && p.x <= b.x + b.w && p.y >= b.y && p.y <= b.y + b.h && (!best || b.w * b.h < best.w * best.h)) best = b;
  }
  return best?.id ?? null;
}
