import React, { useEffect, useRef } from "react";
import { CURVE_H, CURVE_W, WHEEL, curveToPx, drawCurve, drawWheel, wheelPoint, type CurveSpec } from "./canvasDraw";
import type { CurvePoints, Wheel } from "./grade";

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v));

/** A labelled slider with a number box. Double-click the label to reset. */
export const SliderRow: React.FC<{
  label: string;
  value: number;
  min: number;
  max: number;
  step: number;
  def: number;
  digits?: number;
  onChange: (value: number) => void;
}> = ({ label, value, min, max, step, def, digits = 2, onChange }) => (
  <div className="grid grid-cols-[5.5rem_1fr_3.5rem] items-center gap-2">
    <label className="cursor-default truncate text-[11px] text-fg-dim" title="Double-click to reset" onDoubleClick={() => onChange(def)}>
      {label}
    </label>
    <input type="range" min={min} max={max} step={step} value={value} aria-label={label} onChange={(e) => onChange(clamp(Number(e.target.value), min, max))} className="w-full accent-accent" />
    <input
      type="number"
      min={min}
      max={max}
      step={step}
      value={Number(value.toFixed(digits))}
      aria-label={`${label} value`}
      onChange={(e) => {
        const v = Number(e.target.value);
        if (Number.isFinite(v)) onChange(clamp(v, min, max));
      }}
      className="w-full rounded-md border border-edge bg-flat px-1.5 py-0.5 text-right font-mono text-[11px] text-fg focus:border-accent focus:outline-none"
    />
  </div>
);

/** A Resolve-style wheel: drag the puck to push a colour into a tonal range, the slider below is its brightness. */
export const WheelControl: React.FC<{
  title: string;
  wheel: Wheel;
  onChange: (next: Wheel, key: string) => void;
}> = ({ title, wheel, onChange }) => {
  const cv = useRef<HTMLCanvasElement>(null);
  const dragging = useRef(false);
  useEffect(() => {
    if (cv.current) drawWheel(cv.current, wheel);
  }, [wheel.x, wheel.y]);
  const move = (e: React.PointerEvent<HTMLCanvasElement>) => {
    const p = wheelPoint(e.currentTarget.getBoundingClientRect(), e.clientX, e.clientY);
    onChange({ ...wheel, x: p.x, y: p.y }, `w:${title}`);
  };
  return (
    <div className="flex flex-col items-center gap-1">
      <span className="text-[11px] font-medium text-fg-dim">{title}</span>
      <canvas
        ref={cv}
        width={WHEEL}
        height={WHEEL}
        title="Drag the puck. Double-click to reset."
        aria-label={`${title} wheel`}
        className="h-[84px] w-[84px] cursor-crosshair touch-none"
        onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); dragging.current = true; move(e); }}
        onPointerMove={(e) => { if (dragging.current) move(e); }}
        onPointerUp={() => { dragging.current = false; }}
        onDoubleClick={() => onChange({ x: 0, y: 0, m: 0 }, `w:${title}:reset`)}
      />
      <input
        type="range"
        min={-1}
        max={1}
        step={0.005}
        value={wheel.m}
        aria-label={`${title} master`}
        title={`${title} master (brightness of this range)`}
        onChange={(e) => onChange({ ...wheel, m: Number(e.target.value) }, `m:${title}`)}
        onDoubleClick={() => onChange({ ...wheel, m: 0 }, `m:${title}:reset`)}
        className="w-[84px] accent-accent"
      />
    </div>
  );
};

/** A curve: click empty space to add a point, drag to move, double-click or right-click a point to remove it. */
export const CurveEditor: React.FC<{
  spec: CurveSpec;
  points: CurvePoints;
  onChange: (points: CurvePoints, key: string) => void;
  keyName: string;
}> = ({ spec, points, onChange, keyName }) => {
  const cv = useRef<HTMLCanvasElement>(null);
  const drag = useRef(-1);
  useEffect(() => {
    if (cv.current) drawCurve(cv.current, spec, points);
  }, [spec, points]);

  const fromEv = (e: React.PointerEvent | React.MouseEvent): [number, number] => {
    const r = cv.current!.getBoundingClientRect();
    return [clamp((e.clientX - r.left) / r.width, 0, 1), clamp(spec.ymin + (1 - (e.clientY - r.top) / r.height) * (spec.ymax - spec.ymin), spec.ymin, spec.ymax)];
  };
  const nearest = (e: React.PointerEvent | React.MouseEvent) => {
    const r = cv.current!.getBoundingClientRect(), mx = (e.clientX - r.left) * (CURVE_W / r.width), my = (e.clientY - r.top) * (CURVE_H / r.height);
    let best = -1, bd = 12;
    points.forEach((p, i) => {
      const q = curveToPx(spec, p), d = Math.hypot(q[0] - mx, q[1] - my);
      if (d < bd) { bd = d; best = i; }
    });
    return best;
  };
  const r3 = (p: CurvePoints): CurvePoints => p.map((q) => [Math.round(q[0] * 1000) / 1000, Math.round(q[1] * 1000) / 1000]);

  const down = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (e.button !== 0) return;
    e.currentTarget.setPointerCapture(e.pointerId);
    let p = points.map((q) => q.slice() as [number, number]);
    let i = nearest(e);
    if (i < 0) {
      if (!p.length && spec.seed) p = spec.seed.map((x) => [x, 0] as [number, number]);
      const q = fromEv(e);
      p.push(q);
      p.sort((a, b) => a[0] - b[0]);
      i = p.findIndex((x) => x[0] === q[0] && x[1] === q[1]);
      onChange(r3(p), keyName);
    }
    drag.current = i;
  };
  const moveTo = (e: React.PointerEvent<HTMLCanvasElement>) => {
    if (drag.current < 0) return;
    const p = points.map((q) => q.slice() as [number, number]), i = drag.current;
    if (!p[i]) return;
    const q = fromEv(e), last = p.length - 1, fixedX = spec.tone && (i === 0 || i === last);
    p[i] = [fixedX ? p[i][0] : clamp(q[0], i ? p[i - 1][0] + 0.01 : 0, i < last ? p[i + 1][0] - 0.01 : 1), q[1]];
    onChange(r3(p), keyName);
  };
  const remove = (e: React.MouseEvent<HTMLCanvasElement>) => {
    e.preventDefault();
    const i = nearest(e);
    if (i < 0) return;
    if (spec.tone && (points.length <= 2 || i === 0 || i === points.length - 1)) return; // the ends of a tone curve stay
    const p = points.map((q) => q.slice() as [number, number]);
    p.splice(i, 1);
    onChange(r3(p), `${keyName}:remove`);
  };

  return (
    <canvas
      ref={cv}
      width={CURVE_W}
      height={CURVE_H}
      aria-label="Curve editor"
      className="w-full touch-none rounded-lg border border-edge"
      onPointerDown={down}
      onPointerMove={moveTo}
      onPointerUp={() => { drag.current = -1; }}
      onDoubleClick={remove}
      onContextMenu={remove}
    />
  );
};
