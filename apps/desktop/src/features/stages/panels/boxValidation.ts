import { MIN_SIZE, type Box, type Size } from "../kit/canvas/geometry";

export const BOX_ERROR = `Keep the panel inside the page and at least ${MIN_SIZE} pixels wide and high.`;

/** True when the box lies inside the image and is at least the minimum size. */
export const boxIsValid = (box: Box, image: Size) =>
  [box.x, box.y, box.w, box.h].every(Number.isFinite) && box.x >= 0 && box.y >= 0 && box.w >= MIN_SIZE && box.h >= MIN_SIZE && box.x + box.w <= image.w && box.y + box.h <= image.h;

export const parseBox = (x: string, y: string, w: string, h: string): Box => ({ x: Math.round(Number(x)), y: Math.round(Number(y)), w: Math.round(Number(w)), h: Math.round(Number(h)) });
