import React from "react";
import type { CharacterEntity, UtteranceEntity } from "@panelflow/shared-types";
import { Chip, EmptyState, GlassPanel } from "@panelflow/ui-v2";
import { characterName } from "./storyModel";

export interface CharactersTabProps {
  projectId: string;
  characters: CharacterEntity[];
  utterances: UtteranceEntity[];
  panels: Array<{ id: string; sequence: number }>;
  /** Reload the narrative after a change. */
  onChanged: () => Promise<unknown>;
}

/** The characters the analysis found, with their role, status and aliases. */
export const CharactersTab: React.FC<CharactersTabProps> = ({ characters }) => {
  if (characters.length === 0) return <GlassPanel blur={false}><EmptyState title="No characters yet" description="Run the story analysis to find the characters." /></GlassPanel>;
  return (
    <ul className="grid grid-cols-1 gap-4 md:grid-cols-2 lg:grid-cols-3" aria-label="Characters">
      {characters.map((c) => (
        <li key={c.character_id} data-character-id={c.character_id}>
          <GlassPanel blur={false} className="grid h-full content-start gap-3 p-4">
            <div className="flex items-start justify-between gap-2">
              <h3 className="flex items-center gap-2 font-display text-sm font-semibold text-fg">{characterName(c)}{c.manual_override && <Chip>Manual</Chip>}</h3>
              <Chip tone={c.role === "PROTAGONIST" ? "accent" : "neutral"}>{c.role}</Chip>
            </div>
            <p className="line-clamp-2 text-sm text-fg-dim">{c.description || "No description."}</p>
            {c.aliases.length > 0 && <div className="flex flex-wrap gap-1">{c.aliases.map((a) => <Chip key={a}>{a}</Chip>)}</div>}
            <p className="border-t border-edge pt-2 text-xs text-fg-faint">{`Status: ${c.status}`}</p>
          </GlassPanel>
        </li>
      ))}
    </ul>
  );
};
