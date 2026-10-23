/**
 * PanelFlow Studio — Chapter 5B: Story Editor Narration Adapter & Integration Tests
 *
 * Verifies bidirectional sync between NarrationChapter and Timeline NarrationClips,
 * Smart Scene Binding with relative offsets, ripple shifts, unlinking, script editing
 * invalidation triggers, stale async result protection via revision identity,
 * and Schema 5A-v2 contract synchronization.
 */

// Ambient declarations for Node.js built-in test runner
declare module "node:test" {
  export function test(name: string, fn: () => void | Promise<void>): void;
  export function describe(name: string, fn: () => void | Promise<void>): void;
}
declare module "node:assert/strict" {
  export function equal(actual: any, expected: any, message?: string): void;
  export function notEqual(actual: any, expected: any, message?: string): void;
  export function ok(value: any, message?: string): void;
  export function deepEqual(actual: any, expected: any, message?: string): void;
}

import { test, describe } from "node:test";
import assert from "node:assert/strict";
import type { VideoScene, NarrationClip } from "@panelflow/shared-types";
import {
  buildInitialNarrationChapter,
  syncChapterToTimelineClips,
  synchronizeChapterWithTimeline,
  relinkClipToScene,
  unlinkClipFromScene,
  rippleShiftLinkedNarration,
  updateClipScriptText,
  applyGeneratedAudioResult,
  syncTimelineContractToState,
  estimateReadingDuration,
} from "../narrationAdapter.ts";
import type {
  NarrationChapter,
  NarrationToTimelineContract,
} from "../../narration-studio/NarrationStudio.types.ts";

// Helper fixture for test scenes
function createMockScenes(): VideoScene[] {
  return [
    {
      id: "scene_01",
      sequence: 1,
      title: "Scene 1 — Obsidian Gateway",
      start_time_sec: 0.0,
      duration_sec: 4.0,
      transition_in: "fade",
      layers: [
        {
          id: "layer_01",
          source_page_id: "page_01",
          source_panel_id: "panel_01_01",
          image_url: "/panels/p1.png",
          page_sequence: 1,
          crop: { x: 0, y: 0, width: 800, height: 600 },
          transform: { x: 0, y: 0, scale: 1.0, rotation: 0, opacity: 1.0, z_index: 1 },
          start_offset_sec: 0,
          duration_sec: 4.0,
        },
      ],
    },
    {
      id: "scene_02",
      sequence: 2,
      title: "Scene 2 — Pulse in the Dark",
      start_time_sec: 4.0,
      duration_sec: 5.0,
      transition_in: "none",
      layers: [
        {
          id: "layer_02",
          source_page_id: "page_01",
          source_panel_id: "panel_01_02",
          image_url: "/panels/p2.png",
          page_sequence: 1,
          crop: { x: 0, y: 0, width: 800, height: 600 },
          transform: { x: 0, y: 0, scale: 1.0, rotation: 0, opacity: 1.0, z_index: 1 },
          start_offset_sec: 0,
          duration_sec: 5.0,
        },
      ],
    },
    {
      id: "scene_03",
      sequence: 3,
      title: "Scene 3 — Ancient Seal",
      start_time_sec: 9.0,
      duration_sec: 6.0,
      transition_in: "dissolve",
      layers: [
        {
          id: "layer_03",
          source_page_id: "page_02",
          source_panel_id: "panel_02_01",
          image_url: "/panels/p3.png",
          page_sequence: 2,
          crop: { x: 0, y: 0, width: 800, height: 600 },
          transform: { x: 0, y: 0, scale: 1.0, rotation: 0, opacity: 1.0, z_index: 1 },
          start_offset_sec: 0,
          duration_sec: 6.0,
        },
      ],
    },
  ];
}

