import { drawGraded } from "../color/gradeRender";
import { cutGeometry, isCutIdentity, type CutState } from "./geometry";

export type Source = ImageBitmap | HTMLCanvasElement;

const sizeOf = (s: Source): [number, number] => [s.width, s.height];

/**
 * Draw `src` through the cut: orient (quarter turns, flips), straighten about the frame's centre, cut out the crop, scale.
 * `frameOnly` keeps the whole frame (the Cut page's preview, where the crop is drawn on top); `maxLongEdge` bounds the size.
 */
export function drawCut(src: Source, cut: CutState, opts: { frameOnly?: boolean; maxLongEdge?: number } = {}): HTMLCanvasElement {
  const [sw, sh] = sizeOf(src);
  const g = cutGeometry(opts.frameOnly ? { ...cut, crop: { x: 0, y: 0, w: 1, h: 1 }, longEdge: null } : cut, sw, sh);
  let scale = g.outW / g.crop.w;
  if (opts.maxLongEdge) scale = Math.min(scale, opts.maxLongEdge / Math.max(g.crop.w, g.crop.h));
  const out = document.createElement("canvas");
  out.width = Math.max(1, Math.round(g.crop.w * scale));
  out.height = Math.max(1, Math.round(g.crop.h * scale));
  const ctx = out.getContext("2d");
  if (!ctx) throw new Error("Canvas is not available");
  ctx.imageSmoothingQuality = "high";
  // Transforms apply to what is drawn last-to-first: orient the source, straighten in the frame, move the crop to the origin, scale.
  ctx.scale(out.width / g.crop.w, out.height / g.crop.h);
  ctx.translate(-g.crop.x, -g.crop.y);
  ctx.translate(g.fw / 2, g.fh / 2);
  ctx.rotate((cut.angle * Math.PI) / 180);
  ctx.translate(-g.fw / 2, -g.fh / 2);
  ctx.translate(g.fw / 2, g.fh / 2);
  ctx.rotate((cut.turns * Math.PI) / 2);
  ctx.scale(cut.flipH ? -1 : 1, cut.flipV ? -1 : 1);
  ctx.translate(-sw / 2, -sh / 2);
  ctx.drawImage(src, 0, 0);
  return out;
}

export interface EditedPicture {
  bitmap: ImageBitmap;
  /** The baked grade table, or null when there is no grade. */
  table: Float32Array | null;
  size: number;
  /** The cut, or null when there is none. */
  cut: CutState | null;
}

/** The picture with the grade applied first (at full size), then cut: what Deliver exports and saves. */
export function renderEdited(p: EditedPicture): HTMLCanvasElement {
  let src: Source = p.bitmap;
  if (p.table) {
    const graded = document.createElement("canvas");
    drawGraded(graded, p.bitmap, p.table, p.size, Number.MAX_SAFE_INTEGER);
    src = graded;
  }
  if (p.cut && !isCutIdentity(p.cut)) return drawCut(src, p.cut);
  if (src instanceof HTMLCanvasElement) return src;
  const plain = document.createElement("canvas");
  plain.width = p.bitmap.width;
  plain.height = p.bitmap.height;
  plain.getContext("2d")!.drawImage(p.bitmap, 0, 0);
  return plain;
}

export async function renderEditedBlob(p: EditedPicture, mime: string, quality = 0.92): Promise<Blob> {
  let canvas = renderEdited(p);
  if (mime === "image/jpeg") {
    // JPG has no transparency: straightened corners, if any, become white rather than black
    const flat = document.createElement("canvas");
    flat.width = canvas.width;
    flat.height = canvas.height;
    const ctx = flat.getContext("2d")!;
    ctx.fillStyle = "white";
    ctx.fillRect(0, 0, flat.width, flat.height);
    ctx.drawImage(canvas, 0, 0);
    canvas = flat;
  }
  return new Promise<Blob>((resolve, reject) =>
    canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("Could not encode the edited picture."))), mime, quality),
  );
}
