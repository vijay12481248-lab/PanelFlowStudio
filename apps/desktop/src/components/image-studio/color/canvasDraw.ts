/**
 * Canvas drawing for the Color page: colour wheels, curves and scopes. Ported from ChronoFlow's color.js.
 * Plain .ts on purpose: canvas code cannot use CSS variables, so raw colours live here, not in the .tsx components.
 */
import { G, type CurvePoints, type Wheel } from "./grade";
import type { PixelData } from "./stats";

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

// ---------- colour wheel ----------
export const WHEEL = 120;
const WHEEL_R = 54;
let ring: HTMLCanvasElement | null = null;

function wheelRing(): HTMLCanvasElement {
  if (ring) return ring;
  const cv = document.createElement("canvas");
  cv.width = cv.height = WHEEL;
  const ctx = cv.getContext("2d")!, im = ctx.createImageData(WHEEL, WHEEL);
  for (let y = 0; y < WHEEL; y++) {
    for (let x = 0; x < WHEEL; x++) {
      const dx = x - WHEEL / 2 + 0.5, dy = WHEEL / 2 - y - 0.5, r = Math.hypot(dx, dy) / WHEEL_R;
      if (r > 1) continue;
      const hue = (Math.atan2(dy, dx) / (2 * Math.PI) + 1) % 1, c = G.hsv2rgb(hue, Math.min(1, r) * 0.9, 0.42 + 0.1 * (1 - r)), i = (y * WHEEL + x) * 4;
      im.data[i] = c[0] * 255; im.data[i + 1] = c[1] * 255; im.data[i + 2] = c[2] * 255; im.data[i + 3] = 255;
    }
  }
  ctx.putImageData(im, 0, 0);
  ctx.strokeStyle = "rgba(150,175,255,.4)";
  ctx.beginPath(); ctx.arc(WHEEL / 2, WHEEL / 2, WHEEL_R, 0, 7); ctx.stroke();
  ctx.strokeStyle = "rgba(255,255,255,.12)";
  ctx.beginPath(); ctx.moveTo(WHEEL / 2, 8); ctx.lineTo(WHEEL / 2, WHEEL - 8); ctx.moveTo(8, WHEEL / 2); ctx.lineTo(WHEEL - 8, WHEEL / 2); ctx.stroke();
  return (ring = cv);
}

export function drawWheel(canvas: HTMLCanvasElement, w: Wheel) {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.clearRect(0, 0, WHEEL, WHEEL);
  ctx.drawImage(wheelRing(), 0, 0);
  ctx.fillStyle = "#ffffff";
  ctx.strokeStyle = "#000000";
  ctx.beginPath(); ctx.arc(WHEEL / 2 + w.x * WHEEL_R, WHEEL / 2 - w.y * WHEEL_R, 5, 0, 7); ctx.fill(); ctx.stroke();
}

/** Pointer position on a wheel canvas to a puck position, limited to the ring. */
export function wheelPoint(rect: DOMRect, clientX: number, clientY: number): { x: number; y: number } {
  let x = (((clientX - rect.left) / rect.width) * WHEEL - WHEEL / 2) / WHEEL_R;
  let y = (WHEEL / 2 - ((clientY - rect.top) / rect.height) * WHEEL) / WHEEL_R;
  const len = Math.hypot(x, y);
  if (len > 1) { x /= len; y /= len; }
  return { x: Math.round(x * 1000) / 1000, y: Math.round(y * 1000) / 1000 };
}

// ---------- curve editor ----------
export interface CurveSpec {
  tone: boolean; // true: 0..1 on both axes with a diagonal; false: an offset curve around 0
  ymin: number;
  ymax: number;
  cyclic?: boolean; // hue axis that wraps
  hueBar?: boolean;
  color: string;
  seed?: number[]; // anchors laid down by the first click of an offset curve
}
export const CURVE_W = 300;
export const CURVE_H = 190;

export const curveToPx = (s: CurveSpec, p: [number, number]): [number, number] => [p[0] * CURVE_W, CURVE_H - ((p[1] - s.ymin) / (s.ymax - s.ymin)) * CURVE_H];

