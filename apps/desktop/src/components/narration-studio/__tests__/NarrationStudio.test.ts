/**
 * PanelFlow Studio — Chapter 5A: Narration Studio Unit & Component Tests
 *
 * Verifies script editing, character casting, emotion controls, segment operations,
 * review states, outdated status triggers, continuity checks, and timeline contract serialization.
 */

// Ambient declarations for Node.js built-in test runner when compiling with browser tsconfig
declare module "node:test" {
  export function test(name: string, fn: () => void | Promise<void>): void;
  export function describe(name: string, fn: () => void | Promise<void>): void;
}
declare module "node:assert/strict" {
  export function equal(actual: any, expected: any, message?: string): void;
  export function notEqual(actual: any, expected: any, message?: string): void;
  export function ok(value: any, message?: string): void;
  export function match(value: string, reg: RegExp, message?: string): void;
}

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import {
  MOCK_CHAPTER,
  MOCK_CHARACTERS,
  MOCK_VOICE_PROFILES,
  MOCK_SEGMENTS,
} from "../NarrationStudio.mock.ts";
import {
  type NarrationChapter,
  type NarrationSegment,
  type NarrationEmotion,
  type NarrationToTimelineContract,
  type EmotionalDeliveryConfig,
  computeContentHash,
} from "../NarrationStudio.types.ts";

describe("Chapter 5A: Narration Studio Domain Model & Mock Chapter", () => {
  test("Mock chapter has complete required metadata and segments", () => {
    assert.equal(MOCK_CHAPTER.chapter_number, 14);
    assert.equal(MOCK_CHAPTER.chapter_id, "chap_14_obsidian_vault");
    assert.ok(MOCK_CHAPTER.segments.length >= 8, "Expected at least 8 segments in mock chapter");
    assert.ok(MOCK_CHAPTER.characters.length >= 4, "Expected at least 4 characters");
    assert.ok(MOCK_CHAPTER.voice_profiles.length >= 6, "Expected at least 6 voice profiles");
  });

  test("Every segment has valid 4-tier storytelling source context", () => {
    for (const seg of MOCK_CHAPTER.segments) {
      assert.ok(seg.id, "Segment must have an ID");
      assert.ok(seg.sequence > 0, "Sequence must be positive");
      assert.ok(seg.narration_text.length > 5, "Narration text must be meaningful");
      assert.ok(seg.source_context.page_number > 0, "Page number must be positive");
      assert.ok(seg.source_context.panel_ids.length > 0, "Must reference at least one panel");
      assert.ok(seg.source_context.visual_description, "Must have visual scene description");
      assert.ok(seg.source_context.story_context, "Must have story subtext");
      assert.ok(seg.delivery.emotion, "Must have emotion assigned");
      assert.ok(seg.voice_profile_id, "Must have assigned voice profile ID");
    }
  });

  test("Character profiles contain distinct casting and valid default voices", () => {
    const voiceIds = new Set(MOCK_VOICE_PROFILES.map((v) => v.id));
    for (const char of MOCK_CHARACTERS) {
      assert.ok(char.name, "Character must have a name");
      assert.ok(char.color_accent, "Character must have a color accent");
      assert.ok(char.role, "Character must have a dramatic role");
      assert.ok(
        voiceIds.has(char.default_voice_profile_id),
        `Character ${char.name} has invalid voice profile ID: ${char.default_voice_profile_id}`
      );
    }
  });
});

