/**
 * The Cut page's maths: quarter turns, flips, straighten, crop and resize. Pure functions, no canvas.
 *
 * The picture is first oriented (quarter turns, flips), giving a frame of fw x fh pixels. Straighten rotates the content
 * inside that same frame, so its corners go empty; the crop is a rectangle of the frame (0..1 on both axes) that must stay
 * inside the rotated content. The result is cut out of the frame and, if asked, scaled so its long edge has a given size.
 */
export type Turns = 0 | 1 | 2 | 3;
export type AspectId = "free" | "original" | "1:1" | "4:5" | "3:4" | "4:3" | "16:9" | "9:16";
export interface Crop {
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface CutState {
  turns: Turns;
  flipH: boolean;
  flipV: boolean;
  /** Straighten, degrees, positive turns the content clockwise. */
  angle: number;
  /** In frame coordinates 0..1; null means the whole frame (or the whole rotated content when straightened). */
  crop: Crop | null;
  aspect: AspectId;
  /** Scale the result so its longer side has this many pixels; null keeps the cut size. */
  longEdge: number | null;
}

export const ASPECTS: { id: AspectId; label: string }[] = [
  { id: "free", label: "Free" },
  { id: "original", label: "Original" },
  { id: "1:1", label: "1:1" },
  { id: "4:5", label: "4:5" },
  { id: "3:4", label: "3:4" },
  { id: "4:3", label: "4:3" },
  { id: "16:9", label: "16:9" },
  { id: "9:16", label: "9:16" },
];

export const MAX_SIDE = 16384;
const MIN_CROP = 0.04;
const EPS = 1e-6;
const EDGE = 1; // safety margin, in pixels, between a straightened crop and the empty corners

export const newCut = (): CutState => ({ turns: 0, flipH: false, flipV: false, angle: 0, crop: null, aspect: "free", longEdge: null });

export const isCutIdentity = (c: CutState | null | undefined): boolean =>
  !c || (c.turns === 0 && !c.flipH && !c.flipV && c.angle === 0 && c.crop === null && c.longEdge === null);

export const orientedSize = (sw: number, sh: number, turns: Turns): [number, number] => (turns % 2 ? [sh, sw] : [sw, sh]);

/** Width / height of an aspect in pixels; null for a free crop. */
export function aspectRatio(id: AspectId, fw: number, fh: number): number | null {
  if (id === "free") return null;
  if (id === "original") return fw / fh;
  const [a, b] = id.split(":").map(Number);
  return a / b;
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

/** Is every corner of `crop` inside the content after it was rotated by `angle` degrees about the frame's centre? */
export function rotatedFits(crop: Crop, fw: number, fh: number, angle: number): boolean {
  if (angle === 0) return crop.x >= -EPS && crop.y >= -EPS && crop.x + crop.w <= 1 + EPS && crop.y + crop.h <= 1 + EPS;
  const a = (-angle * Math.PI) / 180, cos = Math.cos(a), sin = Math.sin(a), cx = fw / 2, cy = fh / 2;
  const corners: [number, number][] = [[crop.x, crop.y], [crop.x + crop.w, crop.y], [crop.x, crop.y + crop.h], [crop.x + crop.w, crop.y + crop.h]];
  return corners.every(([nx, ny]) => {
    const dx = nx * fw - cx, dy = ny * fh - cy;
    const sx = dx * cos - dy * sin + cx, sy = dx * sin + dy * cos + cy; // back into the unrotated content
    return sx >= EDGE && sx <= fw - EDGE && sy >= EDGE && sy <= fh - EDGE; // a pixel inside, so no edge pixel is half empty
  });
}

/** Shrink `crop` about its own centre (keeping its shape) until it lies inside the rotated content. */
export function fitCropInside(crop: Crop, fw: number, fh: number, angle: number): Crop {
  const cx = crop.x + crop.w / 2, cy = crop.y + crop.h / 2;
  const at = (s: number): Crop => ({ x: cx - (crop.w * s) / 2, y: cy - (crop.h * s) / 2, w: crop.w * s, h: crop.h * s });
  if (rotatedFits(crop, fw, fh, angle)) return crop;
  // the centre itself may be outside after a big rotation: move it towards the middle first
  let lo = 0, hi = 1;
  for (let i = 0; i < 40; i++) {
    const mid = (lo + hi) / 2;
    if (rotatedFits(at(mid), fw, fh, angle)) lo = mid;
    else hi = mid;
  }
  if (lo > 0) return at(lo);
  return fitCropInside({ ...crop, x: 0.5 - crop.w / 2, y: 0.5 - crop.h / 2 }, fw, fh, angle);
}

/** The largest crop of `ratio` (pixel width / height; null = the frame's own shape) that fits the rotated content, centred. */
export function cropForAspect(fw: number, fh: number, angle: number, ratio: number | null): Crop {
  const r = ratio ?? fw / fh;
  // normalized w/h so that the pixel ratio is r
  const nw = Math.min(1, (r * fh) / fw), nh = Math.min(1, fw / (r * fh));
  const base: Crop = { x: (1 - nw) / 2, y: (1 - nh) / 2, w: nw, h: nh };
  return fitCropInside(base, fw, fh, angle);
}

/** The crop in effect: the stored one, or the largest one that fits when the content is straightened. */
export function effectiveCrop(cut: CutState, fw: number, fh: number): Crop {
  if (cut.crop) return cut.crop;
  if (cut.angle === 0) return { x: 0, y: 0, w: 1, h: 1 };
  return cropForAspect(fw, fh, cut.angle, aspectRatio(cut.aspect, fw, fh) ?? null);
}

export interface CutGeometry {
  fw: number;
  fh: number;
  crop: { x: number; y: number; w: number; h: number }; // pixels in the frame
  outW: number;
  outH: number;
}

/** Pixel geometry of the whole cut for a source of sw x sh. */
export function cutGeometry(cut: CutState, sw: number, sh: number): CutGeometry {
  const [fw, fh] = orientedSize(sw, sh, cut.turns);
  const c = effectiveCrop(cut, fw, fh);
  const crop = { x: c.x * fw, y: c.y * fh, w: Math.max(1, c.w * fw), h: Math.max(1, c.h * fh) };
  let scale = 1;
  if (cut.longEdge) scale = cut.longEdge / Math.max(crop.w, crop.h);
  scale = Math.min(scale, MAX_SIDE / Math.max(crop.w, crop.h));
  return { fw, fh, crop, outW: Math.max(1, Math.round(crop.w * scale)), outH: Math.max(1, Math.round(crop.h * scale)) };
}

export type Handle = "move" | "n" | "s" | "e" | "w" | "ne" | "nw" | "se" | "sw";

/**
 * Move or resize a crop by a drag of (dx, dy) in frame units (0..1). With a ratio (normalized width / height) the shape is kept,
 * anchored on the side opposite the handle.
 */
export function dragCrop(start: Crop, handle: Handle, dx: number, dy: number, ratio: number | null): Crop {
  if (handle === "move") {
    return { ...start, x: clamp(start.x + dx, 0, 1 - start.w), y: clamp(start.y + dy, 0, 1 - start.h) };
  }
  let x0 = start.x, y0 = start.y, x1 = start.x + start.w, y1 = start.y + start.h;
  if (handle.includes("w")) x0 = clamp(x0 + dx, 0, x1 - MIN_CROP);
  if (handle.includes("e")) x1 = clamp(x1 + dx, x0 + MIN_CROP, 1);
  if (handle.includes("n")) y0 = clamp(y0 + dy, 0, y1 - MIN_CROP);
  if (handle.includes("s")) y1 = clamp(y1 + dy, y0 + MIN_CROP, 1);
  if (ratio === null) return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };

  // keep the shape: the dragged side(s) decide the size, the opposite side/corner stays put
  const isCorner = handle.length === 2;
  const horizontal = handle === "e" || handle === "w";
  const vertical = handle === "n" || handle === "s";
  let w = x1 - x0, h = y1 - y0;
  if (vertical) w = h * ratio;
  else if (horizontal || Math.abs(dx) * 1 >= Math.abs(dy) * ratio) h = w / ratio;
  else w = h * ratio;
  if (isCorner || horizontal || vertical) {
    // room available from the anchor
    const anchorX = handle.includes("w") ? start.x + start.w : handle.includes("e") ? start.x : start.x + start.w / 2;
    const anchorY = handle.includes("n") ? start.y + start.h : handle.includes("s") ? start.y : start.y + start.h / 2;
    const roomW = handle.includes("w") ? anchorX : handle.includes("e") ? 1 - anchorX : 2 * Math.min(anchorX, 1 - anchorX);
    const roomH = handle.includes("n") ? anchorY : handle.includes("s") ? 1 - anchorY : 2 * Math.min(anchorY, 1 - anchorY);
    const k = Math.min(1, roomW / w, roomH / h);
    w *= k; h *= k;
    if (w < MIN_CROP) { w = MIN_CROP; h = w / ratio; }
    const nx = handle.includes("w") ? anchorX - w : handle.includes("e") ? anchorX : anchorX - w / 2;
    const ny = handle.includes("n") ? anchorY - h : handle.includes("s") ? anchorY : anchorY - h / 2;
    return { x: nx, y: ny, w, h };
  }
  return { x: x0, y: y0, w, h };
}

/** Re-fit the crop to the chosen aspect (after the aspect, the angle or the orientation changed). */
export function applyAspect(cut: CutState, sw: number, sh: number): CutState {
  const [fw, fh] = orientedSize(sw, sh, cut.turns);
  if (cut.aspect === "free") return cut.crop ? { ...cut, crop: fitCropInside(cut.crop, fw, fh, cut.angle) } : cut;
  if (cut.aspect === "original") return { ...cut, crop: null };
  return { ...cut, crop: cropForAspect(fw, fh, cut.angle, aspectRatio(cut.aspect, fw, fh)) };
}

/** A quarter turn (+1 clockwise, -1 anticlockwise); the crop turns with the picture. */
export function turnCut(cut: CutState, dir: 1 | -1): CutState {
  const c = cut.crop;
  const crop = c ? (dir === 1 ? { x: 1 - c.y - c.h, y: c.x, w: c.h, h: c.w } : { x: c.y, y: 1 - c.x - c.w, w: c.h, h: c.w }) : null;
  return { ...cut, turns: (((cut.turns + dir) % 4) + 4) % 4 as Turns, crop };
}

/** Mirror the picture; the crop is mirrored with it. */
export function flipCut(cut: CutState, axis: "h" | "v"): CutState {
  const c = cut.crop;
  const crop = c ? (axis === "h" ? { ...c, x: 1 - c.x - c.w } : { ...c, y: 1 - c.y - c.h }) : null;
  return axis === "h" ? { ...cut, flipH: !cut.flipH, crop } : { ...cut, flipV: !cut.flipV, crop };
}
