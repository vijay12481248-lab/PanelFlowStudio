import React, { useState } from "react";
import { FlipHorizontal2, FlipVertical2, Redo2, RotateCcw, RotateCw, Undo2 } from "lucide-react";
import { SliderRow } from "../color/controls";
import { ASPECTS, applyAspect, cutGeometry, flipCut, isCutIdentity, newCut, turnCut, type AspectId, type CutState } from "./geometry";

const LONG_EDGES: (number | null)[] = [null, 2048, 1536, 1080, 720, 512];

const Chip: React.FC<{ on?: boolean; onClick: () => void; children: React.ReactNode }> = ({ on, onClick, children }) => (
  <button
    type="button"
    onClick={onClick}
    className={`rounded-full border px-2.5 py-1 text-[11px] transition-colors ${on ? "border-accent bg-accent-soft text-fg" : "border-edge bg-flat text-fg-dim hover:text-fg"}`}
  >
    {children}
  </button>
);

const ToolBtn: React.FC<{ title: string; onClick: () => void; disabled?: boolean; on?: boolean; children: React.ReactNode }> = ({ title, onClick, disabled, on, children }) => (
  <button
    type="button"
    title={title}
    aria-label={title}
    onClick={onClick}
    disabled={disabled}
    className={`flex h-8 flex-1 items-center justify-center rounded-lg border transition-colors disabled:pointer-events-none disabled:opacity-35 ${on ? "border-accent bg-accent-soft text-fg" : "border-edge bg-flat text-fg-dim hover:text-fg"}`}
  >
    {children}
  </button>
);

export interface CutInspectorProps {
  cut: CutState;
  /** Size of the picture being cut, in pixels. */
  sourceWidth: number;
  sourceHeight: number;
  onChange: (next: CutState, key: string) => void;
  canUndo: boolean;
  canRedo: boolean;
  onUndo: () => void;
  onRedo: () => void;
}

export const CutInspector: React.FC<CutInspectorProps> = ({ cut, sourceWidth, sourceHeight, onChange, canUndo, canRedo, onUndo, onRedo }) => {
  const [custom, setCustom] = useState("");
  const g = cutGeometry(cut, sourceWidth, sourceHeight);
  const refit = (next: CutState) => applyAspect(next, sourceWidth, sourceHeight);

  const pickAspect = (aspect: AspectId) => onChange(refit({ ...cut, aspect }), "");
  const setAngle = (angle: number) => onChange(refit({ ...cut, angle: Math.round(angle * 10) / 10 }), "angle");
  const setLongEdge = (longEdge: number | null) => onChange({ ...cut, longEdge }, "long");

  return (
    <div className="flex h-full flex-col overflow-y-auto p-4">
      <div className="flex flex-col gap-4">
        <div className="flex items-center justify-between">
          <span className="text-[11px] font-medium text-fg-dim">Cut</span>
          <div className="flex items-center gap-1.5">
            <button type="button" title="Undo cut change" aria-label="Undo cut change" onClick={onUndo} disabled={!canUndo} className="flex h-7 w-7 items-center justify-center rounded-md border border-edge bg-flat text-fg-dim transition-colors hover:text-fg disabled:pointer-events-none disabled:opacity-35"><Undo2 className="h-3.5 w-3.5" /></button>
            <button type="button" title="Redo cut change" aria-label="Redo cut change" onClick={onRedo} disabled={!canRedo} className="flex h-7 w-7 items-center justify-center rounded-md border border-edge bg-flat text-fg-dim transition-colors hover:text-fg disabled:pointer-events-none disabled:opacity-35"><Redo2 className="h-3.5 w-3.5" /></button>
            <button type="button" onClick={() => onChange(newCut(), "")} disabled={isCutIdentity(cut)} className="rounded-md border border-edge bg-flat px-2 py-1 text-[11px] text-fg-dim transition-colors hover:text-fg disabled:pointer-events-none disabled:opacity-35">Reset</button>
          </div>
        </div>

        <section className="flex flex-col gap-2">
          <span className="text-[11px] font-medium text-fg-dim">Crop</span>
          <div className="flex flex-wrap gap-1.5">
            {ASPECTS.map((a) => (
              <Chip key={a.id} on={cut.aspect === a.id} onClick={() => pickAspect(a.id)}>{a.label}</Chip>
            ))}
          </div>
          <p className="text-[11px] text-fg-faint">
            Drag the frame to move it and a handle to resize it. An aspect other than Free stays locked while you drag.
          </p>
        </section>

        <section className="flex flex-col gap-2">
          <SliderRow label="Straighten" value={cut.angle} min={-45} max={45} step={0.1} def={0} digits={1} onChange={setAngle} />
          <div className="flex gap-1.5">
            <ToolBtn title="Turn left" onClick={() => onChange(refit(turnCut(cut, -1)), "")}><RotateCcw className="h-4 w-4" /></ToolBtn>
            <ToolBtn title="Turn right" onClick={() => onChange(refit(turnCut(cut, 1)), "")}><RotateCw className="h-4 w-4" /></ToolBtn>
            <ToolBtn title="Flip horizontally" on={cut.flipH} onClick={() => onChange(flipCut(cut, "h"), "")}><FlipHorizontal2 className="h-4 w-4" /></ToolBtn>
            <ToolBtn title="Flip vertically" on={cut.flipV} onClick={() => onChange(flipCut(cut, "v"), "")}><FlipVertical2 className="h-4 w-4" /></ToolBtn>
          </div>
        </section>

        <section className="flex flex-col gap-2">
          <span className="text-[11px] font-medium text-fg-dim">Output size (long edge)</span>
          <div className="flex flex-wrap items-center gap-1.5">
            {LONG_EDGES.map((v) => (
              <Chip key={v ?? "keep"} on={cut.longEdge === v} onClick={() => { setCustom(""); setLongEdge(v); }}>{v === null ? "Keep" : `${v}`}</Chip>
            ))}
            <input
              type="number"
              min={16}
              max={16384}
              placeholder="px"
              aria-label="Custom long edge in pixels"
              value={custom}
              onChange={(e) => {
                setCustom(e.target.value);
                const v = Math.round(Number(e.target.value));
                if (Number.isFinite(v) && v >= 16 && v <= 16384) setLongEdge(v);
              }}
              className="w-16 rounded-md border border-edge bg-flat px-1.5 py-1 text-right font-mono text-[11px] text-fg focus:border-accent focus:outline-none"
            />
          </div>
          <p className="font-mono text-[11px] text-fg-dim" aria-live="polite">
            {g.outW} × {g.outH} px <span className="text-fg-faint">from {sourceWidth} × {sourceHeight}</span>
          </p>
        </section>

        <p className="text-[11px] leading-snug text-fg-faint">
          The cut is applied when you export or save from Deliver. The AI and Inpaint pages keep showing the whole picture, so masks line up.
        </p>
      </div>
    </div>
  );
};