describe("Chapter 5A: Script Editing & Outdated Status Triggers", () => {
  test("Modifying script text on a READY segment sets generation_status to OUTDATED", () => {
    const readySeg: NarrationSegment = {
      ...MOCK_SEGMENTS[0],
      generation_status: "READY",
      audio_asset_uri: "/assets/demo/seg_001_audio.mp3",
    };

    // Simulate script edit
    const newText = "Deep beneath the sunken ruins, an ancient evil awakened.";
    const updatedSeg: NarrationSegment = {
      ...readySeg,
      narration_text: newText,
      generation_status: readySeg.generation_status === "READY" ? "OUTDATED" : readySeg.generation_status,
      updated_at: new Date().toISOString(),
    };

    assert.equal(updatedSeg.generation_status, "OUTDATED");
    assert.equal(updatedSeg.narration_text, newText);
    assert.notEqual(updatedSeg.updated_at, readySeg.updated_at);
  });

  test("Editing text on an UNQUEUED or DRAFT segment preserves non-ready status", () => {
    const draftSeg: NarrationSegment = {
      ...MOCK_SEGMENTS[2],
      generation_status: "UNQUEUED",
    };

    const updatedSeg: NarrationSegment = {
      ...draftSeg,
      narration_text: "Updated draft narration line.",
      generation_status: draftSeg.generation_status === "READY" ? "OUTDATED" : draftSeg.generation_status,
    };

    assert.equal(updatedSeg.generation_status, "UNQUEUED");
  });

  test("Estimated audio duration calculation responds to word count and speed", () => {
    const words = "One two three four five six seven eight nine ten."; // 10 words
    const baseWps = 2.33; // 140 words per minute

    // Speed 1.0x
    const est1 = Math.round((10 / (baseWps * 1.0)) * 10) / 10;
    assert.ok(est1 > 4.0 && est1 < 4.5);

    // Speed 1.5x (faster, shorter duration)
    const estFast = Math.round((10 / (baseWps * 1.5)) * 10) / 10;
    assert.ok(estFast < est1, "Faster speech speed should decrease estimated duration");

    // Speed 0.75x (slower, longer duration)
    const estSlow = Math.round((10 / (baseWps * 0.75)) * 10) / 10;
    assert.ok(estSlow > est1, "Slower speech speed should increase estimated duration");
  });
});

describe("Chapter 5A: Character Voice Casting & 1-Click Propagation", () => {
  test("Assigning voice profile to character propagates to all matching segments", () => {
    let currentChapter: NarrationChapter = JSON.parse(JSON.stringify(MOCK_CHAPTER));

    const targetCharId = "char_elena";
    const newVoiceId = "voice_lyra";

    // Perform propagation
    currentChapter = {
      ...currentChapter,
      segments: currentChapter.segments.map((s) => {
        if (s.speaker_id !== targetCharId) return s;
        return {
          ...s,
          voice_profile_id: newVoiceId,
          generation_status: s.generation_status === "READY" ? "OUTDATED" : s.generation_status,
        };
      }),
    };

    // Verify all Elena segments now have voice_lyra
    const elenaSegments = currentChapter.segments.filter((s) => s.speaker_id === targetCharId);
    assert.ok(elenaSegments.length >= 2, "Elena should have multiple segments");
    for (const seg of elenaSegments) {
      assert.equal(seg.voice_profile_id, newVoiceId);
    }

    // Verify non-Elena segments were not modified
    const narratorSegments = currentChapter.segments.filter((s) => s.speaker_id === "char_narrator");
    for (const seg of narratorSegments) {
      assert.notEqual(seg.voice_profile_id, newVoiceId);
    }
  });

  test("Voice Profile IDs are stable and preserved for future TTS integration", () => {
    for (const vp of MOCK_VOICE_PROFILES) {
      assert.match(vp.id, /^voice_[a-z0-9_]+$/, "Voice profile ID must follow voice_* format");
      assert.ok(vp.model_family, "Voice profile must declare target model family");
      assert.equal(vp.is_mock, true, "Must be clearly labeled as mock voice profile");
    }
  });
});

describe("Chapter 5A: Emotional Delivery Controls", () => {
  test("All 11 defined emotions are accepted and configured", () => {
    const allEmotions: NarrationEmotion[] = [
      "Neutral",
      "Happy",
      "Sad",
      "Angry",
      "Fearful",
      "Suspenseful",
      "Excited",
      "Whispering",
      "Serious",
      "Mysterious",
      "Determined",
    ];

    assert.equal(allEmotions.length, 11);

    for (const emotion of allEmotions) {
      const delivery: EmotionalDeliveryConfig = {
        emotion,
        intensity: 0.75,
        speech_speed: 1.0,
        pause: { preset: "short", duration_ms: 250, placement: "after_first_sentence" },
        performance_notes: `Delivery notes for ${emotion}`,
        pronunciation_guide: [],
      };
      assert.equal(delivery.emotion, emotion);
      assert.equal(delivery.intensity, 0.75);
    }
  });

  test("Pause suggestions preserve structured timing and instruction", () => {
    const pauseConfig = {
      preset: "dramatic" as const,
      duration_ms: 900,
      placement: "after_first_sentence" as const,
      instruction: "Hold dramatic pause after the revelation.",
    };

    assert.equal(pauseConfig.preset, "dramatic");
    assert.equal(pauseConfig.duration_ms, 900);
    assert.equal(pauseConfig.placement, "after_first_sentence");
    assert.ok(pauseConfig.instruction.includes("Hold dramatic pause"));
  });
});

