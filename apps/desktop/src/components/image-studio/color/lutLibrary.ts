import type { LutLibrary } from "./grade";

const KEY = "imagestudio:luts:v1";

const toB64 = (u8: Uint8Array) => {
  let s = "";
  for (let i = 0; i < u8.length; i += 0x8000) s += String.fromCharCode.apply(null, Array.from(u8.subarray(i, i + 0x8000)));
  return btoa(s);
};

/** Imported .cube LUTs live in this browser, stored as 16-bit tables (same format as ChronoFlow's library). */
export function saveLutLibrary(lib: LutLibrary): boolean {
  try {
    const out: Record<string, { title: string; size: number; data: string }> = {};
    for (const [id, l] of Object.entries(lib)) {
      const u = new Uint16Array(l.table.length);
      for (let i = 0; i < u.length; i++) u[i] = Math.round(Math.min(1, Math.max(0, l.table[i])) * 65535);
      out[id] = { title: l.title, size: l.size, data: toB64(new Uint8Array(u.buffer)) };
    }
    localStorage.setItem(KEY, JSON.stringify(out));
    return true;
  } catch {
    return false; // storage full or blocked: the LUT still works for this session
  }
}

export function loadLutLibrary(): LutLibrary {
  const lib: LutLibrary = {};
  try {
    const raw = JSON.parse(localStorage.getItem(KEY) || "{}");
    for (const [id, l] of Object.entries<any>(raw)) {
      const bin = atob(l.data), u8 = new Uint8Array(bin.length);
      for (let i = 0; i < bin.length; i++) u8[i] = bin.charCodeAt(i);
      const u = new Uint16Array(u8.buffer), t = new Float32Array(u.length);
      for (let i = 0; i < u.length; i++) t[i] = u[i] / 65535;
      lib[id] = { title: l.title, size: l.size, table: t };
    }
  } catch {
    /* no library yet */
  }
  return lib;
}

/** A short id for a LUT's content, so importing the same file twice gives one entry. */
export function lutId(table: Float32Array): string {
  let h = 5381;
  for (let i = 0; i < table.length; i += 7) h = (h * 33 + Math.round(table[i] * 1000)) | 0;
  return `L${(h >>> 0).toString(16)}`;
}
