import { cloneGrade, type Grade } from "./grade";

/** Undo history of the grade. Edits that share a key and come close together (a slider drag) are one step. */
export interface GradeHistory {
  past: Grade[];
  present: Grade;
  future: Grade[];
  lastKey: string;
  lastAt: number;
}

export const COALESCE_MS = 700;
const LIMIT = 60;

export const startHistory = (g: Grade): GradeHistory => ({ past: [], present: g, future: [], lastKey: "", lastAt: 0 });

export function pushGrade(h: GradeHistory, next: Grade, key: string, now: number): GradeHistory {
  const joins = key !== "" && key === h.lastKey && now - h.lastAt < COALESCE_MS;
  const past = joins ? h.past : [...h.past, cloneGrade(h.present)].slice(-LIMIT);
  return { past, present: next, future: [], lastKey: key, lastAt: now };
}

export function undoGrade(h: GradeHistory): GradeHistory {
  if (!h.past.length) return h;
  return { past: h.past.slice(0, -1), present: h.past[h.past.length - 1], future: [h.present, ...h.future], lastKey: "", lastAt: 0 };
}

export function redoGrade(h: GradeHistory): GradeHistory {
  if (!h.future.length) return h;
  return { past: [...h.past, h.present], present: h.future[0], future: h.future.slice(1), lastKey: "", lastAt: 0 };
}
