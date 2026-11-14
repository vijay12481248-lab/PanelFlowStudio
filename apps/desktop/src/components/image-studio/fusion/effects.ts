/**
 * The Fusion page's effect stack: glow, vignette, film grain, blur and text, applied in order to the finished picture
 * (after the grade and the cut, so a vignette centres on the final frame and text is placed in it).
 *
 * Parameters are written for a frame 720 pixels high, like ChronoFlow's Fusion page, and scaled by the picture's real height,
 * so a still looks the same at any size. Plain .ts: the default colours are raw values canvas code needs.
 */
import { FG, type FusionNode } from "./fusionGraph";

export type EffectType = "glow" | "vignette" | "grain" | "blur" | "text";

export interface Effect {
  id: string;
  type: EffectType;
  enabled: boolean;
  params: Record<string, any>;
}
export interface FusionState {
  effects: Effect[];
}

export const REF_HEIGHT = 720;
export const MAX_SIDE = 16384;

export const EFFECT_LABELS: Record<EffectType, string> = { glow: "Glow", vignette: "Vignette", grain: "Film grain", blur: "Blur", text: "Text" };

const DEFAULTS: Record<EffectType, () => Record<string, any>> = {
  glow: () => ({ size: 10, intensity: 1.3 }),
  vignette: () => ({ radius: 0.8, softness: 0.5, color: "#000000", opacity: 0.7 }),
  grain: () => ({ intensity: 0.2, size: 1.5, seed: 42 }),
  blur: () => ({ radius: 4 }),
  text: () => ({
    text: "TITLE", fontFamily: "Inter", fontSize: 48, lineSpacing: 1.2, color: "#ffffff", strokeColor: "#000000", strokeWidth: 2,
    glowColor: "#3b6bf5", glowSize: 0, posX: 0.5, posY: 0.85, align: "center", box: false, boxColor: "rgba(5, 8, 22, 0.7)",
  }),
};

export const newFusion = (): FusionState => ({ effects: [] });

let counter = 0;
export function newEffect(type: EffectType): Effect {
  return { id: `fx${Date.now().toString(36)}${(counter++).toString(36)}`, type, enabled: true, params: DEFAULTS[type]() };
}

/** Does this effect change the picture at all? (An empty text or a zero blur is skipped, so Deliver need not bake it.) */
export function changesPicture(e: Effect): boolean {
  if (!e.enabled) return false;
  switch (e.type) {
    case "text": return String(e.params.text || "").trim().length > 0;
    case "blur": return Number(e.params.radius) > 0;
    case "grain": return Number(e.params.intensity) > 0.01;
    case "vignette": return Number(e.params.opacity) > 0;
    default: return true;
  }
}
export const isFusionActive = (f: FusionState | null | undefined): boolean => !!f && f.effects.some(changesPicture);

/** Pixel size scale: parameters are in units of a 720-high frame. */
export const refScale = (height: number) => height / REF_HEIGHT;

const RENDERER: Record<Exclude<EffectType, "grain">, string> = { glow: "glow", vignette: "vignette", blur: "blur", text: "text_plus" };

/** The ChronoFlow node for an effect, with its pixel-sized parameters scaled to a picture of `height` pixels. */
export function scaledNode(e: Effect, height: number): FusionNode {
  const k = refScale(height);
  const p: Record<string, any> = { ...e.params, enabled: true };
  if (e.type === "blur") p.radius = Number(p.radius) * k;
  if (e.type === "glow") p.size = Number(p.size) * k;
  if (e.type === "text") p.glowSize = Number(p.glowSize || 0) * k; // font size and stroke are scaled by the renderer itself
  return { type: RENDERER[e.type as Exclude<EffectType, "grain">], params: p };
}

/**
 * Film grain on RGBA bytes, in place. Luma noise on a grid of `cell` pixels (so a bigger size gives coarser grain), the same
 * amount on all three channels, deterministic for a given seed so the preview and the export are the same picture.
 */
export function grainPixels(data: Uint8ClampedArray, w: number, h: number, amount: number, cell: number, seed: number): void {
  const s = Math.max(1, Math.round(cell));
  const gw = Math.ceil(w / s), gh = Math.ceil(h / s);
  const noise = new Float32Array(gw * gh);
  let rnd = (Math.imul(seed | 0, 1103515245) + 12345) & 0x7fffffff;
  const scale = Math.min(1, Math.max(0, amount)) * 128;
  for (let i = 0; i < noise.length; i++) {
    rnd = (Math.imul(rnd, 1103515245) + 12345) & 0x7fffffff;
    noise[i] = (((rnd >>> 8) & 0xff) / 255 - 0.5) * scale;
  }
  for (let y = 0; y < h; y++) {
    const row = ((y / s) | 0) * gw;
    for (let x = 0; x < w; x++) {
      const n = noise[row + ((x / s) | 0)], i = (y * w + x) * 4;
      data[i] += n; data[i + 1] += n; data[i + 2] += n; // Uint8ClampedArray clamps to 0..255
    }
  }
}

function copyCanvas(src: HTMLCanvasElement): HTMLCanvasElement {
  const c = document.createElement("canvas");
  c.width = src.width;
  c.height = src.height;
  c.getContext("2d")!.drawImage(src, 0, 0);
  return c;
}

/** Run the stack over `src` (left untouched) and return the result. */
export function applyFusion(src: HTMLCanvasElement, effects: Effect[]): HTMLCanvasElement {
  let cur = copyCanvas(src);
  for (const e of effects) {
    if (!changesPicture(e)) continue;
    if (e.type === "grain") {
      const ctx = cur.getContext("2d", { willReadFrequently: true })!;
      const img = ctx.getImageData(0, 0, cur.width, cur.height);
      grainPixels(img.data, cur.width, cur.height, Number(e.params.intensity), Number(e.params.size) * refScale(cur.height), Number(e.params.seed ?? 42));
      ctx.putImageData(img, 0, 0);
      continue;
    }
    const dst = document.createElement("canvas");
    FG.processNode(scaledNode(e, cur.height), cur, dst, 0);
    cur = dst;
  }
  return cur;
}