describe("Chapter 5B: Chapter Narration Initialization & Duration Estimation", () => {
  test("estimateReadingDuration calculates duration based on speech rate and speed", () => {
    const text = "Beneath the shattered pillars of the Obsidian Vault, a forgotten pulse echoed through the stone.";
    const durNormal = estimateReadingDuration(text, 1.0);
    const durFast = estimateReadingDuration(text, 1.5);
    const durSlow = estimateReadingDuration(text, 0.75);

    assert.ok(durNormal > 4.0 && durNormal < 10.0, "Normal reading should be ~6-8s");
    assert.ok(durFast < durNormal, "Faster speed should yield shorter duration");
    assert.ok(durSlow > durNormal, "Slower speed should yield longer duration");
  });

  test("buildInitialNarrationChapter creates structured chapter from video scenes", () => {
    const scenes = createMockScenes();
    const chapter = buildInitialNarrationChapter("proj_test", "Demon Emperor", scenes);

    assert.equal(chapter.project_id, "proj_test");
    assert.equal(chapter.segments.length, 3);
    assert.equal(chapter.segments[0].scene_id, "scene_01");
    assert.equal(chapter.segments[1].scene_id, "scene_02");
    assert.equal(chapter.segments[2].scene_id, "scene_03");
    assert.equal(chapter.segments[0].linked_to_scene, true);
    assert.equal(chapter.segments[0].scene_offset_sec, 0.0);
    assert.equal(chapter.segments[0].text_revision, 1);
    assert.ok(chapter.segments[0].content_hash.length > 0);
  });
});

