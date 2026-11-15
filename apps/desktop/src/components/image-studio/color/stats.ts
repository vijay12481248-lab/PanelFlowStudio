import { G } from "./grade";

/** Minimal ImageData shape, so the maths also runs where there is no canvas (tests). */
export interface PixelData {
  data: Uint8ClampedArray;
  width: number;
  height: number;
}

export interface FrameStats {
  mean: number[];
  std: number[];
  p1: number;
  p99: number;
  mid: number[];
  midY: number;
}

export function frameStats(img: PixelData): FrameStats {
  const d = img.data, n = img.width * img.height, L = G.LUMA, ys = new Float32Array(n);
  const sum = [0, 0, 0], sq = [0, 0, 0], midSum = [0, 0, 0];
  let midN = 0, midY = 0;
  for (let i = 0; i < n; i++) {
    const r = d[i * 4] / 255, g = d[i * 4 + 1] / 255, b = d[i * 4 + 2] / 255, y = L[0] * r + L[1] * g + L[2] * b;
    ys[i] = y;
    sum[0] += r; sum[1] += g; sum[2] += b; sq[0] += r * r; sq[1] += g * g; sq[2] += b * b;
    if (y > 0.12 && y < 0.88) { midSum[0] += r; midSum[1] += g; midSum[2] += b; midN++; midY += y; }
  }
  const sorted = Array.from(ys).sort((a, b) => a - b);
  const mean = sum.map((s) => s / n), std = sq.map((s, i) => Math.sqrt(Math.max(1e-8, s / n - mean[i] * mean[i])));
  return {
    mean, std, p1: sorted[Math.floor(n * 0.01)], p99: sorted[Math.floor(n * 0.99)],
    mid: midN > 200 ? midSum.map((s) => s / midN) : mean,
    midY: midN > 200 ? midY / midN : (mean[0] + mean[1] + mean[2]) / 3,
  };
}

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));
const r4 = (x: number) => Math.round(x * 1e4) / 1e4;

/** Auto balance: gray-world on the mid tones plus black and white points, as an ASC CDL (same maths as ChronoFlow's Color page). */
export function autoBalanceCdl(img: PixelData) {
  const s = frameStats(img);
  const gains = s.mid.map((m) => clamp(1 + (s.midY / Math.max(0.02, m) - 1) * 0.8, 0.75, 1.33));
  const lo = Math.min(s.p1, 0.12), hi = Math.max(s.p99, 0.85), ls = clamp(1 / Math.max(0.2, hi - lo), 0.85, 1.35);
  return {
    cdl: { slope: gains.map((g) => r4(g * ls)), offset: [r4(-lo * ls), r4(-lo * ls), r4(-lo * ls)], power: [1, 1, 1] },
    summary: `gains ${gains.map((g) => g.toFixed(2)).join(" / ")}, black ${lo.toFixed(2)}, white ${hi.toFixed(2)}`,
  };
}
