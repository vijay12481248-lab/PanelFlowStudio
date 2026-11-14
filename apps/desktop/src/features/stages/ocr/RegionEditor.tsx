import React from "react";
import type { CharacterEntity, TextRegion } from "@panelflow/shared-types";
import { Button, GlassPanel, Select } from "@panelflow/ui-v2";
import { ConfirmDialog } from "../kit/ConfirmDialog";
import { type EditForm, type TextTool, assignmentWord, editForm, formatText, regionPatch, speakerOptions, statusOptions, typeOptions } from "./ocrModel";
import type { RegionEditing } from "./useRegionEditing";

const TOOLS: Array<{ id: TextTool; label: string; hint: string }> = [
  { id: "trim", label: "Trim spaces", hint: "Collapse repeated spaces into one and trim the ends" },
  { id: "quotes", label: "Fix quotes", hint: "Turn Japanese brackets and curly quotes into plain quotes" },
  { id: "sentence", label: "Sentence case", hint: "Capitalise the first letter of each sentence" },
  { id: "clear", label: "Clear text", hint: "Empty the correction" },
];

export interface RegionEditorProps {
  region: TextRegion;
  characters: CharacterEntity[];
  editing: RegionEditing;
  /** Whether Read again can be used (a real engine is chosen). */
  canReadAgain: boolean;
  onSaveAndNext: (region: TextRegion, form: EditForm) => void;
  /** The region was deleted. */
  onDeleted: () => void;
}

const Section: React.FC<{ title: string; children: React.ReactNode }> = ({ title, children }) => (
  <section className="grid gap-2 border-t border-edge pt-3 first:border-t-0 first:pt-0">
    <h4 className="text-[13px] font-medium text-fg">{title}</h4>
    {children}
  </section>
);

/** One text region in its three layers: what the engine read, what the person corrected, and who says it. */
export const RegionEditor: React.FC<RegionEditorProps> = ({ region, characters, editing, canReadAgain, onSaveAndNext, onDeleted }) => {
  const [form, setForm] = React.useState<EditForm>(() => editForm(region));
  const [confirmingDelete, setConfirmingDelete] = React.useState(false);

  // Start again from the region when the engine's copy of it changes (another region, a re-read, a save), not on every keystroke.
  const seed = JSON.stringify(editForm(region));
  React.useEffect(() => { setForm(JSON.parse(seed) as EditForm); editing.clearError(); }, [region.id, seed]); // eslint-disable-line react-hooks/exhaustive-deps

  const dirty = Object.keys(regionPatch(region, form)).length > 0;
  const set = <K extends keyof EditForm>(key: K, value: EditForm[K]) => setForm((f) => ({ ...f, [key]: value }));
  const confidence = region.raw_confidence == null ? null : `${Math.round(region.raw_confidence * 100)}%`;

  return (
    <GlassPanel blur={false} className="grid grid-cols-1 gap-3 p-4" aria-label={`Region ${region.sequence_in_panel}`}>
      <h3 className="font-display text-sm font-semibold text-fg">{`Region ${region.sequence_in_panel}`}</h3>

      <Section title="Machine reading">
        <p data-machine-text className="rounded-ctl border border-edge bg-glass p-2 text-sm text-fg-dim">{region.raw_text?.trim() ? region.raw_text : "Nothing was read yet."}</p>
        <p className="text-xs text-fg-faint">{region.ocr_engine ? `Read by ${region.ocr_engine}${confidence ? `, ${confidence} sure` : ""}.` : "Not read by an engine."}</p>
        <div><Button size="sm" variant="secondary" disabled={editing.busy || !canReadAgain} onClick={() => void editing.readOne(region)}>Read again</Button></div>
      </Section>

      <Section title="Correction">
        <textarea
          aria-label="Corrected text"
          value={form.corrected_text}
          onChange={(e) => set("corrected_text", e.target.value)}
          className="min-h-24 w-full rounded-ctl border border-edge bg-glass p-3 text-sm text-fg"
          placeholder="Type the text exactly as it should be read"
        />
        <div className="flex flex-wrap gap-2">
          {TOOLS.map((t) => <Button key={t.id} size="sm" variant="ghost" title={t.hint} onClick={() => set("corrected_text", formatText(t.id, form.corrected_text))}>{t.label}</Button>)}
        </div>
        <div className="grid grid-cols-2 gap-2">
          <label className="grid gap-1 text-xs text-fg-dim">Type
            <Select aria-label="Region type" className="h-9 text-sm" value={form.region_type} onChange={(e) => set("region_type", e.target.value)}>
              {typeOptions(region.region_type).map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
            </Select>
          </label>
          <label className="grid gap-1 text-xs text-fg-dim">Status
            <Select aria-label="Region status" className="h-9 text-sm" value={form.status} onChange={(e) => set("status", e.target.value)}>
              {statusOptions(region.status).map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
            </Select>
          </label>
        </div>
      </Section>

      <Section title="Speaker">
        <Select aria-label="Speaker" className="h-9 text-sm" value={form.speaker_character_id} onChange={(e) => set("speaker_character_id", e.target.value)}>
          {speakerOptions(characters, region.speaker_character_id).map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
        </Select>
        <p className="text-xs text-fg-faint">{`Chosen by: ${assignmentWord(region.speaker_assignment_method)}`}</p>
      </Section>

      {editing.error && <p role="alert" className="text-sm text-bad">{editing.error}</p>}
      <div className="flex flex-wrap gap-2">
        <Button size="sm" variant="secondary" disabled={editing.busy || !dirty} onClick={() => void editing.save(region, form)}>Save</Button>
        <Button size="sm" variant="primary" disabled={editing.busy} onClick={() => void editing.approve(region, form)}>Approve</Button>
        <Button size="sm" variant="secondary" disabled={editing.busy} onClick={() => void editing.reject(region)}>Ignore this region</Button>
        <Button size="sm" variant="secondary" disabled={editing.busy} onClick={() => onSaveAndNext(region, form)}>Save and next</Button>
        <Button size="sm" variant="danger" disabled={editing.busy} onClick={() => setConfirmingDelete(true)}>Delete region</Button>
      </div>
      <ConfirmDialog
        open={confirmingDelete}
        title={`Delete region ${region.sequence_in_panel}?`}
        description="The region and its text are removed. You can undo it with Undo."
        confirmLabel="Delete region"
        danger
        onConfirm={() => { setConfirmingDelete(false); void editing.remove(region).then((done) => { if (done) onDeleted(); }); }}
        onCancel={() => setConfirmingDelete(false)}
      />
    </GlassPanel>
  );
};