describe("Chapter 5B: Smart Scene Binding & Bidirectional Sync", () => {
  test("syncChapterToTimelineClips aligns linked narration with scene start and preserves offset", () => {
    const scenes = createMockScenes();
    const chapter = buildInitialNarrationChapter("proj_test", "Demon Emperor", scenes);

    // Give segment 2 an explicit 1.5s offset
    chapter.segments[1].scene_offset_sec = 1.5;

    const clips = syncChapterToTimelineClips(chapter, scenes);

    assert.equal(clips.length, 3);
    // Scene 1 starts at 0.0 -> clip start = 0.0
    assert.equal(clips[0].start_time_sec, 0.0);
    assert.equal(clips[0].scene_id, "scene_01");
    assert.equal(clips[0].linked_to_scene, true);

    // Scene 2 starts at 4.0 -> clip start = 4.0 + 1.5 = 5.5
    assert.equal(clips[1].start_time_sec, 5.5);
    assert.equal(clips[1].scene_id, "scene_02");
    assert.equal(clips[1].scene_offset_sec, 1.5);
    assert.equal(clips[1].linked_to_scene, true);
  });

  test("rippleShiftLinkedNarration moves linked clips while strictly preserving scene_offset_sec", () => {
    const scenes = createMockScenes();
    const chapter = buildInitialNarrationChapter("proj_test", "Demon Emperor", scenes);
    chapter.segments[1].scene_offset_sec = 1.2;

    const initialClips = syncChapterToTimelineClips(chapter, scenes);
    assert.equal(initialClips[1].start_time_sec, 5.2);

    // Trim Scene 1: expand duration from 4.0 to 7.0 seconds (ripples scene 2 start to 7.0)
    const shiftedScenes: VideoScene[] = [
      { ...scenes[0], duration_sec: 7.0 },
      { ...scenes[1], start_time_sec: 7.0 },
      { ...scenes[2], start_time_sec: 12.0 },
    ];

    const shiftedClips = rippleShiftLinkedNarration(shiftedScenes, initialClips);

    // Scene 2 starts at 7.0 -> clip 2 should be at 7.0 + 1.2 = 8.2s
    assert.equal(shiftedClips[1].start_time_sec, 8.2);
    assert.equal(shiftedClips[1].scene_offset_sec, 1.2);

    // Clip 1 starts at 0.0 + 0 = 0.0s
    assert.equal(shiftedClips[0].start_time_sec, 0.0);
  });

  test("Unlinked narration remains at exact absolute coordinates when scenes shift", () => {
    const scenes = createMockScenes();
    const chapter = buildInitialNarrationChapter("proj_test", "Demon Emperor", scenes);

    const initialClips = syncChapterToTimelineClips(chapter, scenes);

    // Unlink clip 2
    const unlinkedClip2 = unlinkClipFromScene(initialClips[1]);
    assert.equal(unlinkedClip2.linked_to_scene, false);
    assert.equal(unlinkedClip2.start_time_sec, 4.0);
    assert.equal(unlinkedClip2.scene_id, "scene_02", "Retains scene context reference");

    const mixedClips = [initialClips[0], unlinkedClip2, initialClips[2]];

    // Reorder scenes or shift scene 2 start time to 10.0s
    const movedScenes: VideoScene[] = [
      { ...scenes[0], duration_sec: 10.0 },
      { ...scenes[1], start_time_sec: 10.0 },
      { ...scenes[2], start_time_sec: 15.0 },
    ];

    const resynced = rippleShiftLinkedNarration(movedScenes, mixedClips);

    // Unlinked clip 2 MUST remain at 4.0s
    assert.equal(resynced[1].start_time_sec, 4.0, "Unlinked clip should not move when scene shifts");
    assert.equal(resynced[1].linked_to_scene, false);

    // Linked clip 3 MUST move to 15.0s
    assert.equal(resynced[2].start_time_sec, 15.0);
  });

  test("relinkClipToScene supports snap_to_start and preserve_offset modes", () => {
    const scenes = createMockScenes();
    const floatingClip: NarrationClip = {
      id: "narr_float",
      speaker: "Aria",
      text: "A floating voiceover spanning cutscenes.",
      emotion: "Mysterious",
      speed: 1.0,
      status: "READY",
      start_time_sec: 6.5,
      duration_sec: 3.0,
      linked_to_scene: false,
    };

    // Mode 1: snap_to_start on Scene 2 (start 4.0) -> offset 0, start 4.0
    const snapped = relinkClipToScene(floatingClip, scenes[1], "snap_to_start");
    assert.equal(snapped.linked_to_scene, true);
    assert.equal(snapped.scene_id, "scene_02");
    assert.equal(snapped.scene_offset_sec, 0.0);
    assert.equal(snapped.start_time_sec, 4.0);

    // Mode 2: preserve_offset on Scene 2 (start 4.0) -> offset = 6.5 - 4.0 = 2.5
    const preserved = relinkClipToScene(floatingClip, scenes[1], "preserve_offset");
    assert.equal(preserved.linked_to_scene, true);
    assert.equal(preserved.scene_id, "scene_02");
    assert.equal(preserved.scene_offset_sec, 2.5);
    assert.equal(preserved.start_time_sec, 6.5);
  });

  test("Scene deletion safety: missing parent scene converts linked clips to floating unlinked clips", () => {
    const scenes = createMockScenes();
    const chapter = buildInitialNarrationChapter("proj_test", "Demon Emperor", scenes);
    const initialClips = syncChapterToTimelineClips(chapter, scenes);

    // Initial clip 2 is linked to scene_02 at start_time_sec = 4.0s
    assert.equal(initialClips[1].scene_id, "scene_02");
    assert.equal(initialClips[1].linked_to_scene, true);
    assert.equal(initialClips[1].start_time_sec, 4.0);

    // Simulate scene_02 deletion: remaining scenes are scene_01 (4s) and scene_03 (start 4s)
    const scenesWith02Deleted: VideoScene[] = [
      scenes[0], // start 0s, dur 4s
      { ...scenes[2], sequence: 2, start_time_sec: 4.0 }, // moved left from 9s to 4s
    ];

    const safeClips = rippleShiftLinkedNarration(scenesWith02Deleted, initialClips);

    // Clip 1 (scene_01) remains linked at 0.0s
    assert.equal(safeClips[0].linked_to_scene, true);
    assert.equal(safeClips[0].start_time_sec, 0.0);

    // Clip 2 (scene_02 was deleted) MUST be safely converted to unlinked floating clip
    // and preserve its exact absolute start time (4.0s) without dangling references!
    assert.equal(safeClips[1].linked_to_scene, false);
    assert.equal(safeClips[1].start_time_sec, 4.0);
    assert.equal(safeClips[1].text, initialClips[1].text);

    // Clip 3 (scene_03) rippled to 4.0s
    assert.equal(safeClips[2].linked_to_scene, true);
    assert.equal(safeClips[2].start_time_sec, 4.0);
  });
});

