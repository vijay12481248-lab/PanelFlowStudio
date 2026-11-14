import React from "react";
import { AlertCircle, ImageUp, RefreshCw, Wand2 } from "lucide-react";
import { AiMode, INPUT_CLASS, ToolMode } from "./types";

export interface InpaintPreset {
  label: string;
  prompt: string;
}

export interface MaskColor {
  id: string;
  label: string;
  hex: string;
}

export interface AiInspectorProps {
  mode: AiMode;
  onMode: (mode: AiMode) => void;
  /** Edit and Pose & camera need a project picture; story panels can only be inpainted. */
  isProject: boolean;
  busy: boolean;
  progress: number;
  statusText: string;
  error: string | null;
  prompt: string;
  onPrompt: (value: string) => void;
  seed: number;
  onSeed: (value: number) => void;
  onEdit: () => void;
  pose: {
    imageData: string | null;
    fileName: string;
    note: string;
    onNote: (value: string) => void;
    onFile: (file?: File) => void;
    onSubmit: () => void;
  };
  inpaint: {
    tool: ToolMode;
    onTool: (tool: ToolMode) => void;
    brushSize: number;
    onBrushSize: (value: number) => void;
    brushOpacity: number;
    onBrushOpacity: (value: number) => void;
    maskColors: MaskColor[];
    maskColorIndex: number;
    onMaskColor: (index: number) => void;
    presets: InpaintPreset[];
    negativePrompt: string;
    onNegativePrompt: (value: string) => void;
    hasMask: boolean;
    onSubmit: () => void;
  };
}

const MODES: { id: AiMode; label: string; project: boolean }[] = [
  { id: "edit", label: "Edit", project: true },
  { id: "pose", label: "Pose & camera", project: true },
  { id: "inpaint", label: "Inpaint", project: false },
];

const Label: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <span className="mb-1 block text-[11px] font-medium text-fg-dim">{children}</span>
);

const GenerateButton: React.FC<{ disabled: boolean; busy: boolean; onClick: () => void; idle: string; workflow: string }> = ({
  disabled, busy, onClick, idle, workflow,
}) => (
  <div className="flex flex-col gap-1">
    <button
      type="button"
      onClick={onClick}
      disabled={disabled || busy}
      className={`flex w-full items-center justify-center gap-2 rounded-xl py-2.5 text-xs font-semibold transition-colors ${
        disabled || busy ? "cursor-not-allowed border border-edge bg-flat text-fg-faint" : "bg-accent text-white hover:bg-accent/90"
      }`}
    >
      <Wand2 className={`h-4 w-4 ${busy ? "animate-spin" : ""}`} />
      <span>{busy ? "Working…" : idle}</span>
    </button>
    <span className="text-center font-mono text-[10px] text-fg-faint">{workflow}</span>
  </div>
);

