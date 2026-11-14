import type {
  CharacterEntity, ContinuityWarningEntity, EventEntity, LLMProviderInfo, NarrativeDocument, PipelineStage, SceneEntity, StoryBeatEntity, UtteranceEntity,
} from "@panelflow/shared-types";

/**
 * The engine's `/characters` and `/scenes` send `id` where the typed entities say `character_id` / `scene_id`
 * (the narrative document sends the typed names). Both are accepted; an item with neither is dropped, never sent as `undefined`.
 */
export function normalizeCharacters(raw: any[] | null | undefined): CharacterEntity[] {
  const out: CharacterEntity[] = [];
  for (const item of raw ?? []) {
    const id = item?.character_id ?? item?.id;
    if (!id) continue;
    out.push({ ...item, character_id: id, aliases: Array.isArray(item.aliases) ? item.aliases : [] });
  }
  return out;
}

export function normalizeScenes(raw: any[] | null | undefined): SceneEntity[] {
  const out: SceneEntity[] = [];
  for (const item of raw ?? []) {
    const id = item?.scene_id ?? item?.id;
    if (!id) continue;
    out.push({ ...item, scene_id: id });
  }
  return out.sort((a, b) => (a.sequence ?? 0) - (b.sequence ?? 0));
}

/** Canonical names are often null in real data; the display name is then the name. */
export function characterName(c: { canonical_name?: string | null; display_name?: string | null }): string {
  return c.canonical_name || c.display_name || "Unnamed character";
}

export interface SceneBlock { scene: SceneEntity; beats: StoryBeatEntity[]; events: EventEntity[] }

export function sceneBlocks(narrative: NarrativeDocument | null, scenes: SceneEntity[]): SceneBlock[] {
  return scenes.map((scene) => {
    const beats = (narrative?.beats ?? []).filter((b) => b.scene_id === scene.scene_id).sort((a, b) => a.sequence - b.sequence);
    const eventIds = new Set(beats.flatMap((b) => b.event_ids ?? []));
    const events = (narrative?.events ?? []).filter((e) => eventIds.has(e.event_id));
    return { scene, beats, events };
  });
}

const SPECIAL_SPEAKERS: Record<string, string> = { NARRATOR: "Narrator", SFX: "Sound effect", UNKNOWN: "Unknown" };

/** Who says an utterance, in words. An id that matches nobody is "Unknown", never the raw id. */
export function speakerLabel(u: Pick<UtteranceEntity, "speaker_character_id">, characters: CharacterEntity[]): string {
  const id = u.speaker_character_id;
  if (!id) return "Unknown";
  if (SPECIAL_SPEAKERS[id]) return SPECIAL_SPEAKERS[id];
  const known = characters.find((c) => c.character_id === id);
  return known ? characterName(known) : "Unknown";
}

export function panelLabel(panelId: string, panels: Array<{ id: string; sequence: number }>): string {
  const known = panels.find((p) => p.id === panelId);
  return known ? `Panel ${known.sequence}` : `Panel …${panelId.slice(-4)}`;
}

export function blockingWarnings(n: NarrativeDocument | null): ContinuityWarningEntity[] {
  return (n?.continuity_warnings ?? []).filter((w) => w.severity === "ERROR" && !w.resolved);
}

export function canApproveStory({ narrative, analyzing }: { narrative: NarrativeDocument | null; analyzing: boolean }): { ok: boolean; reason: string | null } {
  if (!narrative) return { ok: false, reason: "Run the story analysis first." };
  if (analyzing) return { ok: false, reason: "Analysis is still running." };
  const blocking = blockingWarnings(narrative).length;
  if (blocking > 0) return { ok: false, reason: `${blocking} continuity error${blocking === 1 ? "" : "s"} must be resolved first.` };
  return { ok: true, reason: null };
}

const STORY_APPROVED_ONWARD: ReadonlySet<PipelineStage> = new Set<PipelineStage>([
  "STORY_APPROVED", "SCRIPT_GENERATED", "SCRIPT_APPROVED", "VOICE_GENERATED", "AUDIO_APPROVED", "SHOT_PLAN_GENERATED", "MOTION_APPROVED", "RENDERED", "QA_APPROVED", "EXPORTED",
]);

export const isStoryApproved = (stage: PipelineStage) => STORY_APPROVED_ONWARD.has(stage);

export interface ProviderOption { id: string; label: string; healthy: boolean; mock: boolean }

/** The models story analysis can use. A mock provider is never the default; the default is a healthy local model, then a healthy cloud one, else none. */
export function providerChoices(providers: LLMProviderInfo[], settings: Record<string, any> | undefined): { options: ProviderOption[]; defaultId: string | null } {
  const isMock = (p: LLMProviderInfo) => /mock/i.test(p.provider_id) || /mock/i.test(p.provider_name ?? "");
  const options = providers
    .filter((p) => !(settings?.visual_storytelling && isMock(p)))
    .map((p): ProviderOption => ({
      id: p.provider_id,
      mock: isMock(p),
      healthy: p.is_healthy,
      label: isMock(p) ? `${p.provider_name} · Test data only` : `${p.provider_name} · ${p.is_local ? "Local" : "Cloud"} · ${p.is_healthy ? "Online" : "Offline"}`,
    }));
  const real = providers.filter((p) => !isMock(p) && p.is_healthy);
  const pick = real.find((p) => p.is_local) ?? real[0];
  return { options, defaultId: pick?.provider_id ?? null };
}

export function parseList(text: string): string[] {
  return [...new Set(text.split(",").map((part) => part.trim()).filter(Boolean))];
}

/** The panels where a character speaks, in reading order: the choices when splitting that character. */
export function splitPanelChoices(utterances: UtteranceEntity[], characterId: string): string[] {
  const mine = utterances.filter((u) => u.speaker_character_id === characterId).sort((a, b) => a.sequence - b.sequence);
  return [...new Set(mine.map((u) => u.panel_id))];
}
