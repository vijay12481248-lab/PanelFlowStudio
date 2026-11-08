import { useQuery } from "@tanstack/react-query";
import { api } from "@panelflow/api-client";
import type { CharacterEntity, LLMProviderInfo, NarrativeDocument } from "@panelflow/shared-types";
import { useEngine } from "../../../app/providers";
import { normalizeCharacters } from "./storyModel";

export const storyKeys = {
  narrative: (projectId: string) => ["stages", "story", "narrative", projectId] as const,
  providers: ["stages", "story", "providers"] as const,
  panels: (projectId: string) => ["stages", "story", "panels", projectId] as const,
  characters: (projectId: string) => ["stages", "story", "characters", projectId] as const,
};

/** The saved narrative. No narrative is a normal state (the engine answers with an error), shown as "no analysis yet". */
export function useNarrative(projectId: string) {
  const { connected } = useEngine();
  return useQuery<NarrativeDocument | null>({ queryKey: storyKeys.narrative(projectId), queryFn: () => api.getNarrative(projectId).catch(() => null), enabled: connected, retry: false });
}

export function useStoryProviders() {
  const { connected } = useEngine();
  return useQuery<LLMProviderInfo[]>({ queryKey: storyKeys.providers, queryFn: () => api.listLLMProviders(), enabled: connected, retry: false });
}

/** Panel numbers for labels. A failure only means labels fall back to the end of the panel id. */
export function usePanelsLite(projectId: string) {
  const { connected } = useEngine();
  return useQuery<Array<{ id: string; sequence: number }>>({ queryKey: storyKeys.panels(projectId), queryFn: () => api.listPanels(projectId).catch(() => []), enabled: connected, retry: false });
}

/** Characters from the narrative (which carries `character_id`); the character list is only a fallback when the narrative has none. */
export function useStoryCharacters(projectId: string, narrative: NarrativeDocument | null | undefined): CharacterEntity[] {
  const { connected } = useEngine();
  const fromNarrative = normalizeCharacters(narrative?.characters);
  const needFallback = narrative !== undefined && fromNarrative.length === 0;
  const fallback = useQuery<CharacterEntity[]>({
    queryKey: storyKeys.characters(projectId),
    queryFn: async () => normalizeCharacters(await api.listCharacters(projectId).catch(() => [])),
    enabled: connected && needFallback,
    retry: false,
  });
  return fromNarrative.length > 0 ? fromNarrative : fallback.data ?? [];
}