describe("Chapter 5B: Audio Regeneration Policy & Invalidation", () => {
  test("Editing narration text on a READY clip increments revision and marks OUTDATED", () => {
    const scenes = createMockScenes();
    const chapter = buildInitialNarrationChapter("proj_test", "Demon Emperor", scenes);
    const clips = syncChapterToTimelineClips(chapter, scenes);

    const readyClip = clips[0];
    assert.equal(readyClip.status, "READY");
    assert.equal(readyClip.text_revision, 1);
    const priorAudio = readyClip.audio_url;
    assert.ok(priorAudio, "Initial clip should have audio URL");

    // Edit text
    const newText = "The ancient chamber trembled as the seal ignited.";
    const { updatedClip, updatedChapter } = updateClipScriptText(readyClip, newText, chapter);

    // Verify clip invalidation & take preservation
    assert.equal(updatedClip.text, newText);
    assert.equal(updatedClip.text_revision, 2, "Text revision must increment to 2");
    assert.equal(updatedClip.status, "OUTDATED", "Status must be OUTDATED");
    assert.equal(updatedClip.previous_audio_asset_uri, priorAudio, "Previous take must be preserved");
    assert.equal(updatedClip.audio_url, undefined, "Active audio asset must be cleared until regenerated");
    assert.notEqual(updatedClip.content_hash, readyClip.content_hash, "Content hash must update");

    // Verify chapter segment synchronization
    const seg = updatedChapter?.segments.find((s) => s.id === readyClip.id);
    assert.ok(seg);
    assert.equal(seg?.narration_text, newText);
    assert.equal(seg?.text_revision, 2);
    assert.equal(seg?.generation_status, "OUTDATED");
    assert.equal(seg?.previous_audio_asset_uri, priorAudio);
  });

  test("Editing text to same content does not increment revision or invalidate", () => {
    const scenes = createMockScenes();
    const chapter = buildInitialNarrationChapter("proj_test", "Demon Emperor", scenes);
    const clips = syncChapterToTimelineClips(chapter, scenes);

    const readyClip = clips[0];
    const { updatedClip } = updateClipScriptText(readyClip, readyClip.text, chapter);

    assert.equal(updatedClip.text_revision, 1);
    assert.equal(updatedClip.status, "READY");
    assert.equal(updatedClip.audio_url, readyClip.audio_url);
  });
});

describe("Chapter 5B: Stale Async Result Protection via Revision Identity", () => {
  test("applyGeneratedAudioResult accepts result matching active script revision", () => {
    const scenes = createMockScenes();
    const chapter = buildInitialNarrationChapter("proj_test", "Demon Emperor", scenes);
    const clips = syncChapterToTimelineClips(chapter, scenes);

    const clip = clips[0];
    assert.equal(clip.text_revision, 1);

    const result = applyGeneratedAudioResult(
      clip,
      {
        target_revision: 1,
        audio_asset_uri: "/audio/seg_01_take1.mp3",
        measured_duration_sec: 4.2,
      },
      chapter
    );

    assert.equal(result.success, true);
    assert.equal(result.updatedClip.status, "READY");
    assert.equal(result.updatedClip.audio_url, "/audio/seg_01_take1.mp3");
    assert.equal(result.updatedClip.duration_sec, 4.2);
    assert.equal(result.updatedClip.generated_audio_revision, 1);

    const seg = result.updatedChapter?.segments.find((s) => s.id === clip.id);
    assert.equal(seg?.generation_status, "READY");
    assert.equal(seg?.audio_asset_uri, "/audio/seg_01_take1.mp3");
  });

  test("applyGeneratedAudioResult REJECTS stale async result when revision has advanced", () => {
    const scenes = createMockScenes();
    const chapter = buildInitialNarrationChapter("proj_test", "Demon Emperor", scenes);
    const clips = syncChapterToTimelineClips(chapter, scenes);

    // User edited text to Revision 2
    const { updatedClip: rev2Clip, updatedChapter } = updateClipScriptText(
      clips[0],
      "Brand new revised script text for Scene 1.",
      chapter
    );
    assert.equal(rev2Clip.text_revision, 2);
    assert.equal(rev2Clip.status, "OUTDATED");

    // Async synthesis job queued earlier completes and returns Revision 1 result
    const staleResult = applyGeneratedAudioResult(
      rev2Clip,
      {
        target_revision: 1, // Stale!
        audio_asset_uri: "/audio/stale_take_rev1.mp3",
        measured_duration_sec: 3.8,
      },
      updatedChapter
    );

    assert.equal(staleResult.success, false, "Stale result must be rejected");
    assert.equal(staleResult.updatedClip.status, "OUTDATED", "Clip must remain OUTDATED");
    assert.notEqual(staleResult.updatedClip.audio_url, "/audio/stale_take_rev1.mp3", "Stale audio must not overwrite");
    assert.ok(staleResult.rejectionReason?.includes("Stale synthesis rejected"));
    assert.ok(staleResult.rejectionReason?.includes("Rev #2"));
  });
});

