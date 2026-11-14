import React from "react";
import { api } from "@panelflow/api-client";
import type { CharacterEntity, UtteranceEntity } from "@panelflow/shared-types";
import { Button, Dialog, Field, Input, Select } from "@panelflow/ui-v2";
import { refusal } from "../kit/engineReason";
import { characterName, panelLabel, splitPanelChoices } from "./storyModel";

export interface SplitCharacterDialogProps {
  open: boolean;
  projectId: string;
  characters: CharacterEntity[];
  utterances: UtteranceEntity[];
  panels: Array<{ id: string; sequence: number }>;
  onClose: () => void;
  onSplit: () => Promise<unknown>;
}

/** Split part of a character's lines into a new identity. The panels offered are the ones where that character speaks. */
export const SplitCharacterDialog: React.FC<SplitCharacterDialogProps> = ({ open, projectId, characters, utterances, panels, onClose, onSplit }) => {
  const [characterId, setCharacterId] = React.useState("");
  const [newName, setNewName] = React.useState("");
  const [checked, setChecked] = React.useState<string[]>([]);
  const [error, setError] = React.useState<string | null>(null);
  const [splitting, setSplitting] = React.useState(false);
  const busy = React.useRef(false);
  React.useEffect(() => { if (open) { setCharacterId(""); setNewName(""); setChecked([]); setError(null); } }, [open]);

  const choices = characterId ? splitPanelChoices(utterances, characterId) : [];
  const canSplit = Boolean(characterId) && newName.trim() !== "" && checked.length > 0;
  const toggle = (panelId: string) => setChecked((list) => (list.includes(panelId) ? list.filter((p) => p !== panelId) : [...list, panelId]));

  const split = async () => {
    if (!canSplit || busy.current) return;
    busy.current = true;
    setSplitting(true);
    setError(null);
    try {
      await api.splitCharacter(projectId, characterId, newName.trim(), choices.filter((p) => checked.includes(p)));
      await onSplit();
      onClose();
    } catch (err) {
      setError(refusal("Couldn't split the character.", err, "Try again."));
    } finally { busy.current = false; setSplitting(false); }
  };

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => { if (!next) onClose(); }}
      title="Split character identity"
      description="Move the lines in some panels to a new character."
      footer={<><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" loading={splitting} disabled={!canSplit} onClick={() => void split()}>Split identity</Button></>}
    >
      <div className="grid grid-cols-1 gap-3">
        <Field label="Character to split">
          <Select value={characterId} onChange={(e) => { setCharacterId(e.target.value); setChecked([]); }}>
            <option value="">Choose a character</option>
            {characters.map((c) => <option key={c.character_id} value={c.character_id}>{characterName(c)}</option>)}
          </Select>
        </Field>
        <Field label="New character name"><Input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="For example: Mysterious stranger" /></Field>
        <fieldset className="grid gap-2">
          <legend className="text-[13px] font-medium text-fg">Panels where this character speaks</legend>
          {!characterId ? <p className="text-sm text-fg-dim">Choose a character first.</p>
            : choices.length === 0 ? <p className="text-sm text-fg-dim">No lines are attributed to this character, so there is nothing to split off.</p>
            : choices.map((panelId) => {
              const label = panelLabel(panelId, panels);
              return (
                <label key={panelId} className="flex items-center gap-2 text-sm text-fg">
                  <input type="checkbox" aria-label={label} checked={checked.includes(panelId)} onChange={() => toggle(panelId)} />
                  {label}
                </label>
              );
            })}
        </fieldset>
        {error && <p role="alert" className="text-sm text-bad">{error}</p>}
      </div>
    </Dialog>
  );
};
