import React, { useEffect, useRef, useState } from "react";
import { drawGraded } from "../color/gradeRender";
import { aspectRatio, dragCrop, effectiveCrop, fitCropInside, type CutState, type Crop, type Handle } from "./geometry";
import { drawCut } from "./render";

const PREVIEW_EDGE = 1600;

const HANDLES: { id: Handle; className: string; cursor: string }[] = [
  { id: "nw", className: "left-0 top-0 -translate-x-1/2 -translate-y-1/2", cursor: "nwse-resize" },
  { id: "n", className: "left-1/2 top-0 -translate-x-1/2 -translate-y-1/2", cursor: "ns-resize" },
  { id: "ne", className: "right-0 top-0 translate-x-1/2 -translate-y-1/2", cursor: "nesw-resize" },
  { id: "e", className: "right-0 top-1/2 translate-x-1/2 -translate-y-1/2", cursor: "ew-resize" },
  { id: "se", className: "bottom-0 right-0 translate-x-1/2 translate-y-1/2", cursor: "nwse-resize" },
  { id: "s", className: "bottom-0 left-1/2 -translate-x-1/2 translate-y-1/2", cursor: "ns-resize" },
  { id: "sw", className: "bottom-0 left-0 -translate-x-1/2 translate-y-1/2", cursor: "nesw-resize" },
  { id: "w", className: "left-0 top-1/2 -translate-x-1/2 -translate-y-1/2", cursor: "ew-resize" },
];

/**
 * The Cut page's view: the picture as oriented and straightened (with the grade, if there is one), the crop drawn on top with
 * eight handles, the rest dimmed. Drag inside the crop to move it, a handle to resize; the chosen aspect stays locked.
 */
export const CutStage: React.FC<{
  bitmap: ImageBitmap | null;
  table: Float32Array | null;
  size: number;
  cut: CutState;
  onChange: (next: CutState, key: string) => void;
  error: string | null;
}> = ({ bitmap, table, size, cut, onChange, error }) => {
  const canvas = useRef<HTMLCanvasElement>(null);
  const box = useRef<HTMLDivElement>(null);
  const [frame, setFrame] = useState<{ w: number; h: number } | null>(null);
  const drag = useRef<{ handle: Handle; start: Crop; x: number; y: number } | null>(null);

  // The frame (everything but the crop) is redrawn only when the picture, the grade, or the orientation changes.
  useEffect(() => {
    if (!bitmap || !canvas.current) return;
    let src: ImageBitmap | HTMLCanvasElement = bitmap;
    if (table) {
      const graded = document.createElement("canvas");
      drawGraded(graded, bitmap, table, size, PREVIEW_EDGE);
      src = graded;
    }
    const out = drawCut(src, cut, { frameOnly: true, maxLongEdge: PREVIEW_EDGE });
    const cv = canvas.current;
    cv.width = out.width;
    cv.height = out.height;
    cv.getContext("2d")!.drawImage(out, 0, 0);
    setFrame({ w: out.width, h: out.height });
  }, [bitmap, table, size, cut.turns, cut.flipH, cut.flipV, cut.angle]);

  if (!bitmap) {
    return <p className="text-xs text-fg-dim">{error || "Reading the picture…"}</p>;
  }

  const fw = frame?.w ?? bitmap.width, fh = frame?.h ?? bitmap.height;
  const crop = effectiveCrop(cut, fw, fh);
  const ratioPx = aspectRatio(cut.aspect, fw, fh);
  const ratio = ratioPx === null ? null : (ratioPx * fh) / fw; // normalized width / height

  const down = (handle: Handle) => (e: React.PointerEvent) => {
    e.stopPropagation();
    e.currentTarget.setPointerCapture(e.pointerId);
    drag.current = { handle, start: crop, x: e.clientX, y: e.clientY };
  };
  const move = (e: React.PointerEvent) => {
    const d = drag.current;
    const r = box.current?.getBoundingClientRect();
    if (!d || !r) return;
    const next = dragCrop(d.start, d.handle, (e.clientX - d.x) / r.width, (e.clientY - d.y) / r.height, ratio);
    onChange({ ...cut, crop: fitCropInside(next, fw, fh, cut.angle) }, "crop");
  };
  const up = () => { drag.current = null; };

  return (
    <div ref={box} className="relative inline-block touch-none select-none" style={{ lineHeight: 0 }}>
      <canvas ref={canvas} aria-label="Picture to cut" className="max-h-[68vh] max-w-[62vw] rounded-sm border border-edge/80" />
      <div
        role="group"
        aria-label="Crop"
        className="absolute cursor-move border border-fg/90"
        style={{
          left: `${crop.x * 100}%`,
          top: `${crop.y * 100}%`,
          width: `${crop.w * 100}%`,
          height: `${crop.h * 100}%`,
          boxShadow: "0 0 0 9999px rgba(7, 11, 28, 0.66)", // dims everything outside the crop
        }}
        onPointerDown={down("move")}
        onPointerMove={move}
        onPointerUp={up}
        onPointerCancel={up}
      >
        {/* rule of thirds */}
        <div className="pointer-events-none absolute inset-0">
          <div className="absolute left-1/3 top-0 h-full w-px bg-fg/30" />
          <div className="absolute left-2/3 top-0 h-full w-px bg-fg/30" />
          <div className="absolute left-0 top-1/3 h-px w-full bg-fg/30" />
          <div className="absolute left-0 top-2/3 h-px w-full bg-fg/30" />
        </div>
        {HANDLES.map((h) => (
          <div
            key={h.id}
            aria-label={`Crop handle ${h.id}`}
            className={`absolute h-3 w-3 rounded-sm border border-ink bg-fg ${h.className}`}
            style={{ cursor: h.cursor }}
            onPointerDown={down(h.id)}
            onPointerMove={move}
            onPointerUp={up}
            onPointerCancel={up}
          />
        ))}
      </div>
    </div>
  );
};
