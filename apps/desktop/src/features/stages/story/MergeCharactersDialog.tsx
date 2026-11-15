import React from "react";
import { api } from "@panelflow/api-client";
import type { CharacterEntity } from "@panelflow/shared-types";
import { Button, Dialog, Field, Select } from "@panelflow/ui-v2";
import { refusal } from "../kit/engineReason";
import { characterName } from "./storyModel";

export interface MergeCharactersDialogProps {
  open: boolean;
  projectId: string;
  characters: CharacterEntity[];
  onClose: () => void;
  onMerged: () => Promise<unknown>;
}

/** Merge a duplicate into the identity to keep. Two steps: choose, then confirm that it can't be undone. */
export const MergeCharactersDialog: React.FC<MergeCharactersDialogProps> = ({ open, projectId, characters, onClose, onMerged }) => {
  const [source, setSource] = React.useState("");
  const [target, setTarget] = React.useState("");
  const [step, setStep] = React.useState<"choose" | "confirm">("choose");
  const [fieldError, setFieldError] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [merging, setMerging] = React.useState(false);
  const busy = React.useRef(false);
  React.useEffect(() => { if (open) { setSource(""); setTarget(""); setStep("choose"); setFieldError(null); setError(null); } }, [open]);

  const name = (id: string) => { const c = characters.find((x) => x.character_id === id); return c ? characterName(c) : ""; };
  const review = () => {
    if (!source || !target || source === target) { setFieldError("Choose two different characters."); return; }
    setFieldError(null);
    setStep("confirm");
  };
  const merge = async () => {
    if (busy.current) return;
    busy.current = true;
    setMerging(true);
    setError(null);
    try {
      await api.mergeCharacters(projectId, source, target);
      await onMerged();
      onClose();
    } catch (err) {
      setError(refusal("Couldn't merge the characters.", err, "Try again."));
    } finally { busy.current = false; setMerging(false); }
  };
  const options = (<><option value="">Choose a character</option>{characters.map((c) => <option key={c.character_id} value={c.character_id}>{characterName(c)}</option>)}</>);

  return (
    <Dialog
      open={open}
      onOpenChange={(next) => { if (!next) onClose(); }}
      title="Merge character identities"
      description="Merge a duplicate character into the identity you keep."
      footer={step === "choose"
        ? <><Button variant="ghost" onClick={onClose}>Cancel</Button><Button variant="primary" onClick={review}>Review merge</Button></>
        : <><Button variant="ghost" onClick={() => { setStep("choose"); setError(null); }}>Back</Button><Button variant="danger" loading={merging} onClick={() => void merge()}>Merge identities</Button></>}
    >
      {step === "choose" ? (
        <div className="grid grid-cols-1 gap-3">
          <Field label="Merge this identity (it will be removed)"><Select value={source} onChange={(e) => setSource(e.target.value)}>{options}</Select></Field>
          <Field label="Into this identity (it is kept)" error={fieldError ?? undefined}><Select value={target} onChange={(e) => setTarget(e.target.value)}>{options}</Select></Field>
        </div>
      ) : (
        <div className="grid grid-cols-1 gap-3">
          <p className="text-sm text-fg">{`Merge "${name(source)}" into "${name(target)}"?`}</p>
          <p className="text-sm text-fg-dim">{`This can't be undone. All lines and events of ${name(source)} move to ${name(target)}, and ${name(source)} is removed.`}</p>
          {error && <p role="alert" className="text-sm text-bad">{error}</p>}
        </div>
      )}
    </Dialog>
  );
};
