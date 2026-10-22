export type Point = { x: number; y: number };
export type Bounds = { x: number; y: number; width: number; height: number };
export type Selector = Bounds & { id: string; kind: "rect" | "polygon" | "pen"; points?: Point[] };
export type Handle = "nw" | "n" | "ne" | "e" | "se" | "s" | "sw" | "w" | "center";
export const clamp = (n: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, n));
export function boundsOf(points: Point[]): Bounds {
  const x = Math.min(...points.map(p => p.x)), y = Math.min(...points.map(p => p.y));
  return { x, y, width: Math.max(...points.map(p => p.x)) - x, height: Math.max(...points.map(p => p.y)) - y };
}
export function transformSelector(original: Selector, handle: Handle, dx: number, dy: number, limit: Bounds): Selector {
  let left = original.x, top = original.y, right = left + original.width, bottom = top + original.height;
  if (handle === "center") {
    left = clamp(left + dx, limit.x, limit.x + limit.width - original.width);
    top = clamp(top + dy, limit.y, limit.y + limit.height - original.height);
    right = left + original.width; bottom = top + original.height;
  } else {
    if (handle.includes("w")) left = clamp(left + dx, limit.x, right - 4);
    if (handle.includes("e")) right = clamp(right + dx, left + 4, limit.x + limit.width);
    if (handle.includes("n")) top = clamp(top + dy, limit.y, bottom - 4);
    if (handle.includes("s")) bottom = clamp(bottom + dy, top + 4, limit.y + limit.height);
  }
  const result = { ...original, x: left, y: top, width: right - left, height: bottom - top };
  if (original.points) result.points = original.points.map(p => ({
    x: left + (p.x - original.x) * result.width / original.width,
    y: top + (p.y - original.y) * result.height / original.height,
  }));
  return result;
}
export function splitSelector(selector: Selector, direction: "vertical" | "horizontal", count: number): Selector[] {
  if (selector.kind !== "rect") throw new Error("Straight splits require a rectangle selector.");
  const length = direction === "vertical" ? selector.width : selector.height;
  if (!Number.isInteger(count) || count < 2 || count > 12 || length / count < 4) throw new Error("Choose 2–12 parts, each at least 4 pixels wide or high.");
  return Array.from({ length: count }, (_, index) => {
    const start = Math.round(length * index / count), end = Math.round(length * (index + 1) / count);
    return { ...selector, id: `${selector.id}-${index}`, ...(direction === "vertical"
      ? { x: selector.x + start, width: end - start } : { y: selector.y + start, height: end - start }) };
  });
}
export function validPolygon(points: Point[]): boolean {
  if (points.length < 3 || points.length > 512) return false;
  const cross = (a: Point, b: Point, c: Point) => (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x);
  const area = points.reduce((sum, p, i) => { const q = points[(i + 1) % points.length]; return sum + p.x * q.y - q.x * p.y; }, 0);
  if (Math.abs(area) < 8) return false;
  for (let i = 0; i < points.length; i++) for (let j = i + 2; j < points.length; j++) {
    if (i === 0 && j === points.length - 1) continue;
    const a = points[i], b = points[(i + 1) % points.length], c = points[j], d = points[(j + 1) % points.length];
    if (cross(a, b, c) * cross(a, b, d) <= 0 && cross(c, d, a) * cross(c, d, b) <= 0 &&
      Math.max(Math.min(a.x, b.x), Math.min(c.x, d.x)) <= Math.min(Math.max(a.x, b.x), Math.max(c.x, d.x)) &&
      Math.max(Math.min(a.y, b.y), Math.min(c.y, d.y)) <= Math.min(Math.max(a.y, b.y), Math.max(c.y, d.y))) return false;
  }
  return true;
}
export function panelSelector(panel: Bounds & { id: string; polygon_json?: string | null }): Selector {
  let points: Point[] | undefined;
  try {
    const parsed = JSON.parse(panel.polygon_json || "null");
    if (Array.isArray(parsed)) points = parsed.map(p => Array.isArray(p) ? { x: p[0], y: p[1] } : p);
    if (!points?.every(p => Number.isFinite(p.x) && Number.isFinite(p.y)) || !validPolygon(points)) points = undefined;
  } catch { /* Older rectangular records have no contour. */ }
  return { id: panel.id, x: panel.x, y: panel.y, width: panel.width, height: panel.height, kind: points ? "polygon" : "rect", points };
}
