import React from "react";
import { drawBox, isDrawable, moveBox, nudgeBox, pointToImage, resizeBox, type Box, type Handle, type Point, type Size } from "./geometry";

export interface CanvasBox {
  id: string;
  box: Box;
  label: string;
  tone: "accent" | "ok" | "warn" | "bad" | "neutral";
  /** Can be selected but not moved, resized or nudged. */
  locked?: boolean;
}

export interface InteractionOptions {
  image: Size;
  boxes: CanvasBox[];
  editable: boolean;
  drawMode: boolean;
  onSelect: (id: string | null, additive: boolean) => void;
  /** Every step of a drag, and the restore when a drag is cancelled. */
  onChange?: (id: string, box: Box) => void;
  /** Once, when a drag or a key press has changed a box. `previous` is the box as it was before. */
  onCommit?: (id: string, box: Box, previous: Box) => void;
  onDraw?: (box: Box) => void;
}

type Session = { kind: "move" | "resize" | "draw"; id?: string; handle?: Handle; start: Point; startBox?: Box; last?: Box };

const same = (a: Box, b: Box) => a.x === b.x && a.y === b.y && a.w === b.w && a.h === b.h;

/** The drag state machine of the canvas: move, resize and draw with the pointer, nudge with the keyboard, Escape to cancel. */
export function useCanvasInteraction(options: InteractionOptions) {
  const opts = React.useRef(options);
  opts.current = options;
  const overlayRef = React.useRef<SVGSVGElement | null>(null);
  const session = React.useRef<Session | null>(null);
  const [drawing, setDrawing] = React.useState<Box | null>(null);

  const toImage = (e: { clientX: number; clientY: number }): Point =>
    pointToImage(overlayRef.current!.getBoundingClientRect(), opts.current.image, { x: e.clientX, y: e.clientY });
  const find = (id: string) => opts.current.boxes.find((b) => b.id === id);
  const capture = (e: React.PointerEvent) => {
    if (typeof e.pointerId === "number") overlayRef.current?.setPointerCapture?.(e.pointerId);
  };

  // Escape puts a dragged box back and ends the drag without a commit.
  React.useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const s = session.current;
      if (event.key !== "Escape" || !s) return;
      if ((s.kind === "move" || s.kind === "resize") && s.id && s.startBox) opts.current.onChange?.(s.id, s.startBox);
      session.current = null;
      setDrawing(null);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  return {
    overlayRef,
    drawing,

    onBoxPointerDown(e: React.PointerEvent, cb: CanvasBox) {
      e.stopPropagation();
      const additive = e.shiftKey || e.ctrlKey || e.metaKey;
      opts.current.onSelect(cb.id, additive);
      const { editable, drawMode } = opts.current;
      if (!editable || cb.locked || drawMode || additive) return;
      capture(e);
      session.current = { kind: "move", id: cb.id, start: toImage(e), startBox: cb.box };
    },

    onHandlePointerDown(e: React.PointerEvent, cb: CanvasBox, handle: Handle) {
      e.stopPropagation();
      if (!opts.current.editable || cb.locked) return;
      capture(e);
      session.current = { kind: "resize", id: cb.id, handle, start: toImage(e), startBox: cb.box };
    },

    onBackgroundPointerDown(e: React.PointerEvent) {
      const { editable, drawMode } = opts.current;
      if (drawMode && editable) {
        capture(e);
        const start = toImage(e);
        session.current = { kind: "draw", start };
        setDrawing({ x: start.x, y: start.y, w: 0, h: 0 });
      } else {
        opts.current.onSelect(null, false);
      }
    },

    onPointerMove(e: React.PointerEvent) {
      const s = session.current;
      if (!s) return;
      const p = toImage(e);
      if (s.kind === "draw") { setDrawing(drawBox(s.start, p)); return; }
      if (!s.startBox || !s.id) return;
      const dx = p.x - s.start.x;
      const dy = p.y - s.start.y;
      const next = s.kind === "move" ? moveBox(s.startBox, dx, dy, opts.current.image) : resizeBox(s.startBox, s.handle!, dx, dy, opts.current.image);
      if (s.last && same(s.last, next)) return;
      if (!s.last && same(s.startBox, next)) return;
      s.last = next;
      opts.current.onChange?.(s.id, next);
    },

    onPointerUp(e: React.PointerEvent) {
      const s = session.current;
      session.current = null;
      if (!s) return;
      if (s.kind === "draw") {
        const box = drawBox(s.start, toImage(e));
        setDrawing(null);
        if (isDrawable(box)) opts.current.onDraw?.(box);
        return;
      }
      if (s.id && s.startBox && s.last && !same(s.last, s.startBox)) opts.current.onCommit?.(s.id, s.last, s.startBox);
    },

    onBoxKeyDown(e: React.KeyboardEvent, cb: CanvasBox) {
      if (e.key === "Enter" || e.key === " ") { e.preventDefault(); opts.current.onSelect(cb.id, false); return; }
      if (!["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key)) return;
      const { editable, image } = opts.current;
      if (!editable || cb.locked) return;
      const current = find(cb.id)?.box ?? cb.box;
      const next = nudgeBox(current, e.key as "ArrowLeft", e.altKey ? 1 : 10, e.shiftKey, image);
      e.preventDefault();
      if (same(next, current)) return;
      opts.current.onChange?.(cb.id, next);
      opts.current.onCommit?.(cb.id, next, current);
    },
  };
}