export const AiInspector: React.FC<AiInspectorProps> = (p) => {
  const fileInput = React.useRef<HTMLInputElement>(null);
  const { inpaint, pose } = p;

  return (
    <div className="flex h-full flex-col gap-4 overflow-y-auto p-4">
      <div role="tablist" aria-label="AI mode" className="flex gap-1 rounded-lg bg-flat p-1">
        {MODES.map((m) => {
          const locked = m.project && !p.isProject;
          return (
            <button
              key={m.id}
              type="button"
              role="tab"
              aria-selected={p.mode === m.id}
              disabled={locked || p.busy}
              title={locked ? "Needs a project picture" : undefined}
              onClick={() => p.onMode(m.id)}
              className={`flex-1 rounded-md py-1.5 text-[11px] font-medium transition-colors ${
                p.mode === m.id ? "bg-accent text-white" : "text-fg-dim hover:text-fg"
              } ${locked ? "cursor-not-allowed opacity-40" : ""}`}
            >
              {m.label}
            </button>
          );
        })}
      </div>

      {p.mode === "edit" && (
        <section className="flex flex-col gap-3">
          <p className="text-[11px] leading-snug text-fg-faint">Describe what the whole picture should become. No mask needed.</p>
          <label>
            <Label>Instruction</Label>
            <textarea
              value={p.prompt}
              onChange={(e) => p.onPrompt(e.target.value)}
              rows={4}
              disabled={p.busy}
              placeholder="e.g. a stormy sky over the street, golden sparks around the sword"
              className={INPUT_CLASS}
            />
          </label>
          <GenerateButton disabled={!p.prompt.trim()} busy={p.busy} onClick={p.onEdit} idle="Edit with H3 Image" workflow="minimax_h3_image_edit" />
        </section>
      )}

      {p.mode === "pose" && (
        <section className="flex flex-col gap-3">
          <p className="text-[11px] leading-snug text-fg-faint">
            This picture keeps its characters, scene and style. The picture you choose, a photo works, gives the poses, camera angle and
            framing. The result has that picture's shape.
          </p>
          <div>
            <Label>Pose and camera picture</Label>
            <input ref={fileInput} type="file" accept="image/*" className="hidden" disabled={p.busy} onChange={(e) => pose.onFile(e.target.files?.[0])} />
            <button
              type="button"
              disabled={p.busy}
              onClick={() => fileInput.current?.click()}
              className="flex w-full flex-col items-center gap-1 rounded-lg border border-dashed border-edge bg-flat/60 px-3 py-4 text-[11px] text-fg-dim transition-colors hover:border-info/60 hover:text-fg"
            >
              {pose.imageData ? (
                <>
                  <img src={pose.imageData} alt="Pose and camera reference" className="mb-1 max-h-28 rounded-md border border-edge object-contain" />
                  <span className="max-w-full truncate">{pose.fileName}</span>
                  <span className="text-fg-faint">Click to choose another</span>
                </>
              ) : (
                <>
                  <ImageUp className="h-5 w-5" />
                  <span>Choose a picture from disk</span>
                </>
              )}
            </button>
          </div>
          <label>
            <Label>Who plays whom (optional)</Label>
            <input
              type="text"
              value={pose.note}
              onChange={(e) => pose.onNote(e.target.value)}
              disabled={p.busy}
              placeholder="the man in black leaps, the armoured man crouches"
              className={INPUT_CLASS}
            />
          </label>
          <GenerateButton disabled={!pose.imageData} busy={p.busy} onClick={pose.onSubmit} idle="Transfer pose & camera" workflow="minimax_h3_image_edit" />
        </section>
      )}

      {p.mode === "inpaint" && (
        <section className="flex flex-col gap-3">
          <p className="text-[11px] leading-snug text-fg-faint">
            Paint over the area to replace (B brush, E eraser, [ ] size), then say what belongs there.
          </p>
          <label>
            <Label>What to draw in the mask</Label>
            <textarea
              value={p.prompt}
              onChange={(e) => p.onPrompt(e.target.value)}
              rows={3}
              disabled={p.busy}
              placeholder="e.g. golden sparks around the sword"
              className={INPUT_CLASS}
            />
          </label>
          <div className="flex flex-wrap gap-1.5">
            {inpaint.presets.map((preset) => (
              <button
                key={preset.label}
                type="button"
                disabled={p.busy}
                onClick={() => p.onPrompt(preset.prompt)}
                className="rounded-full border border-edge bg-flat px-2.5 py-1 text-[11px] text-fg-dim transition-colors hover:border-info/60 hover:text-fg"
              >
                {preset.label}
              </button>
            ))}
          </div>
          <div>
            <div className="mb-1 flex justify-between text-[11px] text-fg-dim">
              <span>Brush size</span>
              <span className="font-mono">{inpaint.brushSize}px</span>
            </div>
            <input type="range" min={8} max={200} value={inpaint.brushSize} onChange={(e) => inpaint.onBrushSize(Number(e.target.value))} className="w-full accent-accent" />
          </div>
          <div>
            <div className="mb-1 flex justify-between text-[11px] text-fg-dim">
              <span>Mask opacity</span>
              <span className="font-mono">{Math.round(inpaint.brushOpacity * 100)}%</span>
            </div>
            <input type="range" min={0.3} max={1} step={0.05} value={inpaint.brushOpacity} onChange={(e) => inpaint.onBrushOpacity(Number(e.target.value))} className="w-full accent-accent" />
          </div>
          <div className="flex items-center gap-2 text-[11px] text-fg-dim">
            <span>Mask colour</span>
            {inpaint.maskColors.map((c, i) => (
              <button
                key={c.id}
                type="button"
                title={c.label}
                aria-label={c.label}
                onClick={() => inpaint.onMaskColor(i)}
                className={`h-5 w-5 rounded-full border-2 transition-transform ${inpaint.maskColorIndex === i ? "scale-110 border-fg" : "border-transparent"}`}
                style={{ backgroundColor: c.hex }}
              />
            ))}
          </div>
          <details className="text-[11px] text-fg-dim">
            <summary className="cursor-pointer select-none">Negative prompt</summary>
            <textarea value={inpaint.negativePrompt} onChange={(e) => inpaint.onNegativePrompt(e.target.value)} rows={2} className={`${INPUT_CLASS} mt-1`} />
          </details>
          <GenerateButton
            disabled={!inpaint.hasMask || !p.prompt.trim()}
            busy={p.busy}
            onClick={inpaint.onSubmit}
            idle={inpaint.hasMask ? "Inpaint masked area" : "Paint a mask to inpaint"}
            workflow="qwen_image_21_inpaint"
          />
        </section>
      )}

      <div className="mt-auto flex flex-col gap-3 border-t border-edge/70 pt-3">
        <div className="flex items-center gap-2">
          <span className="text-[11px] text-fg-dim">Seed</span>
          <input type="number" value={p.seed} disabled={p.busy} onChange={(e) => p.onSeed(Number(e.target.value) || 0)} className={`${INPUT_CLASS} font-mono`} />
          <button
            type="button"
            title="New random seed"
            aria-label="New random seed"
            disabled={p.busy}
            onClick={() => p.onSeed(Math.floor(Math.random() * 900000000) + 100000000)}
            className="rounded-lg border border-edge bg-flat p-2 text-fg-dim transition-colors hover:text-fg"
          >
            <RefreshCw className="h-3.5 w-3.5" />
          </button>
        </div>
        {p.error && (
          <div role="alert" className="flex items-start gap-2 rounded-lg border border-bad/50 bg-bad/10 p-2.5 text-[11px] text-bad">
            <AlertCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
            <span>{p.error}</span>
          </div>
        )}
        {p.busy && (
          <div>
            <div className="mb-1 flex justify-between text-[11px] text-fg-dim">
              <span className="truncate">{p.statusText || "Working…"}</span>
              <span className="font-mono">{Math.round(p.progress * 100)}%</span>
            </div>
            <div className="h-1 overflow-hidden rounded-full bg-flat">
              <div className="h-full rounded-full bg-accent transition-all duration-300" style={{ width: `${Math.max(4, p.progress * 100)}%` }} />
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
