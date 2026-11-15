import React from "react";
import { api } from "@panelflow/api-client";
import type { CharacterEntity, UtteranceEntity } from "@panelflow/shared-types";
import { Button, Chip, EmptyState, GlassPanel, Select } from "@panelflow/ui-v2";
import { characterName, panelLabel, speakerLabel } from "./storyModel";

const PAGE = 100;

export interface UtterancesTabProps {
  projectId: string;
  utterances: UtteranceEntity[];
  characters: CharacterEntity[];
  panels: Array<{ id: string; sequence: number }>;
  /** Reload the narrative after a change. */
  onChanged: () => Promise<unknown>;
}

/** Source-grounded dialogue, narration and sound effects, with the speaker changeable one line at a time. */
export const UtterancesTab: React.FC<UtterancesTabProps> = ({ projectId, utterances, characters, panels, onChanged }) => {
  const [shown, setShown] = React.useState(PAGE);
  const [pending, setPending] = React.useState<Record<string, string>>({});
  const [failed, setFailed] = React.useState<Record<string, boolean>>({});
  const busy = React.useRef(false); // one speaker change at a time: each one reloads the narrative the next one builds on

  const change = async (u: UtteranceEntity, speaker: string) => {
    if (busy.current) return;
    busy.current = true;
    setFailed((f) => ({ ...f, [u.utterance_id]: false }));
    setPending((p) => ({ ...p, [u.utterance_id]: speaker }));
    try {
      await api.updateTextRegion(projectId, u.text_region_id, { speaker_character_id: speaker, speaker_assignment_method: "MANUAL" });
      await onChanged();
    } catch {
      setFailed((f) => ({ ...f, [u.utterance_id]: true }));
    } finally {
      busy.current = false;
      setPending((p) => { const next = { ...p }; delete next[u.utterance_id]; return next; });
    }
  };

  if (utterances.length === 0) return <GlassPanel blur={false}><EmptyState title="No utterances" description="Dialogue and narration appear here once the story analysis has read the text." /></GlassPanel>;
  const rows = utterances.slice(0, shown);
  const known = new Set(characters.map((c) => c.character_id));
  return (
    <div className="grid grid-cols-1 gap-3">
      <p className="text-sm text-fg-dim">Dialogue, narration and sound effects read from the text. Change the speaker where it is wrong.</p>
      <ul className="grid grid-cols-1 gap-2" aria-label="Utterances">
        {rows.map((u) => {
          const current = pending[u.utterance_id] ?? (u.speaker_character_id && (known.has(u.speaker_character_id) || ["NARRATOR", "SFX"].includes(u.speaker_character_id)) ? u.speaker_character_id : "UNKNOWN");
          return (
            <li key={u.utterance_id} data-utterance-id={u.utterance_id}>
              <GlassPanel blur={false} className="grid grid-cols-1 gap-3 p-3.5 md:grid-cols-[minmax(0,1fr)_auto] md:items-center">
                <div className="grid min-w-0 gap-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <Chip tone={u.utterance_type === "NARRATION" ? "neutral" : "accent"}>{u.utterance_type}</Chip>
                    <span className="text-sm font-medium text-fg">{speakerLabel(u, characters)}</span>
                    <span className="font-data text-xs text-fg-faint">{panelLabel(u.panel_id, panels)}</span>
                  </div>
                  <p className="break-words font-data text-sm text-fg">{`"${u.corrected_text || u.source_text}"`}</p>
                  {failed[u.utterance_id] && <p role="alert" className="text-xs text-bad">Couldn't change the speaker. It was left as it was.</p>}
                </div>
                <Select aria-label={`Speaker for line ${u.sequence}`} className="h-9 text-sm md:w-56" value={current} onChange={(e) => void change(u, e.target.value)}>
                  <option value="UNKNOWN">Unknown</option>
                  <option value="NARRATOR">Narrator</option>
                  <option value="SFX">Sound effect</option>
                  {characters.map((c) => <option key={c.character_id} value={c.character_id}>{characterName(c)}</option>)}
                </Select>
              </GlassPanel>
            </li>
          );
        })}
      </ul>
      {utterances.length > shown && <Button variant="secondary" size="sm" onClick={() => setShown((n) => n + PAGE)}>{`Show more (${utterances.length - shown} left)`}</Button>}
    </div>
  );
};
