import test from "node:test";
import assert from "node:assert/strict";
import type { LLMProviderInfo, NarrativeDocument, UtteranceEntity } from "@panelflow/shared-types";
import {
  blockingWarnings, canApproveStory, characterName, isStoryApproved, normalizeCharacters, normalizeScenes, panelLabel,
  parseList, providerChoices, sceneBlocks, speakerLabel, splitPanelChoices,
} from "../storyModel";

// The engine's real shapes: /characters and /scenes send `id`, and canonical_name is null.
const REAL_CHARS = [
  { id: "c1", display_name: "Shangguan Yulin", canonical_name: null, aliases: ["Yulin"], role: "UNKNOWN", status: "LIKELY" },
  { id: "c2", display_name: "Red Demon", canonical_name: null, role: "UNKNOWN", status: "LIKELY" },
];
const REAL_SCENES = [{ id: "s2", sequence: 2, title: "Second" }, { id: "s1", sequence: 1, title: "First" }];

test("characters are read from character_id or id; items with neither are dropped", () => {
  const out = normalizeCharacters([...REAL_CHARS, { character_id: "c3", display_name: "Luo" }, { display_name: "No id" }, {}, null] as any);
  assert.deepEqual(out.map((c) => c.character_id), ["c1", "c2", "c3"]);
  assert.deepEqual(out[1].aliases, [], "aliases default to an empty list");
  assert.deepEqual(normalizeCharacters(undefined), []);
});

test("scenes are read from scene_id or id and kept in sequence order", () => {
  assert.deepEqual(normalizeScenes([...REAL_SCENES, { title: "no id" }] as any).map((s) => s.scene_id), ["s1", "s2"]);
  assert.deepEqual(normalizeScenes(null), []);
});

test("a character's name is canonical, else display, else a placeholder", () => {
  assert.equal(characterName({ canonical_name: "Yulin", display_name: "Shangguan" }), "Yulin");
  assert.equal(characterName({ canonical_name: null as any, display_name: "Shangguan" }), "Shangguan");
  assert.equal(characterName({ canonical_name: "", display_name: "" }), "Unnamed character");
});

const narrative = {
  scenes: [{ scene_id: "s1", sequence: 1, title: "A" }, { scene_id: "s2", sequence: 2, title: "B" }, { scene_id: "s3", sequence: 3, title: "Empty" }],
  beats: [
    { beat_id: "b2", scene_id: "s1", sequence: 2, event_ids: ["e2"] },
    { beat_id: "b1", scene_id: "s1", sequence: 1, event_ids: ["e1"] },
    { beat_id: "b3", scene_id: "s2", sequence: 1, event_ids: [] },
  ],
  events: [{ event_id: "e1" }, { event_id: "e2" }, { event_id: "e9" }],
} as unknown as NarrativeDocument;

test("beats and events are grouped under the scene they belong to, in order, and an empty scene still appears", () => {
  const blocks = sceneBlocks(narrative, normalizeScenes(narrative.scenes as any));
  assert.deepEqual(blocks.map((b) => b.scene.scene_id), ["s1", "s2", "s3"]);
  assert.deepEqual(blocks[0].beats.map((b) => b.beat_id), ["b1", "b2"]);
  assert.deepEqual(blocks[0].events.map((e) => e.event_id), ["e1", "e2"]);
  assert.deepEqual(blocks[2].beats, []);
  assert.deepEqual(sceneBlocks(null, []), []);
});

test("scenes from the list endpoint (id only) still get their beats once normalised", () => {
  const blocks = sceneBlocks(narrative, normalizeScenes([{ id: "s1", sequence: 1, title: "A" }] as any));
  assert.equal(blocks[0].beats.length, 2);
});

const chars = normalizeCharacters(REAL_CHARS as any);
const utt = (over: Partial<UtteranceEntity>) => ({ utterance_id: "u", text_region_id: "r", panel_id: "p", source_text: "x", corrected_text: "x", utterance_type: "DIALOGUE", sequence: 1, ...over }) as UtteranceEntity;

test("speakers are named, with special values in words and unknown ids never shown raw", () => {
  assert.equal(speakerLabel(utt({ speaker_character_id: "c1" }), chars), "Shangguan Yulin");
  assert.equal(speakerLabel(utt({ speaker_character_id: "NARRATOR" }), chars), "Narrator");
  assert.equal(speakerLabel(utt({ speaker_character_id: "SFX" }), chars), "Sound effect");
  assert.equal(speakerLabel(utt({ speaker_character_id: "UNKNOWN" }), chars), "Unknown");
  assert.equal(speakerLabel(utt({ speaker_character_id: null }), chars), "Unknown");
  assert.equal(speakerLabel(utt({ speaker_character_id: "ghost123" }), chars), "Unknown");
});

