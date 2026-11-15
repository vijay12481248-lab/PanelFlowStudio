/**
 * The colour grade of a picture. The maths is ChronoFlow's own `grade.js` (pure, unit-tested in tests/js/chronoflow_grade.test.js),
 * imported unchanged so a still looks exactly as it would in the video: a serial stack of nodes baked into one 33^3 LUT.
 */
import * as gradeModule from "../../../../../../engine/chronoflow/static/nle/grade.js";

export interface Wheel {
  x: number;
  y: number;
  m: number;
}
export type CurvePoints = [number, number][];
export type WheelKey = "lift" | "gamma" | "gain" | "offset";
export type ToneKey = "y" | "r" | "g" | "b";
export type HueCurveKey = "hueVsHue" | "hueVsSat" | "hueVsLum" | "lumVsSat";

export interface GradeNode {
  id: string;
  label: string;
  enabled: boolean;
  cdl: { slope: number[]; offset: number[]; power: number[] };
  lift: Wheel;
  gamma: Wheel;
  gain: Wheel;
  offset: Wheel;
  contrast: number;
  pivot: number;
  saturation: number;
  hue: number;
  temp: number;
  tint: number;
  boost: number;
  shadows: number;
  highlights: number;
  curves: Record<ToneKey, CurvePoints>;
  hueVsHue: CurvePoints;
  hueVsSat: CurvePoints;
  hueVsLum: CurvePoints;
  lumVsSat: CurvePoints;
  lut: { id: string; strength: number } | null;
}

export interface Grade {
  v: number;
  on: boolean;
  nodes: GradeNode[];
}

/** An imported .cube LUT: a size^3 table of RGB floats, red fastest. */
export interface LutEntry {
  title: string;
  size: number;
  table: Float32Array;
}
export type LutLibrary = Record<string, LutEntry>;

interface GradeApi {
  LUT_SIZE: number;
  LUMA: number[];
  newNode(label?: string): GradeNode;
  newGrade(): Grade;
  curveFn(points: CurvePoints, cyclic?: boolean, fallback?: (x: number) => number): (x: number) => number;
  tone0(): CurvePoints;
  wheelRgb(w: Wheel): number[];
  hsv2rgb(h: number, s: number, v: number): number[];
  bake(grade: Grade, size: number, lib?: LutLibrary): Float32Array;
  parseCube(text: string): LutEntry;
  isIdentity(grade: Grade | null | undefined): boolean;
  activeNodes(grade: Grade | null | undefined): GradeNode[];
  applyToPixels(data: Uint8ClampedArray, table: Float32Array, size: number): Uint8ClampedArray;
}

// In the browser the file sets globalThis.NLEGrade; under Node (tests) it is a CommonJS module.
export const G: GradeApi = (globalThis as any).NLEGrade ?? (gradeModule as any).default ?? (gradeModule as any);

export const cloneGrade = (g: Grade): Grade => JSON.parse(JSON.stringify(g));
export const isNeutral = (g: Grade | null | undefined): boolean => G.isIdentity(g);

/** Same grade, same table: the key a baked table is cached under (imported LUTs count by id). */
export function gradeSignature(g: Grade): string {
  return JSON.stringify(g) + G.activeNodes(g).map((n) => (n.lut ? n.lut.id : "")).join(",");
}

export const round3 = (x: number) => Math.round(x * 1000) / 1000;
