import React, { useEffect, useRef } from "react";
import type { CutState } from "../cut/geometry";
import { renderPreview } from "../cut/render";
import type { Effect } from "./effects";

const PREVIEW_EDGE = 1600;

/**
 * The Fusion page's view: the finished picture (grade, cut, then the effects) at screen size. While a text effect is selected,
 * click or drag on the picture to place it.
 */
export const FusionStage: React.FC<{
  bitmap: ImageBitmap | null;
  table: Float32Array | null;
  size: number;
  cut: CutState | null;
  effects: Effect[];
  /** The selected effect, when it is a text effect. */
  text: Effect | null;
  onMoveText: (id: string, x: number, y: number) => void;
  error: string | null;
}> = ({ bitmap, table, size, cut, effects, text, onMoveText, error }) => {
  const canvas = useRef<HTMLCanvasElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  useEffect(() => {
    if (!bitmap || !canvas.current) return;
    const out = renderPreview({ bitmap, table, size, cut, effects }, PREVIEW_EDGE);
    const cv = canvas.current;
    cv.width = out.width;
    cv.height = out.height;
    cv.getContext("2d")!.drawImage(out, 0, 0);
  }, [bitmap, table, size, cut, effects]);

  if (!bitmap) return <p className="text-xs text-fg-dim">{error || "Reading the picture…"}</p>;

  const place = (e: React.PointerEvent) => {
    const r = box.current?.getBoundingClientRect();
    if (!text || !r) return;
    const x = Math.min(1, Math.max(0, (e.clientX - r.left) / r.width)), y = Math.min(1, Math.max(0, (e.clientY - r.top) / r.height));
    onMoveText(text.id, Math.round(x * 1000) / 1000, Math.round(y * 1000) / 1000);
  };

  return (
    <div ref={box} className="relative inline-block touch-none select-none" style={{ lineHeight: 0 }}>
      <canvas ref={canvas} aria-label="Picture with effects" className="max-h-[68vh] max-w-[62vw] rounded-sm border border-edge/80" />
      {text && (
        <div
          role="group"
          aria-label="Text placement"
          className="absolute inset-0 cursor-crosshair"
          onPointerDown={(e) => { e.currentTarget.setPointerCapture(e.pointerId); dragging.current = true; place(e); }}
          onPointerMove={(e) => { if (dragging.current) place(e); }}
          onPointerUp={() => { dragging.current = false; }}
          onPointerCancel={() => { dragging.current = false; }}
        >
          <div
            className="pointer-events-none absolute h-3 w-3 -translate-x-1/2 -translate-y-1/2 rounded-full border-2 border-info bg-ink/60"
            style={{ left: `${Number(text.params.posX) * 100}%`, top: `${Number(text.params.posY) * 100}%` }}
          />
        </div>
      )}
    </div>
  );
};
