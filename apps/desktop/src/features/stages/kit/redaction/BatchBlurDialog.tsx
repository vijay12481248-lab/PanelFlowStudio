import React from "react";
import { Button, Dialog } from "@panelflow/ui-v2";
import type { BatchPreset, Redaction } from "./useRedaction";

const PRESETS: Array<{ value: BatchPreset; label: string; hint: string; usesHeight: boolean }> = [
  { value: "TOP_WATERMARK", label: "Top watermark banner", hint: "Blur a strip along the top of every panel.", usesHeight: true },
  { value: "BOTTOM_SUBSCRIBE", label: "Bottom subscribe note", hint: "Blur a strip along the bottom of every panel.", usesHeight: true },
  { value: "ALL_TEXT_REGIONS", label: "All detected text", hint: "Blur every text region the OCR found.", usesHeight: false },
  { value: "ENTIRE_PANEL", label: "Entire panels", hint: "Blur whole panels.", usesHeight: false },
];

/** Blur the same thing on every panel, or put every panel back. Restoring everything asks twice. */
export const BatchBlurDialog: React.FC<{ open: boolean; onClose: () => void; redaction: Redaction }> = ({ open, onClose, redaction }) => {
  const [preset, setPreset] = React.useState<BatchPreset>("TOP_WATERMARK");
  const [height, setHeight] = React.useState("80");
  const [result, setResult] = React.useState<string | null>(null);
  const [restoreStep, setRestoreStep] = React.useState(false);
  React.useEffect(() => { if (open) { setResult(null); setRestoreStep(false); redaction.clearError(); } }, [open]); // eslint-disable-line react-hooks/exhaustive-deps
  const current = PRESETS.find((p) => p.value === preset)!;

  const blur = async () => {
    setResult(null);
    const done = await redaction.batchBlur(preset, Math.max(1, Math.round(Number(height) || 80)));
    if (done) setResult("Blur request sent for the panels. Check them, then use Undo if it isn't right.");
  };
  const restore = async () => {
    setResult(null);
    const done = await redaction.batchReset();
    setRestoreStep(false);
    if (done) setResult("Restore request sent for every panel. Check them, then use Undo if it isn't right.");
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => { if (!next) onClose(); }}
      title="Blur on every panel"
      description="Blur the same area on all panels, for example a site watermark. The original images are kept."
      footer={<><Button variant="ghost" onClick={onClose}>Close</Button><Button variant="primary" loading={redaction.busy && !restoreStep} onClick={() => void blur()}>Blur panels</Button></>}
    >
      <div className="grid grid-cols-1 gap-4">
        <fieldset className="grid gap-2">
          <legend className="mb-1 text-[13px] font-medium text-fg">What to blur</legend>
          {PRESETS.map((p) => (
            <label key={p.value} className="grid gap-0.5 rounded-ctl border border-edge p-2.5 text-sm text-fg">
              <span className="flex items-center gap-2"><input type="radio" name="batch-preset" value={p.value} checked={preset === p.value} onChange={() => setPreset(p.value)} />{p.label}</span>
              <span className="pl-6 text-xs text-fg-dim">{p.hint}</span>
            </label>
          ))}
        </fieldset>
        {current.usesHeight && (
          <label className="grid gap-1 text-[13px] font-medium text-fg">Height in pixels
            <input type="number" min={1} max={2000} value={height} onChange={(e) => setHeight(e.target.value)} className="h-10 w-32 rounded-ctl border border-edge bg-glass px-3 text-sm" />
          </label>
        )}
        {redaction.error && <p role="alert" className="text-sm text-bad">{redaction.error}</p>}
        {result && <p role="status" className="text-sm text-fg-dim">{result}</p>}
        <div className="grid gap-2 border-t border-edge pt-3">
          <h3 className="text-[13px] font-medium text-fg">Put everything back</h3>
          {!restoreStep ? (
            <div><Button variant="secondary" size="sm" onClick={() => setRestoreStep(true)}>Restore every panel</Button></div>
          ) : (
            <div className="grid gap-2">
              <p className="text-sm text-warn">This puts every panel back to its original image. It can't be undone.</p>
              <div className="flex gap-2">
                <Button variant="danger" size="sm" loading={redaction.busy} onClick={() => void restore()}>Yes, restore every panel</Button>
                <Button variant="ghost" size="sm" onClick={() => setRestoreStep(false)}>Keep my changes</Button>
              </div>
            </div>
          )}
        </div>
      </div>
    </Dialog>
  );
};