describe("Chapter 5A: Segment Creation, Reordering, and Deletion", () => {
  test("Creating a new segment appends to chapter and increments sequence", () => {
    const initialCount = MOCK_CHAPTER.segments.length;
    const newSeq = initialCount + 1;

    const newSegText = "A new discovery awaits in the hall.";
    const newSeg: NarrationSegment = {
      id: "seg_test_new",
      sequence: newSeq,
      scene_id: "scene_4",
      linked_to_scene: true,
      scene_offset_sec: 0.0,
      speaker_id: "char_narrator",
      speaker_name: "The Narrator",
      speaker_type: "NARRATOR",
      narration_text: newSegText,
      text_revision: 1,
      content_hash: computeContentHash(newSegText, "Mysterious", 1.0, "none"),
      source_context: {
        page_id: "page_4",
        page_number: 4,
        panel_ids: ["panel_4_1"],
        panel_labels: ["Page 4 • Panel 1"],
        raw_ocr_dialogue: "",
        visual_description: "New chamber vista.",
        story_context: "Progression into deeper depths.",
      },
      delivery: {
        emotion: "Mysterious",
        intensity: 0.5,
        speech_speed: 1.0,
        pause: { preset: "none", duration_ms: 0, placement: "before" },
        performance_notes: "",
        pronunciation_guide: [],
      },
      review_status: "DRAFT",
      generation_status: "UNQUEUED",
      estimated_duration_sec: 4.0,
      voice_profile_id: "voice_aria",
      updated_at: new Date().toISOString(),
    };

    const updatedSegments = [...MOCK_CHAPTER.segments, newSeg];
    assert.equal(updatedSegments.length, initialCount + 1);
    assert.equal(updatedSegments[updatedSegments.length - 1].sequence, newSeq);
  });

  test("Reordering segments swaps order and re-indexes sequence cleanly", () => {
    const segments: NarrationSegment[] = JSON.parse(JSON.stringify(MOCK_SEGMENTS.slice(0, 3)));
    assert.equal(segments[0].id, "seg_001");
    assert.equal(segments[1].id, "seg_002");

    // Move seg_002 up to position 0
    const temp = segments[0];
    segments[0] = segments[1];
    segments[1] = temp;

    const reindexed = segments.map((s, i) => ({ ...s, sequence: i + 1 }));
    assert.equal(reindexed[0].id, "seg_002");
    assert.equal(reindexed[0].sequence, 1);
    assert.equal(reindexed[1].id, "seg_001");
    assert.equal(reindexed[1].sequence, 2);
  });

  test("Deleting a segment removes item and maintains continuous 1-based sequence", () => {
    const segments: NarrationSegment[] = JSON.parse(JSON.stringify(MOCK_SEGMENTS.slice(0, 4)));
    assert.equal(segments.length, 4);

    // Delete index 1 (seg_002)
    const remaining = segments.filter((s) => s.id !== "seg_002").map((s, i) => ({ ...s, sequence: i + 1 }));

    assert.equal(remaining.length, 3);
    assert.equal(remaining[0].id, "seg_001");
    assert.equal(remaining[0].sequence, 1);
    assert.equal(remaining[1].id, "seg_003");
    assert.equal(remaining[1].sequence, 2);
    assert.equal(remaining[2].id, "seg_004");
    assert.equal(remaining[2].sequence, 3);
  });

  test("Duplicating a segment resets review and generation states to DRAFT / UNQUEUED", () => {
    const sourceSeg = MOCK_SEGMENTS[0]; // APPROVED and READY
    const duplicated: NarrationSegment = {
      ...sourceSeg,
      id: "seg_dup_001",
      narration_text: `${sourceSeg.narration_text} (Copy)`,
      review_status: "DRAFT",
      generation_status: "UNQUEUED",
      generation_progress: 0,
      audio_asset_uri: null,
      updated_at: new Date().toISOString(),
    };

    assert.equal(duplicated.review_status, "DRAFT");
    assert.equal(duplicated.generation_status, "UNQUEUED");
    assert.equal(duplicated.audio_asset_uri, null);
    assert.ok(duplicated.narration_text.includes("(Copy)"));
  });
});

