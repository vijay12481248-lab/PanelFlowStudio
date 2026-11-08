import React from "react";
import { Button } from "@panelflow/ui-v2";
import type { Box, Handle } from "./geometry";
import { useCanvasInteraction, type CanvasBox } from "./useCanvasInteraction";

export type { CanvasBox } from "./useCanvasInteraction";

export interface PageCanvasProps {
  image: { src: string; width: number; height: number; alt: string };
  boxes: CanvasBox[];
  selectedId: string | null;
  onSelect: (id: string | null, additive: boolean) => void;
  onChange?: (id: string, box: Box) => void;
  onCommit?: (id: string, box: Box, previous: Box) => void;
  onDraw?: (box: Box) => void;
  /** The image's own size once it has loaded (box coordinates are in this space). */
  onImageSize?: (width: number, height: number) => void;
  drawMode?: boolean;
  showBoxes?: boolean;
  /** Percent: 100 draws the image at its own size. */
  zoom: number;
  editable?: boolean;
  className?: string;
  /** What the fallback says when the image cannot load. */
  unavailableLabel?: string;
}

const TONE: Record<CanvasBox["tone"], string> = {
  accent: "stroke-accent fill-accent/10",
  ok: "stroke-ok fill-ok/10",
  warn: "stroke-warn fill-warn/10",
  bad: "stroke-bad fill-bad/10",
  neutral: "stroke-fg-dim fill-fg/5",
};
const HANDLES: Array<{ handle: Handle; fx: number; fy: number; cursor: string }> = [
  { handle: "nw", fx: 0, fy: 0, cursor: "nwse-resize" }, { handle: "n", fx: 0.5, fy: 0, cursor: "ns-resize" }, { handle: "ne", fx: 1, fy: 0, cursor: "nesw-resize" },
  { handle: "w", fx: 0, fy: 0.5, cursor: "ew-resize" }, { handle: "e", fx: 1, fy: 0.5, cursor: "ew-resize" },
  { handle: "sw", fx: 0, fy: 1, cursor: "nesw-resize" }, { handle: "s", fx: 0.5, fy: 1, cursor: "ns-resize" }, { handle: "se", fx: 1, fy: 1, cursor: "nwse-resize" },
];

/**
 * A page (or panel crop) with boxes over it. Boxes can be selected, dragged, resized with their handles and nudged with the
 * arrow keys (Alt for single pixels, Shift to resize); a new box can be drawn. Drawing and dragging use the pointer, everything
 * has a keyboard path, and the image says so when it cannot load.
 */
export const PageCanvas: React.FC<PageCanvasProps> = ({ image, boxes, selectedId, onSelect, onChange, onCommit, onDraw, onImageSize, drawMode = false, showBoxes = true, zoom, editable = true, className, unavailableLabel = "Page image unavailable" }) => {
  const [attempt, setAttempt] = React.useState(0);
  const [failed, setFailed] = React.useState(false);
  const interaction = useCanvasInteraction({ image: { w: image.width, h: image.height }, boxes, editable, drawMode, onSelect, onChange, onCommit, onDraw });
  const scale = 100 / Math.max(1, zoom); // image pixels per screen pixel
  const stroke = 2 * scale;
  const handleSize = 10 * scale;

  if (failed) {
    return (
      <div role="status" className="grid min-h-48 place-items-center gap-2 rounded-ctl border border-edge bg-glass p-6 text-center text-sm text-fg-dim">
        <span>{unavailableLabel}</span>
        <Button size="sm" variant="secondary" onClick={() => { setAttempt((n) => n + 1); setFailed(false); }}>Retry</Button>
      </div>
    );
  }
  const src = attempt ? `${image.src}${image.src.includes("?") ? "&" : "?"}retry=${attempt}` : image.src;
  const selected = boxes.find((b) => b.id === selectedId);

  return (
    <div className={`overflow-auto rounded-ctl border border-edge bg-ink ${className ?? ""}`}>
      <div className="relative" style={{ width: `${(image.width * zoom) / 100}px`, aspectRatio: `${image.width} / ${image.height}` }}>
        <img src={src} alt={image.alt} draggable={false} className="block size-full select-none" onLoad={(e) => onImageSize?.(e.currentTarget.naturalWidth, e.currentTarget.naturalHeight)} onError={() => setFailed(true)} />
        <svg
          ref={interaction.overlayRef}
          data-canvas-overlay
          className="absolute inset-0 size-full"
          viewBox={`0 0 ${image.width} ${image.height}`}
          preserveAspectRatio="none"
          style={{ touchAction: "none", cursor: drawMode && editable ? "crosshair" : "default" }}
          onPointerDown={interaction.onBackgroundPointerDown}
          onPointerMove={interaction.onPointerMove}
          onPointerUp={interaction.onPointerUp}
        >
          {showBoxes && boxes.map((cb) => {
            const { x, y, w, h } = cb.box;
            const active = cb.id === selectedId;
            return (
              <g key={cb.id}>
                <rect
                  data-box-id={cb.id}
                  role="button"
                  tabIndex={0}
                  aria-label={`${cb.label}, at ${x}, ${y}, ${w} by ${h}${cb.locked ? ", locked" : ""}`}
                  aria-pressed={active}
                  x={x} y={y} width={w} height={h}
                  strokeWidth={active ? stroke * 1.8 : stroke}
                  strokeDasharray={cb.locked ? `${stroke * 4} ${stroke * 3}` : undefined}
                  className={`${TONE[cb.tone]} outline-none focus-visible:stroke-info`}
                  style={{ cursor: editable && !cb.locked && !cb.fixed && !drawMode ? "move" : "pointer" }}
                  onPointerDown={(e) => interaction.onBoxPointerDown(e, cb)}
                  onKeyDown={(e) => interaction.onBoxKeyDown(e, cb)}
                />
                <text x={x + 6 * scale} y={y + 18 * scale} fontSize={14 * scale} className="pointer-events-none select-none fill-fg" style={{ paintOrder: "stroke" }}>{cb.label}</text>
              </g>
            );
          })}
          {showBoxes && editable && selected && !selected.locked && !selected.fixed && !drawMode && HANDLES.map(({ handle, fx, fy, cursor }) => (
            <rect
              key={handle}
              data-handle={handle}
              x={selected.box.x + selected.box.w * fx - handleSize / 2}
              y={selected.box.y + selected.box.h * fy - handleSize / 2}
              width={handleSize}
              height={handleSize}
              className="fill-accent stroke-ink"
              strokeWidth={scale}
              style={{ cursor }}
              onPointerDown={(e) => interaction.onHandlePointerDown(e, selected, handle)}
            />
          ))}
          {interaction.drawing && <rect x={interaction.drawing.x} y={interaction.drawing.y} width={interaction.drawing.w} height={interaction.drawing.h} strokeWidth={stroke} strokeDasharray={`${stroke * 4} ${stroke * 3}`} className="pointer-events-none fill-accent/10 stroke-accent" />}
        </svg>
      </div>
    </div>
  );
};
