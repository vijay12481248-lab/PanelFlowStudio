import React from "react";
import { Eraser, Eye, EyeOff, Maximize2, Paintbrush, Redo2, Trash2, Undo2, ZoomIn, ZoomOut } from "lucide-react";
import type { ToolMode } from "./types";

const BTN =
  "flex h-9 w-9 items-center justify-center rounded-lg text-fg-dim transition-colors hover:bg-flat hover:text-fg disabled:pointer-events-none disabled:opacity-30";

/** Left rail: the mask tools (only while Inpaint is the AI mode) and the view controls. */
export const ToolRail: React.FC<{
  maskTools: boolean;
  tool: ToolMode;
  onTool: (tool: ToolMode) => void;
  canUndo: boolean;
  canRedo: boolean;
  hasMask: boolean;
  showMask: boolean;
  onUndo: () => void;
  onRedo: () => void;
  onClearMask: () => void;
  onToggleMask: () => void;
  zoom: number;
  fitMode: "contain" | "actual";
  onZoomOut: () => void;
  onZoomIn: () => void;
  onFit: () => void;
}> = (p) => (
  <div className="flex w-12 flex-col items-center gap-1 border-r border-edge bg-navy py-2">
    {p.maskTools && (
      <>
        <button type="button" className={`${BTN} ${p.tool === "brush" ? "bg-accent-soft text-info" : ""}`} onClick={() => p.onTool("brush")} title="Brush (B)">
          <Paintbrush className="h-4 w-4" />
        </button>
        <button type="button" className={`${BTN} ${p.tool === "eraser" ? "bg-accent-soft text-info" : ""}`} onClick={() => p.onTool("eraser")} title="Eraser (E)">
          <Eraser className="h-4 w-4" />
        </button>
        <button type="button" className={BTN} onClick={p.onUndo} disabled={!p.canUndo} title="Undo (Ctrl+Z)">
          <Undo2 className="h-4 w-4" />
        </button>
        <button type="button" className={BTN} onClick={p.onRedo} disabled={!p.canRedo} title="Redo (Ctrl+Y)">
          <Redo2 className="h-4 w-4" />
        </button>
        <button type="button" className={`${BTN} hover:text-bad`} onClick={p.onClearMask} disabled={!p.hasMask} title="Clear mask">
          <Trash2 className="h-4 w-4" />
        </button>
        <button type="button" className={`${BTN} ${!p.showMask ? "text-warn" : ""}`} onClick={p.onToggleMask} title={p.showMask ? "Hide mask overlay" : "Show mask overlay"}>
          {p.showMask ? <Eye className="h-4 w-4" /> : <EyeOff className="h-4 w-4" />}
        </button>
        <div className="my-1 h-px w-6 bg-edge" />
      </>
    )}
    <button type="button" className={BTN} onClick={p.onZoomIn} title="Zoom in">
      <ZoomIn className="h-4 w-4" />
    </button>
    <span className="font-mono text-[10px] text-fg-faint">{Math.round(p.zoom * 100)}%</span>
    <button type="button" className={BTN} onClick={p.onZoomOut} title="Zoom out">
      <ZoomOut className="h-4 w-4" />
    </button>
    <button type="button" className={`${BTN} ${p.fitMode === "actual" ? "bg-accent-soft text-info" : ""}`} onClick={p.onFit} title="Toggle 100% size or Fit to screen">
      <Maximize2 className="h-4 w-4" />
    </button>
  </div>
);