export function drawCurve(canvas: HTMLCanvasElement, s: CurveSpec, points: CurvePoints) {
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  const W = CURVE_W, H = CURVE_H;
  ctx.fillStyle = "#080d22";
  ctx.fillRect(0, 0, W, H);
  if (s.hueBar) {
    const g = ctx.createLinearGradient(0, 0, W, 0);
    for (let i = 0; i <= 12; i++) { const c = G.hsv2rgb(i / 12, 0.8, 0.8); g.addColorStop(i / 12, `rgb(${(c[0] * 255) | 0},${(c[1] * 255) | 0},${(c[2] * 255) | 0})`); }
    ctx.fillStyle = g; ctx.globalAlpha = 0.28; ctx.fillRect(0, 0, W, H); ctx.globalAlpha = 1;
  }
  ctx.strokeStyle = "rgba(150,175,255,.14)";
  for (let i = 1; i < 4; i++) { ctx.beginPath(); ctx.moveTo((i * W) / 4, 0); ctx.lineTo((i * W) / 4, H); ctx.moveTo(0, (i * H) / 4); ctx.lineTo(W, (i * H) / 4); ctx.stroke(); }
  if (s.tone) { ctx.strokeStyle = "rgba(255,255,255,.22)"; ctx.beginPath(); ctx.moveTo(0, H); ctx.lineTo(W, 0); ctx.stroke(); }
  else { const z = curveToPx(s, [0, 0])[1]; ctx.strokeStyle = "rgba(255,255,255,.3)"; ctx.beginPath(); ctx.moveTo(0, z); ctx.lineTo(W, z); ctx.stroke(); }
  const f = G.curveFn(points, s.cyclic, s.tone ? undefined : () => 0);
  ctx.strokeStyle = s.color; ctx.lineWidth = 2; ctx.beginPath();
  for (let x = 0; x <= W; x += 2) { const q = curveToPx(s, [x / W, clamp(f(x / W), s.ymin, s.ymax)]); if (x) ctx.lineTo(q[0], q[1]); else ctx.moveTo(q[0], q[1]); }
  ctx.stroke(); ctx.lineWidth = 1;
  for (const pt of points) { const q = curveToPx(s, pt); ctx.fillStyle = "#ffffff"; ctx.strokeStyle = "#000000"; ctx.beginPath(); ctx.arc(q[0], q[1], 4.5, 0, 7); ctx.fill(); ctx.stroke(); }
}

// ---------- scopes ----------
export type ScopeKind = "waveform" | "parade" | "vector" | "histogram";
export const SCOPE_SIZE: Record<ScopeKind, [number, number]> = { waveform: [256, 128], parade: [256, 128], vector: [200, 200], histogram: [256, 100] };

const inten = (c: number) => Math.min(255, Math.sqrt(c) * 70);
const GRATICULE = "rgba(150,175,255,.22)";

function paint(cv: HTMLCanvasElement, w: number, h: number, fn: (p: number) => number[], extra?: (ctx: CanvasRenderingContext2D) => void) {
  cv.width = w; cv.height = h;
  const ctx = cv.getContext("2d")!, im = ctx.createImageData(w, h);
  for (let p = 0; p < w * h; p++) { const c = fn(p); im.data[p * 4] = c[0]; im.data[p * 4 + 1] = c[1]; im.data[p * 4 + 2] = c[2]; im.data[p * 4 + 3] = 255; }
  ctx.putImageData(im, 0, 0);
  extra?.(ctx);
}

