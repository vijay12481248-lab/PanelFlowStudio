import { useQuery } from "@tanstack/react-query";
import { api } from "@panelflow/api-client";
import type { CharacterEntity, OCREngineInfo, TextRegion } from "@panelflow/shared-types";
import { useEngine } from "../../../app/providers";
import { normalizeCharacters } from "../story/storyModel";

export const ocrKeys = {
  regions: (projectId: string) => ["stages", "ocr", "regions", projectId] as const,
  engines: ["stages", "ocr", "engines"] as const,
  characters: (projectId: string) => ["stages", "ocr", "characters", projectId] as const,
};

export function useTextRegions(projectId: string) {
  const { connected } = useEngine();
  return useQuery<TextRegion[]>({ queryKey: ocrKeys.regions(projectId), queryFn: () => api.listTextRegions(projectId), enabled: connected, retry: 1 });
}

export function useOcrEngines() {
  const { connected } = useEngine();
  return useQuery<OCREngineInfo[]>({ queryKey: ocrKeys.engines, queryFn: () => api.listOCREngines(), enabled: connected, retry: 1 });
}

/** Characters for the speaker choice. Not having them is not an error: the choices are then Unknown, Narrator and Sound effect. */
export function useCharacters(projectId: string) {
  const { connected } = useEngine();
  return useQuery<CharacterEntity[]>({ queryKey: ocrKeys.characters(projectId), queryFn: async () => normalizeCharacters(await api.listCharacters(projectId).catch(() => [])), enabled: connected, retry: false });
}
