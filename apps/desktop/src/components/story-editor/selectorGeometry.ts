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

export function convertRectToPolygon(selector: Selector): Selector {
  const points: Point[] = [
    { x: Math.round(selector.x), y: Math.round(selector.y) },
    { x: Math.round(selector.x + selector.width), y: Math.round(selector.y) },
    { x: Math.round(selector.x + selector.width), y: Math.round(selector.y + selector.height) },
    { x: Math.round(selector.x), y: Math.round(selector.y + selector.height) },
  ];
  return {
    ...selector,
    kind: "polygon",
    points,
  };
}

export function convertPolygonToRect(selector: Selector): Selector {
  const bounds = selector.points && selector.points.length >= 3 ? boundsOf(selector.points) : selector;
  return {
    ...selector,
    x: bounds.x,
    y: bounds.y,
    width: bounds.width,
    height: bounds.height,
    kind: "rect",
    points: undefined,
  };
}

export function addVertexToPolygon(selector: Selector, targetIndex?: number, point?: Point): Selector {
  const current = selector.kind !== "polygon" || !selector.points ? convertRectToPolygon(selector) : selector;
  const pts = [...(current.points || [])];
  if (pts.length < 3) return selector;

  if (point && targetIndex !== undefined && targetIndex >= 0 && targetIndex <= pts.length) {
    pts.splice(targetIndex, 0, point);
  } else if (targetIndex !== undefined && targetIndex >= 0 && targetIndex < pts.length) {
    const p1 = pts[targetIndex];
    const p2 = pts[(targetIndex + 1) % pts.length];
    const midPoint: Point = {
      x: Math.round((p1.x + p2.x) / 2),
      y: Math.round((p1.y + p2.y) / 2),
    };
    pts.splice(targetIndex + 1, 0, midPoint);
  } else {
    let maxDist = -1;
    let bestIndex = 0;
    for (let i = 0; i < pts.length; i++) {
      const p1 = pts[i];
      const p2 = pts[(i + 1) % pts.length];
      const dist = Math.hypot(p2.x - p1.x, p2.y - p1.y);
      if (dist > maxDist) {
        maxDist = dist;
        bestIndex = i;
      }
    }
    const p1 = pts[bestIndex];
    const p2 = pts[(bestIndex + 1) % pts.length];
    const midPoint: Point = {
      x: Math.round((p1.x + p2.x) / 2),
      y: Math.round((p1.y + p2.y) / 2),
    };
    pts.splice(bestIndex + 1, 0, midPoint);
  }

  const bounds = boundsOf(pts);
  return {
    ...current,
    ...bounds,
    kind: "polygon",
    points: pts,
  };
}

export function removeVertexFromPolygon(selector: Selector, index: number): Selector {
  if (!selector.points || selector.points.length <= 3) return selector;
  if (index < 0 || index >= selector.points.length) return selector;
  const pts = selector.points.filter((_, i) => i !== index);
  const bounds = boundsOf(pts);
  return {
    ...selector,
    ...bounds,
    points: pts,
  };
}

export function insertVertexAlongEdge(selector: Selector, clickPoint: Point): { selector: Selector; insertedIndex: number } | null {
  const current = selector.kind !== "polygon" || !selector.points ? convertRectToPolygon(selector) : selector;
  const pts = [...(current.points || [])];
  if (pts.length < 3) return null;

  let minDist = Infinity;
  let bestIndex = -1;
  let bestPoint = clickPoint;

  for (let i = 0; i < pts.length; i++) {
    const a = pts[i];
    const b = pts[(i + 1) % pts.length];
    const abx = b.x - a.x;
    const aby = b.y - a.y;
    const lenSq = abx * abx + aby * aby;
    if (lenSq === 0) continue;
    const apx = clickPoint.x - a.x;
    const apy = clickPoint.y - a.y;
    const t = clamp((apx * abx + apy * aby) / lenSq, 0, 1);
    const projX = a.x + t * abx;
    const projY = a.y + t * aby;
    const dist = Math.hypot(clickPoint.x - projX, clickPoint.y - projY);
    if (dist < minDist) {
      minDist = dist;
      bestIndex = i;
      bestPoint = { x: Math.round(projX), y: Math.round(projY) };
    }
  }

  if (bestIndex === -1) return null;
  const insertAt = bestIndex + 1;
  pts.splice(insertAt, 0, bestPoint);
  const bounds = boundsOf(pts);
  return {
    selector: {
      ...current,
      ...bounds,
      kind: "polygon",
      points: pts,
    },
    insertedIndex: insertAt,
  };
}