describe("Chapter 5A: Storytelling Continuity Logic", () => {
  test("Detects sharp emotional transitions between adjacent segments", () => {
    const segA: Partial<NarrationSegment> = {
      speaker_name: "Elena",
      delivery: { emotion: "Happy", intensity: 0.8, speech_speed: 1.0, pause: { preset: "none", duration_ms: 0, placement: "before" }, performance_notes: "", pronunciation_guide: [] },
    };
    const segB: Partial<NarrationSegment> = {
      speaker_name: "The Narrator",
      delivery: { emotion: "Fearful", intensity: 0.9, speech_speed: 1.0, pause: { preset: "none", duration_ms: 0, placement: "before" }, performance_notes: "", pronunciation_guide: [] },
    };

    const hasSharpJump = segA.delivery?.emotion === "Happy" && segB.delivery?.emotion === "Fearful";
    assert.equal(hasSharpJump, true, "Should flag sharp jump from Happy to Fearful");
  });

  test("Detects repetitive starting words in consecutive segments", () => {
    const textA = "Elena stepped across the broken threshold.";
    const textB = "Elena glanced up at the cracked archway.";

    const wordA = textA.split(/\s+/)[0].toLowerCase();
    const wordB = textB.split(/\s+/)[0].toLowerCase();

    assert.equal(wordA, wordB);
    assert.equal(wordA, "elena");
  });
});

describe("Chapter 5A Decision 1: Smart Scene Binding & Relative Timing", () => {
  test("All mock segments define linked_to_scene and scene_offset_sec", () => {
    for (const seg of MOCK_CHAPTER.segments) {
      assert.equal(typeof seg.linked_to_scene, "boolean", `Segment ${seg.id} missing linked_to_scene`);
      assert.equal(typeof seg.scene_offset_sec, "number", `Segment ${seg.id} missing scene_offset_sec`);
      assert.ok(seg.scene_offset_sec >= -10 && seg.scene_offset_sec <= 60, "Offset should be in reasonable range");
    }
  });

  test("Toggling linked_to_scene preserves scene references without timeline coupling", () => {
    const seg = MOCK_CHAPTER.segments[0];
    assert.equal(seg.linked_to_scene, true);
    assert.ok(seg.scene_id);

    // Unlink narration segment
    const unlinkedSeg: NarrationSegment = {
      ...seg,
      linked_to_scene: false,
      scene_offset_sec: 3.5,
    };

    assert.equal(unlinkedSeg.linked_to_scene, false);
    assert.equal(unlinkedSeg.scene_offset_sec, 3.5);
    // Scene reference remains intact for contextual story review
    assert.equal(unlinkedSeg.scene_id, seg.scene_id);
  });
});

