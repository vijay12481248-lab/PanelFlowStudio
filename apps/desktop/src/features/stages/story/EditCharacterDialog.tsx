import React from "react";
import { api } from "@panelflow/api-client";
import type { CharacterEntity } from "@panelflow/shared-types";
import { Button, Dialog, Field, Input, Select } from "@panelflow/ui-v2";
import { refusal } from "../kit/engineReason";
import { parseList } from "./storyModel";

const ROLES = ["PROTAGONIST", "ANTAGONIST", "SUPPORTING", "MINOR", "UNKNOWN"] as const;
const STATUSES = ["CONFIRMED", "LIKELY", "UNCERTAIN", "MANUAL"] as const;

interface Form { canonical: string; display: string; role: string; status: string; aliases: string; description: string }

const formOf = (c: CharacterEntity | null): Form => ({
  canonical: c?.canonical_name ?? "", display: c?.display_name ?? "", role: c?.role ?? "UNKNOWN", status: c?.status ?? "LIKELY",
  aliases: (c?.aliases ?? []).join(", "), description: c?.description ?? "",
});

/** Only the fields the person changed. The old form sent every field, turning a null canonical name into an empty string. */
export function characterPatch(c: CharacterEntity, form: Form): Record<string, unknown> {
  const patch: Record<string, unknown> = {};
  if (form.canonical.trim() !== (c.canonical_name ?? "")) patch.canonical_name = form.canonical.trim();
  if (form.display.trim() !== (c.display_name ?? "")) patch.display_name = form.display.trim();
  if (form.role !== c.role) patch.role = form.role;
  if (form.status !== c.status) patch.status = form.status;
  const aliases = parseList(form.aliases);
  const before = c.aliases ?? [];
  if (aliases.length !== before.length || aliases.some((a, i) => a !== before[i])) patch.aliases = aliases;
  if (form.description.trim() !== (c.description ?? "").trim()) patch.description = form.description.trim();
  return patch;
}

export interface EditCharacterDialogProps {
  projectId: string;
  /** The character being edited; the dialog is open while this is set. */
  character: CharacterEntity | null;
  onClose: () => void;
  /** Called after a successful save, before the dialog closes. */
  onSaved: () => Promise<unknown>;
}

export const EditCharacterDialog: React.FC<EditCharacterDialogProps> = ({ projectId, character, onClose, onSaved }) => {
  const [form, setForm] = React.useState<Form>(() => formOf(character));
  const [saving, setSaving] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const busy = React.useRef(false);
  React.useEffect(() => { setForm(formOf(character)); setError(null); }, [character?.character_id]); // eslint-disable-line react-hooks/exhaustive-deps

  const set = (key: keyof Form) => (value: string) => setForm((f) => ({ ...f, [key]: value }));
  const patch = character ? characterPatch(character, form) : {};
  const blankName = form.display.trim() === "";
  const canSave = Boolean(character) && !blankName && Object.keys(patch).length > 0;

  const save = async () => {
    if (!character || !canSave || busy.current) return;
    busy.current = true;
    setSaving(true);
    setError(null);
    try {
      await api.updateCharacter(projectId, character.character_id, patch);
      await onSaved();
      onClose();
    } catch (err) {
      setError(refusal("Couldn't save the character.", err, "Try again."));
    } finally { busy.current = false; setSaving(false); }
  };

  return (
    <Dialog
      open={character !== null}
      onOpenChange={(open) => { if (!open) onClose(); }}
      title="Edit character identity"
      description="Change how this character is named and described. Only the fields you change are saved."
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" loading={saving} disabled={!canSave} onClick={() => void save()}>Save identity</Button></>}
    >
      <div className="grid grid-cols-1 gap-3">
        <Field label="Canonical name"><Input value={form.canonical} onChange={(e) => set("canonical")(e.target.value)} /></Field>
        <Field label="Display name" error={blankName ? "Enter a name." : undefined}><Input value={form.display} onChange={(e) => set("display")(e.target.value)} /></Field>
        <Field label="Role"><Select value={form.role} onChange={(e) => set("role")(e.target.value)}>{ROLES.map((r) => <option key={r} value={r}>{r}</option>)}</Select></Field>
        <Field label="Status"><Select value={form.status} onChange={(e) => set("status")(e.target.value)}>{STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}</Select></Field>
        <Field label="Aliases (comma separated)"><Input value={form.aliases} onChange={(e) => set("aliases")(e.target.value)} /></Field>
        <label className="grid gap-1.5 text-[13px] font-medium text-fg">
          Description
          <textarea rows={3} value={form.description} onChange={(e) => set("description")(e.target.value)} className="w-full rounded-ctl border border-edge bg-glass p-3 text-sm font-normal text-fg focus-visible:outline-2 focus-visible:outline-info" />
        </label>
        {error && <p role="alert" className="text-sm text-bad">{error}</p>}
      </div>
    </Dialog>
  );
};
