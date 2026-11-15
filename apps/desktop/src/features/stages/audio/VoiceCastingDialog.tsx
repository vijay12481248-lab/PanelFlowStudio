import React from "react";
import type { CharacterEntity } from "@panelflow/shared-types";
import { Button, Dialog, Field, Select } from "@panelflow/ui-v2";
import { castingValue, narratorVoice, setCharacterVoice, setNarratorVoice, type Castable, type Casting, type Voice } from "./casting";

export interface VoiceCastingDialogProps {
  open: boolean;
  characters: CharacterEntity[];
  voices: Voice[];
  /** True when the engine's voice list could not be loaded. */
  voicesFailed: boolean;
  casting: Casting;
  onClose: () => void;
  onSave: (casting: Casting) => void;
  onSaveAndGenerate: (casting: Casting) => void;
}

/** One voice per speaker, chosen from the voices the engine reports. Automatic leaves the choice to the engine. */
export const VoiceCastingDialog: React.FC<VoiceCastingDialogProps> = ({ open, characters, voices, voicesFailed, casting, onClose, onSave, onSaveAndGenerate }) => {
  const [draft, setDraft] = React.useState<Casting>(casting);
  React.useEffect(() => { if (open) setDraft(casting); }, [open]); // eslint-disable-line react-hooks/exhaustive-deps

  /** A saved voice the engine no longer lists still shows, so it is not silently replaced. */
  const options = (current: string) => (
    <>
      <option value="">Automatic</option>
      {voices.map((v) => <option key={v.id} value={v.id}>{v.name}</option>)}
      {current && !voices.some((v) => v.id === current) && <option value={current}>{`${current} (saved)`}</option>}
    </>
  );
  const narrator = narratorVoice(draft);

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => { if (!next) onClose(); }}
      title="Voice casting"
      description="Choose a voice for the narrator and for each character. Automatic leaves the choice to the engine."
      footer={
        <>
          <Button variant="ghost" onClick={onClose}>Cancel</Button>
          <Button variant="secondary" onClick={() => onSave(draft)}>Save casting</Button>
          <Button variant="primary" onClick={() => onSaveAndGenerate(draft)}>Save and generate</Button>
        </>
      }
    >
      <div className="grid grid-cols-1 gap-4">
        {voicesFailed && <p className="text-sm text-warn">Couldn't load the voice list. The engine's default voices will be used.</p>}
        {!voicesFailed && voices.length === 0 && <p className="text-sm text-fg-dim">The engine reported no voices, so the engine's defaults will be used.</p>}
        <Field label="Narrator voice">
          <Select aria-label="Narrator voice" value={narrator} onChange={(e) => setDraft((d) => setNarratorVoice(d, e.target.value))}>{options(narrator)}</Select>
        </Field>
        {characters.length === 0 ? (
          <p className="rounded-ctl border border-dashed border-edge p-3 text-sm text-fg-dim">No characters found yet. The narrator voice is used for every line.</p>
        ) : (
          characters.map((entity) => {
            const character = entity as Castable & CharacterEntity; // the engine sends `id`, which the typed entity lacks
            const name = character.canonical_name || character.display_name || "Unnamed character";
            const current = castingValue(draft, character);
            return (
              <Field key={character.character_id || character.id || name} label={name} hint={character.aliases?.length ? `Also called ${character.aliases.join(", ")}` : undefined}>
                <Select aria-label={`Voice for ${name}`} value={current} onChange={(e) => setDraft((d) => setCharacterVoice(d, character, e.target.value))}>{options(current)}</Select>
              </Field>
            );
          })
        )}
      </div>
    </Dialog>
  );
};