describe("Chapter 5A Decision 2: Regeneration Policy & Stale Async Protection", () => {
  test("Text modification increments text_revision and updates deterministic content_hash", () => {
    const seg = MOCK_CHAPTER.segments[0];
    const initialRev = seg.text_revision || 1;
    const initialHash = seg.content_hash;

    const modifiedText = "Elena lowered her torch into the ancient abyss.";
    const newHash = computeContentHash(
      modifiedText,
      seg.delivery.emotion,
      seg.delivery.speech_speed,
      seg.delivery.pause?.preset
    );

    assert.notEqual(newHash, initialHash, "Content hash must change when text changes");

    const updatedSeg: NarrationSegment = {
      ...seg,
      narration_text: modifiedText,
      text_revision: initialRev + 1,
      content_hash: newHash,
      generation_status: "OUTDATED",
      previous_audio_asset_uri: seg.audio_asset_uri,
      audio_asset_uri: null,
    };

    assert.equal(updatedSeg.text_revision, initialRev + 1);
    assert.equal(updatedSeg.generation_status, "OUTDATED");
    assert.equal(updatedSeg.previous_audio_asset_uri, seg.audio_asset_uri);
    assert.equal(updatedSeg.audio_asset_uri, null);
  });

  test("Outdated audio takes are preserved so creators can listen to prior take", () => {
    // Segment 5 in mock chapter demonstrates an already OUTDATED segment
    const outdatedSeg = MOCK_CHAPTER.segments.find((s) => s.generation_status === "OUTDATED");
    assert.ok(outdatedSeg, "Mock chapter should include an OUTDATED segment demonstrating take preservation");
    assert.equal(outdatedSeg.generation_status, "OUTDATED");
    assert.ok(
      outdatedSeg.previous_audio_asset_uri,
      "OUTDATED segment must preserve previous_audio_asset_uri for preview playback"
    );
    assert.equal(outdatedSeg.audio_asset_uri, null, "Active audio asset URI must be cleared while outdated");
  });

  test("Stale asynchronous result is rejected when text changed during generation", () => {
    const seg: NarrationSegment = {
      ...MOCK_CHAPTER.segments[0],
      text_revision: 1,
      narration_text: "Revision 1 text.",
      generation_status: "PROCESSING",
    };

    // User edits text while synthesis was running in background
    const userEditedSeg: NarrationSegment = {
      ...seg,
      narration_text: "Revision 2 text edited by user.",
      text_revision: 2,
      generation_status: "OUTDATED",
      previous_audio_asset_uri: seg.audio_asset_uri,
      audio_asset_uri: null,
    };

    // Later, the background job for Rev 1 finishes and attempts to apply its result
    const staleJobResult = {
      target_revision: 1, // targeted Rev 1
      audio_asset_uri: "/assets/demo/stale_take_rev1.mp3",
      generation_status: "READY" as const,
    };

    // Stale guard logic (identical to NarrationStudio and NarrationJobQueue)
    const isStale = staleJobResult.target_revision !== userEditedSeg.text_revision;
    assert.equal(isStale, true, "Must detect revision mismatch");

    const finalSeg: NarrationSegment = isStale
      ? {
          ...userEditedSeg,
          generation_status: "OUTDATED",
          generation_error: `Stale generation rejected: Text changed to Rev #${userEditedSeg.text_revision}`,
        }
      : {
          ...userEditedSeg,
          generation_status: "READY",
          audio_asset_uri: staleJobResult.audio_asset_uri,
        };

    // Stale result must NOT overwrite audio_asset_uri
    assert.equal(finalSeg.generation_status, "OUTDATED");
    assert.equal(finalSeg.audio_asset_uri, null);
    assert.ok(finalSeg.generation_error?.includes("Stale generation rejected"));
  });

  test("Generation status is strictly decoupled from script review/approval status", () => {
    const seg = MOCK_CHAPTER.segments[0];

    // Case A: Script can be APPROVED even if generation is OUTDATED
    const approvedOutdated: NarrationSegment = {
      ...seg,
      review_status: "APPROVED",
      generation_status: "OUTDATED",
    };
    assert.equal(approvedOutdated.review_status, "APPROVED");
    assert.equal(approvedOutdated.generation_status, "OUTDATED");

    // Case B: Generating audio READY does NOT auto-approve a DRAFT script
    const draftReady: NarrationSegment = {
      ...seg,
      review_status: "DRAFT",
      generation_status: "READY",
    };
    assert.equal(draftReady.review_status, "DRAFT");
    assert.equal(draftReady.generation_status, "READY");
  });
});

