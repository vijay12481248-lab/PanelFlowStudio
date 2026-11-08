import React from "react";
import type { CharacterEntity, UtteranceEntity } from "@panelflow/shared-types";
import { Button, Chip, EmptyState, GlassPanel } from "@panelflow/ui-v2";
import { EditCharacterDialog } from "./EditCharacterDialog";
import { MergeCharactersDialog } from "./MergeCharactersDialog";
import { SplitCharacterDialog } from "./SplitCharacterDialog";
import { characterName } from "./storyModel";

export interface CharactersTabProps {
  projectId: string;
  characters: CharacterEntity[];
  utterances: UtteranceEntity[];
  panels: Array<{ id: string; sequence: number }>;
  /** Reload the narrative after a change. */
  onChanged: () => Promise<unknown>;
}

/** The characters the analysis found. Merge duplicates, split a mixed-up identity, or edit one. */
export const CharactersTab: React.FC<CharactersTabProps> = ({ projectId, characters, utterances, panels, onChanged }) => {
  const [editing, setEditing] = React.useState<CharacterEntity | null>(null);
  const [merging, setMerging] = React.useState(false);
  const [splitting, setSplitting] = React.useState(false);

  return (
    <div className="grid grid-cols-1 gap-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <p className="text-sm text-fg-dim">Characters and aliases found across the panels. Merge duplicates or split a mixed-up identity.</p>
        <div className="flex gap-2">
          <Button variant="secondary" size="sm" disabled={characters.length < 2} onClick={() => setMerging(true)}>Merge identities</Button>
          <Button variant="secondary" size="sm" disabled={characters.length === 0} onClick={() => setSplitting(true)}>Split identity</Button>
        </div>
      </div>
      {characters.length === 0 ? (
        <GlassPanel blur={false}><EmptyState title="No characters yet" description="Run the story analysis to find the characters." /></GlassPanel>
      ) : (
        <ul className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3" aria-label="Characters">
          {characters.map((c) => (
            <li key={c.character_id} data-character-id={c.character_id}>
              <GlassPanel blur={false} className="grid h-full content-start gap-3 p-4">
                <div className="flex items-start justify-between gap-2">
                  <h3 className="flex flex-wrap items-center gap-2 font-display text-sm font-semibold text-fg">{characterName(c)}{c.manual_override && <Chip>Manual</Chip>}</h3>
                  <Chip tone={c.role === "PROTAGONIST" ? "accent" : "neutral"}>{c.role}</Chip>
                </div>
                <p className="line-clamp-2 text-sm text-fg-dim">{c.description || "No description."}</p>
                {c.aliases.length > 0 && <div className="flex flex-wrap gap-1">{c.aliases.map((a) => <Chip key={a}>{a}</Chip>)}</div>}
                <div className="flex items-center justify-between border-t border-edge pt-2">
                  <p className="text-xs text-fg-faint">{`Status: ${c.status}`}</p>
                  <Button size="sm" variant="ghost" aria-label={`Edit ${characterName(c)}`} onClick={() => setEditing(c)}>Edit</Button>
                </div>
              </GlassPanel>
            </li>
          ))}
        </ul>
      )}
      <EditCharacterDialog projectId={projectId} character={editing} onClose={() => setEditing(null)} onSaved={onChanged} />
      <MergeCharactersDialog open={merging} projectId={projectId} characters={characters} onClose={() => setMerging(false)} onMerged={onChanged} />
      <SplitCharacterDialog open={splitting} projectId={projectId} characters={characters} utterances={utterances} panels={panels} onClose={() => setSplitting(false)} onSplit={onChanged} />
    </div>
  );
};
