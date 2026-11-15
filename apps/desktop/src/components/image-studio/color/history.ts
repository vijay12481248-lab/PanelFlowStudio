/**
 * Undo history for a value that is edited in gestures: the colour grade and the cut. Edits that share a key and come close
 * together (a slider drag) are one step. The names say "grade" for historical reasons; they work for any JSON-like value.
 */
export interface History<T> {
  past: T[];
  present: T;
  future: T[];
  lastKey: string;
  lastAt: number;
}
export type GradeHistory<T = unknown> = History<T>;

export const COALESCE_MS = 700;
const LIMIT = 60;

const copy = <T>(x: T): T => JSON.parse(JSON.stringify(x));

export const startHistory = <T>(value: T): History<T> => ({ past: [], present: value, future: [], lastKey: "", lastAt: 0 });

export function pushGrade<T>(h: History<T>, next: T, key: string, now: number): History<T> {
  const joins = key !== "" && key === h.lastKey && now - h.lastAt < COALESCE_MS;
  const past = joins ? h.past : [...h.past, copy(h.present)].slice(-LIMIT);
  return { past, present: next, future: [], lastKey: key, lastAt: now };
}

export function undoGrade<T>(h: History<T>): History<T> {
  if (!h.past.length) return h;
  return { past: h.past.slice(0, -1), present: h.past[h.past.length - 1], future: [h.present, ...h.future], lastKey: "", lastAt: 0 };
}

export function redoGrade<T>(h: History<T>): History<T> {
  if (!h.future.length) return h;
  return { past: [...h.past, h.present], present: h.future[0], future: h.future.slice(1), lastKey: "", lastAt: 0 };
}
