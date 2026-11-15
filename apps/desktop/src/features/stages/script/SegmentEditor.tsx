import React from "react";
import { Button, Select } from "@panelflow/ui-v2";
import { EMOTIONS } from "./scriptModel";

export interface LineValues { text: string; emotion: string; intensity: number; estimated_duration?: number }

export interface SegmentEditorProps {
  initial: { text: string; emotion: string; intensity: number; duration?: number };
  /** Spoken-script lines have an estimated length; storyboard beats do not. */
  showDuration: boolean;
  saveLabel: string;
  busy: boolean;
  /** Resolves true when the change was saved (the caller then closes the editor). */
  onSave: (values: LineValues) => Promise<boolean>;
  onCancel: () => void;
}

const FIELD = "rounded-ctl border border-edge bg-glass text-sm text-fg focus-visible:outline-2 focus-visible:outline-info";

/** Edit a line's text, emotion and intensity. Nothing is saved until it differs from what is on file and the text is not blank. */
export const SegmentEditor: React.FC<SegmentEditorProps> = ({ initial, showDuration, saveLabel, busy, onSave, onCancel }) => {
  const [text, setText] = React.useState(initial.text);
  const [emotion, setEmotion] = React.useState(initial.emotion);
  const [intensity, setIntensity] = React.useState(initial.intensity);
  const [seconds, setSeconds] = React.useState(initial.duration ?? 2);
  const saving = React.useRef(false);

  const trimmed = text.trim();
  const changed = trimmed !== initial.text.trim() || emotion !== initial.emotion || intensity !== initial.intensity || (showDuration && seconds !== (initial.duration ?? 2));
  const valid = trimmed !== "" && (!showDuration || seconds >= 0.1);
  const emotions = EMOTIONS.includes(initial.emotion as (typeof EMOTIONS)[number]) ? [...EMOTIONS] : [initial.emotion, ...EMOTIONS];

  const save = async () => {
    if (saving.current || !changed || !valid) return;
    saving.current = true;
    try {
      await onSave({ text: trimmed, emotion, intensity, ...(showDuration ? { estimated_duration: seconds } : {}) });
    } finally { saving.current = false; }
  };

  return (
    <div className="grid grid-cols-1 gap-3 pt-1">
      <textarea aria-label="Line text" rows={3} value={text} onChange={(e) => setText(e.target.value)} className={`w-full p-3 font-data ${FIELD}`} />
      <div className="flex flex-wrap items-end gap-4">
        <label className="grid gap-1 text-xs text-fg-dim">
          Emotion
          <Select aria-label="Emotion" className="h-9 w-44 text-sm" value={emotion} onChange={(e) => setEmotion(e.target.value)}>
            {emotions.map((e) => <option key={e} value={e}>{e}</option>)}
          </Select>
        </label>
        <label className="grid gap-1 text-xs text-fg-dim">
          {`Intensity ${Math.round(intensity * 100)}%`}
          <input type="range" aria-label="Intensity" min={0.1} max={1} step={0.1} value={intensity} onChange={(e) => setIntensity(parseFloat(e.target.value))} className="h-1.5 w-32 accent-accent" />
        </label>
        {showDuration && (
          <label className="grid gap-1 text-xs text-fg-dim">
            Estimated seconds
            <input type="number" aria-label="Estimated seconds" min={0.1} step={0.1} value={seconds} onChange={(e) => setSeconds(Number(e.target.value))} className={`h-9 w-24 px-2 ${FIELD}`} />
          </label>
        )}
      </div>
      <div className="flex justify-end gap-2">
        <Button variant="ghost" size="sm" onClick={onCancel}>Cancel</Button>
        <Button variant="primary" size="sm" loading={busy} disabled={!changed || !valid} onClick={() => void save()}>{saveLabel}</Button>
      </div>
    </div>
  );
};
