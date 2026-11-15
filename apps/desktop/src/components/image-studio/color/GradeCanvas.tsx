import React, { useEffect, useRef } from "react";
import { drawGraded } from "./gradeRender";

const DISPLAY_EDGE = 2048;

/** The picture drawn through the grade's LUT, laid over the plain <img>. Hidden when there is nothing to show. */
export const GradeCanvas: React.FC<{
  bitmap: ImageBitmap | null;
  table: Float32Array | null;
  size: number;
  onError?: (message: string) => void;
}> = ({ bitmap, table, size, onError }) => {
  const ref = useRef<HTMLCanvasElement>(null);
  const visible = !!bitmap && !!table;

  useEffect(() => {
    if (!visible || !ref.current || !bitmap || !table) return;
    try {
      drawGraded(ref.current, bitmap, table, size, DISPLAY_EDGE);
    } catch (err: any) {
      onError?.(err?.message || "The grade could not be drawn.");
    }
  }, [bitmap, table, size, visible]);

  return (
    <canvas
      ref={ref}
      aria-hidden="true"
      className="pointer-events-none absolute inset-0 h-full w-full rounded-lg"
      style={{ display: visible ? "block" : "none" }}
    />
  );
};