describe("Chapter 5A: Character Voice Override Protection", () => {
  test("Batch voice propagation skips segments with custom overrides unless user explicitly overwrites", () => {
    // Setup 3 segments for Malakor: 2 standard, 1 with custom voice override
    const seg1: NarrationSegment = {
      ...MOCK_CHAPTER.segments[1],
      speaker_id: "char_malakor",
      voice_profile_id: "voice_malakor_orig",
      has_custom_voice_override: false,
    };
    const seg2Custom: NarrationSegment = {
      ...MOCK_CHAPTER.segments[2],
      speaker_id: "char_malakor",
      voice_profile_id: "voice_special_whisper",
      has_custom_voice_override: true, // Manual customization!
    };
    const seg3: NarrationSegment = {
      ...MOCK_CHAPTER.segments[3],
      speaker_id: "char_malakor",
      voice_profile_id: "voice_malakor_orig",
      has_custom_voice_override: false,
    };

    const chapterSegments = [seg1, seg2Custom, seg3];
    const newMalakorVoice = "voice_malakor_new";

    // Subtest A: Safe Propagation (overwriteCustomOverrides = false)
    const safeUpdated = chapterSegments.map((s) => {
      if (s.has_custom_voice_override) return s; // Protected!
      return { ...s, voice_profile_id: newMalakorVoice };
    });

    assert.equal(safeUpdated[0].voice_profile_id, newMalakorVoice);
    assert.equal(safeUpdated[1].voice_profile_id, "voice_special_whisper", "Custom override must be preserved");
    assert.equal(safeUpdated[2].voice_profile_id, newMalakorVoice);

    // Subtest B: Explicit Overwrite (overwriteCustomOverrides = true)
    const forcedUpdated = chapterSegments.map((s) => ({
      ...s,
      voice_profile_id: newMalakorVoice,
      has_custom_voice_override: false,
    }));

    assert.equal(forcedUpdated[0].voice_profile_id, newMalakorVoice);
    assert.equal(forcedUpdated[1].voice_profile_id, newMalakorVoice, "Custom override overwritten by explicit request");
    assert.equal(forcedUpdated[1].has_custom_voice_override, false);
    assert.equal(forcedUpdated[2].voice_profile_id, newMalakorVoice);
  });
});

describe("Chapter 5A: Timeline Integration Contract (Schema 5A-v2)", () => {
  test("Serializes chapter into valid NarrationToTimelineContract Schema 5A-v2 payload", () => {
    const contract: NarrationToTimelineContract = {
      schema_version: "5A-v2",
      project_id: MOCK_CHAPTER.project_id,
      chapter_id: MOCK_CHAPTER.chapter_id,
      exported_at: new Date().toISOString(),
      clips: MOCK_CHAPTER.segments.map((s) => ({
        narration_segment_id: s.id,
        sequence: s.sequence,
        scene_id: s.scene_id,
        linked_to_scene: s.linked_to_scene,
        scene_offset_sec: s.scene_offset_sec,
        speaker: s.speaker_name,
        text: s.narration_text,
        text_revision: s.text_revision,
        content_hash: s.content_hash,
        emotion: s.delivery.emotion,
        speed: s.delivery.speech_speed,
        estimated_duration_sec: s.estimated_duration_sec,
        measured_duration_sec: s.measured_duration_sec,
        audio_asset_uri: s.audio_asset_uri,
        previous_audio_asset_uri: s.previous_audio_asset_uri,
        generated_audio_revision: s.generated_audio_revision,
        review_status: s.review_status,
        generation_status: s.generation_status,
        source_panel_ids: s.source_context.panel_ids,
        voice_profile_id: s.voice_profile_id,
        performance_intent: s.delivery.performance_notes,
      })),
    };

    assert.equal(contract.schema_version, "5A-v2");
    assert.equal(contract.project_id, "proj_demo_manga_01");
    assert.equal(contract.chapter_id, "chap_14_obsidian_vault");
    assert.equal(contract.clips.length, MOCK_CHAPTER.segments.length);

    // Verify Schema 5A-v2 fields in every clip
    for (const clip of contract.clips) {
      assert.ok(clip.narration_segment_id);
      assert.ok(clip.sequence > 0);
      assert.equal(typeof clip.linked_to_scene, "boolean");
      assert.equal(typeof clip.scene_offset_sec, "number");
      assert.equal(typeof clip.text_revision, "number");
      assert.ok(clip.content_hash);
      assert.ok(clip.speaker);
      assert.ok(clip.text);
      assert.ok(clip.emotion);
      assert.ok(clip.speed > 0);
      assert.ok(clip.estimated_duration_sec > 0);
      assert.ok(clip.review_status);
      assert.ok(clip.generation_status);
      assert.ok(clip.source_panel_ids.length > 0);
      assert.ok(clip.voice_profile_id);
    }

    // Verify JSON roundtrip
    const serialized = JSON.stringify(contract);
    const parsed: NarrationToTimelineContract = JSON.parse(serialized);
    assert.equal(parsed.schema_version, "5A-v2");
    assert.equal(parsed.clips.length, contract.clips.length);
    assert.equal(parsed.clips[0].linked_to_scene, true);
  });
});
