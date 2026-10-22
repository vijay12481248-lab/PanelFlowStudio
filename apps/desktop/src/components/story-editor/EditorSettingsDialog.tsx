import React, { useEffect, useRef } from "react";
import { X, Settings2 } from "lucide-react";
import type { StoryEditorState } from "@panelflow/shared-types";

interface EditorSettingsDialogProps {
  state: StoryEditorState;
  onUpdateState: (updater: (state: StoryEditorState) => StoryEditorState) => void;
  onClose: () => void;
}

export function EditorSettingsDialog({ state, onUpdateState, onClose }: EditorSettingsDialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  useEffect(() => {
    const dialog = ref.current;
    if (!dialog) return;
    const previous = document.activeElement as HTMLElement | null;
    if (!dialog.open) dialog.showModal();
    return () => { dialog.close(); previous?.focus(); };
  }, []);
  return (
    <dialog ref={ref} aria-label="Editor settings" className="pf-editor-settings" onCancel={(event) => { event.preventDefault(); onClose(); }}>
      <header className="flex items-center justify-between border-b border-white/10 pb-4 mb-5">
        <h2 className="flex items-center gap-2 text-base font-semibold"><Settings2 size={18} className="text-violet-400" />Editor settings</h2>
        <button type="button" onClick={onClose} aria-label="Close editor settings" className="rounded-md p-1 hover:bg-white/10"><X size={18} /></button>
      </header>
      <div className="space-y-5 text-sm">
        <label className="flex items-center justify-between gap-4">Output format
          <select aria-label="Output format" value={state.aspect_ratio} onChange={(event) => onUpdateState((prev) => ({ ...prev, aspect_ratio: event.target.value as StoryEditorState["aspect_ratio"] }))} className="rounded-lg bg-zinc-900 border border-zinc-700 p-2">
            <option value="16:9">16:9 Landscape</option><option value="9:16">9:16 Portrait</option><option value="1:1">1:1 Square</option>
          </select>
        </label>
        <label className="flex items-center justify-between gap-4">Editing mode
          <select aria-label="Editing mode" value={state.mode} onChange={(event) => onUpdateState((prev) => ({ ...prev, mode: event.target.value as StoryEditorState["mode"] }))} className="rounded-lg bg-zinc-900 border border-zinc-700 p-2">
            <option value="simple">Simple</option><option value="advanced">Advanced</option>
          </select>
        </label>
        {([
          ["snapping", "Snap clips to timeline", state.snapping !== false],
          ["ripple_edit", "Ripple linked scene timing", state.ripple_edit !== false],
          ["show_motion_paths", "Show motion paths on canvas", !!state.show_motion_paths],
        ] as const).map(([key, label, checked]) => (
          <label key={key} className="flex items-center justify-between gap-4">
            {label}<input type="checkbox" checked={checked} onChange={(event) => onUpdateState((prev) => ({ ...prev, [key]: event.target.checked }))} className="accent-violet-500 w-4 h-4" />
          </label>
        ))}
        <p className="text-xs leading-relaxed text-zinc-400 border-t border-white/10 pt-4">Changes use this project’s existing autosave, undo and export state. Canvas view zoom does not change the exported video.</p>
      </div>
    </dialog>
  );
}