test("a panel is labelled by its number, or by the end of its id when it is not in the list", () => {
  assert.equal(panelLabel("p3", [{ id: "p3", sequence: 3 }]), "Panel 3");
  assert.equal(panelLabel("fa4984e4-09eb-4ede-87b2-29722518c211", []), "Panel …c211");
});

test("only unresolved errors block approval", () => {
  const n = { continuity_warnings: [
    { warning_id: "1", severity: "ERROR", resolved: false }, { warning_id: "2", severity: "ERROR", resolved: true },
    { warning_id: "3", severity: "WARNING", resolved: false }, { warning_id: "4", severity: "ERROR", resolved: false },
  ] } as unknown as NarrativeDocument;
  assert.deepEqual(blockingWarnings(n).map((w) => w.warning_id), ["1", "4"]);
  assert.deepEqual(blockingWarnings(null), []);
});

test("approval needs a finished analysis and no blocking errors, and says why not", () => {
  const withErrors = { continuity_warnings: [{ severity: "ERROR", resolved: false }, { severity: "ERROR", resolved: false }] } as unknown as NarrativeDocument;
  const one = { continuity_warnings: [{ severity: "ERROR", resolved: false }] } as unknown as NarrativeDocument;
  const clean = { continuity_warnings: [] } as unknown as NarrativeDocument;
  assert.deepEqual(canApproveStory({ narrative: null, analyzing: false }), { ok: false, reason: "Run the story analysis first." });
  assert.deepEqual(canApproveStory({ narrative: clean, analyzing: true }), { ok: false, reason: "Analysis is still running." });
  assert.equal(canApproveStory({ narrative: withErrors, analyzing: false }).reason, "2 continuity errors must be resolved first.");
  assert.equal(canApproveStory({ narrative: one, analyzing: false }).reason, "1 continuity error must be resolved first.");
  assert.deepEqual(canApproveStory({ narrative: clean, analyzing: false }), { ok: true, reason: null });
});

test("the story counts as approved from STORY_APPROVED onward", () => {
  for (const s of ["RIGHTS_APPROVED", "OCR_APPROVED", "STORY_ANALYZED"] as const) assert.equal(isStoryApproved(s), false, s);
  for (const s of ["STORY_APPROVED", "SCRIPT_GENERATED", "SCRIPT_APPROVED", "AUDIO_APPROVED", "RENDERED", "QA_APPROVED", "EXPORTED"] as const) assert.equal(isStoryApproved(s), true, s);
});

const prov = (id: string, over: Partial<LLMProviderInfo> = {}) => ({ provider_id: id, provider_name: id.toUpperCase(), is_local: true, is_multimodal: true, is_healthy: true, ...over }) as LLMProviderInfo;

test("a mock provider is never the default and is labelled as test data", () => {
  const choice = providerChoices([prov("mock_llm", { provider_name: "Mock Deterministic LLM" }), prov("ollama", { provider_name: "Ollama Local" })], {});
  assert.equal(choice.defaultId, "ollama");
  const mock = choice.options.find((o) => o.id === "mock_llm")!;
  assert.equal(mock.mock, true);
  assert.ok(mock.label.includes("Test data only"));
  assert.equal(choice.options.find((o) => o.id === "ollama")!.label, "Ollama Local · Local · Online");
});

test("with only a mock or an offline provider there is no default", () => {
  assert.equal(providerChoices([prov("mock_llm")], {}).defaultId, null);
  assert.equal(providerChoices([prov("ollama", { is_healthy: false })], {}).defaultId, null);
  assert.equal(providerChoices([], {}).defaultId, null);
});

test("a healthy cloud provider is the default only when no healthy local one exists", () => {
  assert.equal(providerChoices([prov("cloud", { is_local: false }), prov("ollama")], {}).defaultId, "ollama");
  assert.equal(providerChoices([prov("cloud", { is_local: false }), prov("ollama", { is_healthy: false })], {}).defaultId, "cloud");
});

test("visual storytelling projects do not list the mock provider at all", () => {
  const choice = providerChoices([prov("mock_llm"), prov("ollama")], { visual_storytelling: true });
  assert.deepEqual(choice.options.map((o) => o.id), ["ollama"]);
});

test("a comma list is trimmed and de-duplicated", () => {
  assert.deepEqual(parseList("a, b,,a , c"), ["a", "b", "c"]);
  assert.deepEqual(parseList(""), []);
});

test("split choices are the panels where the character speaks, in order, once each", () => {
  const list = [
    utt({ sequence: 3, panel_id: "p3", speaker_character_id: "c1" }), utt({ sequence: 1, panel_id: "p1", speaker_character_id: "c1" }),
    utt({ sequence: 2, panel_id: "p2", speaker_character_id: "c2" }), utt({ sequence: 4, panel_id: "p1", speaker_character_id: "c1" }),
  ];
  assert.deepEqual(splitPanelChoices(list, "c1"), ["p1", "p3"]);
  assert.deepEqual(splitPanelChoices(list, "nobody"), []);
});