describe("Chapter 5B: Timeline Integration Contract (Schema 5A-v2) Ingestion", () => {
  test("syncTimelineContractToState maps contract clips to timeline accurately", () => {
    const scenes = createMockScenes();
    const contract: NarrationToTimelineContract = {
      schema_version: "5A-v2",
      project_id: "proj_test",
      chapter_id: "chap_test",
      exported_at: new Date().toISOString(),
      clips: [
        {
          narration_segment_id: "seg_contract_01",
          sequence: 1,
          scene_id: "scene_01",
          linked_to_scene: true,
          scene_offset_sec: 0.5,
          speaker: "The Narrator",
          text: "Echoes resounded through the ancient chamber.",
          text_revision: 1,
          content_hash: "abcd1234",
          emotion: "Mysterious",
          speed: 1.0,
          estimated_duration_sec: 4.0,
          measured_duration_sec: 4.1,
          audio_asset_uri: "/assets/demo/seg_01.mp3",
          previous_audio_asset_uri: null,
          generated_audio_revision: 1,
          review_status: "APPROVED",
          generation_status: "READY",
          source_panel_ids: ["panel_01_01"],
          voice_profile_id: "voice_aria",
          performance_intent: "Atmospheric",
        },
        {
          narration_segment_id: "seg_contract_02",
          sequence: 2,
          scene_id: "scene_02",
          linked_to_scene: true,
          scene_offset_sec: 1.0,
          speaker: "Archon Malakor",
          text: "The seal will break.",
          text_revision: 2,
          content_hash: "ef012345",
          emotion: "Angry",
          speed: 0.9,
          estimated_duration_sec: 3.0,
          measured_duration_sec: null,
          audio_asset_uri: null,
          previous_audio_asset_uri: "/assets/demo/seg_02_prior.mp3",
          generated_audio_revision: 1,
          review_status: "NEEDS_REVIEW",
          generation_status: "OUTDATED",
          source_panel_ids: ["panel_01_02"],
          voice_profile_id: "voice_malakor",
          performance_intent: "Ominous",
        },
      ],
    };

    const ingested = syncTimelineContractToState(contract, scenes);

    assert.equal(ingested.length, 2);

    // Clip 1: linked to Scene 1 (start 0.0) with offset 0.5 -> start 0.5s
    assert.equal(ingested[0].id, "seg_contract_01");
    assert.equal(ingested[0].start_time_sec, 0.5);
    assert.equal(ingested[0].status, "READY");
    assert.equal(ingested[0].review_status, "APPROVED");
    assert.equal(ingested[0].speaker, "The Narrator");

    // Clip 2: linked to Scene 2 (start 4.0) with offset 1.0 -> start 5.0s
    assert.equal(ingested[1].id, "seg_contract_02");
    assert.equal(ingested[1].start_time_sec, 5.0);
    assert.equal(ingested[1].status, "OUTDATED");
    assert.equal(ingested[1].review_status, "NEEDS_REVIEW");
    assert.equal(ingested[1].previous_audio_asset_uri, "/assets/demo/seg_02_prior.mp3");
  });

  test("buildInitialNarrationChapter grounds narration text and speaker in real TextRegions", () => {
    const scenes = createMockScenes();
    const mockRegions: any[] = [
      {
        id: "tr_1",
        panel_id: "panel_01_01",
        sequence_in_panel: 1,
        raw_text: "What is that light?",
        corrected_text: "What is that light over there?!",
        region_type: "SPEECH",
        speaker_character_id: "char_marcus",
        status: "CONFIRMED",
      },
      {
        id: "tr_2",
        panel_id: "panel_01_02",
        sequence_in_panel: 1,
        raw_text: "The seal is weakening...",
        corrected_text: "The ancient seal is weakening rapidly.",
        region_type: "NARRATION",
        speaker_character_id: "char_narrator",
        status: "CONFIRMED",
      },
    ];

    const chapter = buildInitialNarrationChapter(
      "proj_real",
      "Demon Emperor",
      scenes,
      undefined,
      null,
      null,
      undefined,
      mockRegions
    );

    assert.equal(chapter.segments.length, 3);
    // Segment 1 from panel_01_01 has real corrected speech
    assert.equal(chapter.segments[0].narration_text, "What is that light over there?!");
    assert.equal(chapter.segments[0].source_context.raw_ocr_dialogue, "What is that light over there?!");
    assert.equal(chapter.segments[0].speaker_type, "CHARACTER");

    // Segment 2 from panel_01_02 has narration box
    assert.equal(chapter.segments[1].narration_text, "The ancient seal is weakening rapidly.");
    assert.equal(chapter.segments[1].speaker_type, "NARRATOR");

    // Segment 3 has no OCR, so has natural non-robotic title
    assert.equal(chapter.segments[2].narration_text, "Ancient Seal.");
  });
});