/** Draw one scope of `img` (already graded) onto `cv`. */
export function drawScope(kind: ScopeKind, cv: HTMLCanvasElement, img: PixelData) {
  const [W, H] = SCOPE_SIZE[kind];
  const d = img.data, n = img.width * img.height, L = G.LUMA;
  if (kind === "histogram") {
    cv.width = W; cv.height = H;
    const hist = [new Uint32Array(256), new Uint32Array(256), new Uint32Array(256), new Uint32Array(256)];
    for (let i = 0; i < n; i++) { const r = d[i * 4], g = d[i * 4 + 1], b = d[i * 4 + 2]; hist[0][r]++; hist[1][g]++; hist[2][b]++; hist[3][Math.round(L[0] * r + L[1] * g + L[2] * b)]++; }
    const hx = cv.getContext("2d")!;
    hx.fillStyle = "#060918"; hx.fillRect(0, 0, W, H);
    let mx = 1;
    for (let k = 0; k < 4; k++) for (let i = 2; i < 254; i++) mx = Math.max(mx, hist[k][i]);
    hx.globalCompositeOperation = "lighter";
    ([["#ff3b4a", 0], ["#2bd96b", 1], ["#3b7bff", 2]] as const).forEach(([col, k]) => {
      hx.fillStyle = col; hx.globalAlpha = 0.55;
      for (let i = 0; i < 256; i++) { const bh = Math.min(1, hist[k][i] / mx) * (H - 2); hx.fillRect(i, H - bh, 1, bh); }
    });
    hx.globalAlpha = 1; hx.fillStyle = "rgba(255,255,255,.55)";
    for (let i = 0; i < 256; i++) { const bh = Math.min(1, hist[3][i] / mx) * (H - 2); hx.fillRect(i, H - bh, 1, 1.5); }
    hx.globalCompositeOperation = "source-over";
    return;
  }
  if (kind === "vector") {
    const vec = new Uint16Array(200 * 200);
    for (let i = 0; i < n; i++) {
      const r = d[i * 4], g = d[i * 4 + 1], b = d[i * 4 + 2], y = L[0] * r + L[1] * g + L[2] * b;
      const cb = (b - y) / 255 / 1.8556, cr = (r - y) / 255 / 1.5748, vx = Math.round(100 + cb * 190), vy = Math.round(100 - cr * 190);
      if (vx >= 0 && vx < 200 && vy >= 0 && vy < 200) vec[vy * 200 + vx]++;
    }
    paint(cv, 200, 200, (p) => { const v = inten(vec[p] * 3); return [v * 0.7, v, v * 0.9]; }, (ctx) => {
      ctx.strokeStyle = "rgba(150,175,255,.28)";
      ctx.beginPath(); ctx.arc(100, 100, 95, 0, Math.PI * 2); ctx.stroke(); ctx.beginPath(); ctx.arc(100, 100, 47, 0, Math.PI * 2); ctx.stroke();
      ctx.beginPath(); ctx.moveTo(100, 5); ctx.lineTo(100, 195); ctx.moveTo(5, 100); ctx.lineTo(195, 100); ctx.stroke();
      ([["R", 1, 0, 0], ["Y", 1, 1, 0], ["G", 0, 1, 0], ["C", 0, 1, 1], ["B", 0, 0, 1], ["M", 1, 0, 1]] as const).forEach(([nm, r, g, b]) => {
        const y = L[0] * r + L[1] * g + L[2] * b, cb = (b - y) / 1.8556, cr = (r - y) / 1.5748, x = 100 + cb * 190, yy = 100 - cr * 190;
        ctx.strokeStyle = `rgb(${r * 255},${g * 255},${b * 255})`; ctx.strokeRect(x - 5, yy - 5, 10, 10);
        ctx.fillStyle = "#ffffff"; ctx.font = "9px monospace"; ctx.fillText(nm, x + 7, yy + 3);
      });
      const sy = L[0] + L[1] * 0.75 + L[2] * 0.55, scb = (0.55 - sy) / 1.8556, scr = (1 - sy) / 1.5748, ang = Math.atan2(scr, scb); // skin-tone line
      ctx.strokeStyle = "rgba(255,200,140,.7)"; ctx.beginPath(); ctx.moveTo(100, 100); ctx.lineTo(100 + Math.cos(ang) * 95, 100 - Math.sin(ang) * 95); ctx.stroke();
    });
    return;
  }
  // waveform and parade
  const wf = new Uint16Array(W * H), pr = new Uint16Array(W * H * 3);
  for (let i = 0; i < n; i++) {
    const r = d[i * 4], g = d[i * 4 + 1], b = d[i * 4 + 2], x = i % img.width, y = L[0] * r + L[1] * g + L[2] * b;
    const wx = Math.floor((x * W) / img.width), px = Math.floor((x * (W / 3)) / img.width);
    wf[(H - 1 - Math.round((y / 255) * (H - 1))) * W + wx]++;
    pr[(H - 1 - Math.round((r / 255) * (H - 1))) * W + px]++;
    pr[W * H + (H - 1 - Math.round((g / 255) * (H - 1))) * W + px + 86]++;
    pr[2 * W * H + (H - 1 - Math.round((b / 255) * (H - 1))) * W + px + 171]++;
  }
  const lines = (ctx: CanvasRenderingContext2D) => {
    ctx.strokeStyle = GRATICULE; ctx.fillStyle = "rgba(150,175,255,.6)"; ctx.font = "9px monospace";
    [0, 25, 50, 75, 100].forEach((p) => { const y = Math.round((1 - p / 100) * (H - 1)) + 0.5; ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(W, y); ctx.stroke(); ctx.fillText(String(p), 2, Math.min(H - 2, Math.max(9, y - 1))); });
  };
  if (kind === "waveform") paint(cv, W, H, (p) => { const v = inten(wf[p]); return [v * 0.35, v, v * 0.55]; }, lines);
  else paint(cv, W, H, (p) => [inten(pr[p]), inten(pr[W * H + p]), inten(pr[2 * W * H + p])], (ctx) => {
    lines(ctx); ctx.strokeStyle = "rgba(255,255,255,.15)";
    [86, 171].forEach((x) => { ctx.beginPath(); ctx.moveTo(x + 0.5, 0); ctx.lineTo(x + 0.5, H); ctx.stroke(); });
  });
}

export const TONE_COLORS: Record<"y" | "r" | "g" | "b", string> = { y: "#e6ebff", r: "#ff5a68", g: "#3be07a", b: "#5a8cff" };
export const HUE_CURVE_COLOR = "#e6ebff";