describe("Audio Overlap Prevention & Ripple Synchronization", () => {
  test("synchronizeChapterWithTimeline guarantees zero audio overlap and ripples scene timing", () => {
    const scenes = createMockScenes();
    const chapter = buildInitialNarrationChapter("proj_test", "Demon Emperor", scenes);

    // Make segment 1 long (6.5s) on Scene 1 (which was 4.0s)
    chapter.segments[0].measured_duration_sec = 6.5;
    chapter.segments[1].measured_duration_sec = 5.0;
    chapter.segments[2].measured_duration_sec = 4.0;

    const { scenes: syncedScenes, narrationClips: syncedClips } = synchronizeChapterWithTimeline(
      chapter,
      scenes,
      [],
      { rippleScenes: true }
    );

    assert.equal(syncedClips.length, 3);
    // Clip 1 starts at 0.0s
    assert.equal(syncedClips[0].start_time_sec, 0.0);
    // Scene 1 duration was expanded to at least 6.5s (plus cushion)
    assert.ok(syncedScenes[0].duration_sec >= 6.5, "Scene 1 duration should expand to fit audio");
    // Scene 2 starts AFTER Clip 1 has finished
    assert.ok(syncedScenes[1].start_time_sec >= 6.5, "Scene 2 start time must follow Scene 1 audio");
    // Clip 2 starts at or after Scene 2 start, strictly >= Clip 1 end
    assert.ok(syncedClips[1].start_time_sec >= syncedClips[0].start_time_sec + syncedClips[0].duration_sec);
    // Clip 3 starts strictly >= Clip 2 end
    assert.ok(syncedClips[2].start_time_sec >= syncedClips[1].start_time_sec + syncedClips[1].duration_sec);

    // Verify all clips are strictly non-overlapping
    for (let i = 1; i < syncedClips.length; i++) {
      const prevEnd = syncedClips[i - 1].start_time_sec + syncedClips[i - 1].duration_sec;
      assert.ok(
        syncedClips[i].start_time_sec >= prevEnd,
        `Clip ${i} at ${syncedClips[i].start_time_sec}s overlaps previous clip ending at ${prevEnd}s`
      );
    }
  });

  test("syncChapterToTimelineClips prevents collision when multiple segments share a scene", () => {
    const scenes = createMockScenes();
    const chapter = buildInitialNarrationChapter("proj_test", "Demon Emperor", scenes);

    // Assign segments 0 and 1 to the SAME scene
    chapter.segments[0].scene_id = "scene_01";
    chapter.segments[0].measured_duration_sec = 4.0;
    chapter.segments[1].scene_id = "scene_01";
    chapter.segments[1].measured_duration_sec = 3.5;

    const clips = syncChapterToTimelineClips(chapter, scenes);

    assert.equal(clips[0].start_time_sec, 0.0);
    // Clip 1 must NOT start at 0.0s; it must start AFTER Clip 0 finishes
    assert.ok(clips[1].start_time_sec >= clips[0].start_time_sec + clips[0].duration_sec);
  });
});
