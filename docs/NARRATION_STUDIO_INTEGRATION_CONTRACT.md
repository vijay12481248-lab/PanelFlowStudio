# PanelFlow Studio — Chapter 5A: Narration & Storytelling Studio
## Architecture & Future Timeline Integration Contract (Schema 5A-v2)

---

### Executive Summary

Chapter 5A delivers an independent, professional **AI Narration & Storytelling Workspace** for PanelFlow Studio.

This module was engineered and hardened in strict isolation from Chapter 3 (Timeline Editing) and Chapter 4 (Motion Planning):
- **Zero modification to existing timeline files**: `StoryEditorScreen.tsx`, `StoryEditorTimeline.tsx`, `VideoCompositionCanvas.tsx`, `SourcePageBrowser.tsx`, `ContextualInspector.tsx`, and `App.tsx` remain untouched.
- **Self-contained domain model**: All narration types, mock profiles, and state machines reside within `apps/desktop/src/components/narration-studio/`.
- **Dedicated preview harness**: An independent Vite entry point (`preview-narration.html`) and test harness (`src/preview-narration.tsx`) provide isolated execution, interaction testing, and demonstration without altering global application routing.

---

### 1. Hardened Product Decisions

#### Decision 1 — Smart Scene Binding
- **Stable References**: Narration segments retain permanent references to source manga pages (`page_id`, `page_number`), panels (`panel_ids`, `panel_labels`), and optional scenes (`scene_id`, `scene_title`).
- **Linked vs. Unlinked State**:
  - `linked_to_scene: boolean` (default `true`): When true, future Chapter 3 timeline adapters automatically anchor the narration clip to the start boundary of the associated scene.
  - When set to `false`, the narration clip behaves as floating dialogue that can span across scene transitions.
- **Relative Timing Offset**:
  - `scene_offset_sec: number` (user-editable offset, e.g. `-1.5s` to `+10.0s`).
  - Represents the relative playback offset from scene anchor start, avoiding hardcoded absolute timestamps or assumptions about scene duration.
- **Timeline Decoupling**: No timeline synchronization or absolute track placement is executed in Chapter 5A.

#### Decision 2 — Regeneration Policy & Stale Result Protection
- **Automatic Invalidation on Edit**: When narration text is edited, previously generated audio is immediately flagged as `OUTDATED`.
- **Take Preservation**: The previous audio take is preserved in `previous_audio_asset_uri` with its revision number (`generated_audio_revision`), allowing creators to listen to the prior take while drafting new text.
- **Revision Tracking & Deterministic Hashing**:
  - `text_revision: number`: Monotonically increasing revision counter per text change.
  - `content_hash: string`: Fast, deterministic 32-bit FNV-1a hash of script text, emotion, speed, and pause preset.
- **Stale Async Protection**: If a user edits script text from Revision 1 to Revision 2 while background synthesis is running for Revision 1, the completed result's `target_revision` (1) mismatches the active `text_revision` (2). The stale result is rejected: it does not overwrite `audio_asset_uri`, and the segment remains `OUTDATED` with an explanatory diagnostic message.
- **Decoupled States**:
  - Script Review Status (`DRAFT` | `NEEDS_REVIEW` | `APPROVED`) is an editorial milestone.
  - Generation Status (`UNQUEUED` | `QUEUED` | `PROCESSING` | `READY` | `OUTDATED` | `FAILED`) reflects audio synthesis assets.
  - A script can be approved before audio exists; audio synthesis does not silently change script approval.

#### Decision 3 — Transparent Audio Preview Verification
- **Web Audio API Demonstration**: Provides a calibrated D-Minor synthesizer chime (Lumina acoustic reference) strictly labeled as an interface demonstration test, not voice synthesis.
- **Browser Speech Synthesis Scratchpad**: Uses `window.speechSynthesis` for pacing and pause checks, explicitly disclosed as neutral Web Speech API and not local neural TTS.
- **Clear Fallback**: Displays an explicit `"Audio preview unavailable"` state when ungenerated.
- **Local Model Discipline**: Local TTS model execution (F5-TTS, Chatterbox, Dia in `C:\Tools`) is deferred to Chapter 6.

#### Decision 4 — Character Voice Override Protection
- **Manual Customization Flag**: When a creator changes a voice profile for an individual segment, `has_custom_voice_override` is set to `true`.
- **Safe Batch Propagation**: When applying a character's default voice to all chapter lines in `CharacterVoiceManager`:
  - If lines with custom overrides exist, an interactive confirmation dialog is presented.
  - Creators can choose **"Skip Customized Lines"** (preserves overrides) or **"Overwrite All Lines"** (updates all lines).

---

### 2. Workspace Layout & Component Architecture

```
apps/desktop/src/components/narration-studio/
├── NarrationStudio.tsx               # Top-level orchestrator, state manager & undo/redo
├── NarrationStoryPanel.tsx           # Left Column: Story & Source Context
├── NarrationSegmentEditor.tsx        # Center Column: Main Story Script Editor
├── NarrationReviewPanel.tsx          # Center Column: 4-Tier Storytelling Quality Matrix
├── EmotionDeliveryControls.tsx       # Right Column: Emotion & Performance Directing
├── CharacterVoiceManager.tsx         # Voice Assignment Workspace (Embedded & Modal)
├── AudioPreviewPlayer.tsx            # Transparent Audio Preview & Outdated Take Player
├── NarrationJobQueue.tsx             # Background Generation Job Engine with Stale Guard
├── NarrationStudio.types.ts          # Pure domain types, hash utility & Schema 5A-v2 contract
├── NarrationStudio.mock.ts           # Representative 8-segment manga chapter with 4 characters
├── index.ts                          # Public module barrel exports
└── __tests__/
    └── NarrationStudio.test.ts       # 24 automated unit & component tests (100% pass)
```

---

### 3. Chapter 3 Timeline Integration Contract (Schema 5A-v2)

To enable seamless ingestion after Chapter 3 is completed, Narration Studio exports a strictly typed, serializable JSON contract:

```typescript
export interface NarrationToTimelineContract {
  schema_version: "5A-v2";
  project_id: string;
  chapter_id: string;
  exported_at: string;
  clips: Array<{
    narration_segment_id: string;
    sequence: number;
    scene_id?: string;
    linked_to_scene: boolean;
    scene_offset_sec: number;
    speaker: string;
    text: string;
    text_revision: number;
    content_hash: string;
    emotion: NarrationEmotion;
    speed: number;
    estimated_duration_sec: number;
    measured_duration_sec?: number | null;
    audio_asset_uri?: string | null;
    previous_audio_asset_uri?: string | null;
    generated_audio_revision?: number | null;
    review_status: "DRAFT" | "NEEDS_REVIEW" | "APPROVED";
    generation_status: "UNQUEUED" | "QUEUED" | "PROCESSING" | "READY" | "OUTDATED" | "FAILED";
    source_panel_ids: string[];
    voice_profile_id: string;
    performance_intent: string;
  }>;
}
```

#### Example Exported Payload (Snippet)

```json
{
  "schema_version": "5A-v2",
  "project_id": "proj_demo_manga_01",
  "chapter_id": "chap_14_obsidian_vault",
  "exported_at": "2026-10-18T11:20:00.000Z",
  "clips": [
    {
      "narration_segment_id": "seg_001",
      "sequence": 1,
      "scene_id": "scene_1",
      "linked_to_scene": true,
      "scene_offset_sec": 0.0,
      "speaker": "The Narrator",
      "text": "Beneath the shattered pillars of the Obsidian Vault, a forgotten pulse echoed through the stone.",
      "text_revision": 1,
      "content_hash": "a4f891b2",
      "emotion": "Mysterious",
      "speed": 1.0,
      "estimated_duration_sec": 6.8,
      "measured_duration_sec": 7.1,
      "audio_asset_uri": "/assets/demo/seg_001_audio.mp3",
      "previous_audio_asset_uri": null,
      "generated_audio_revision": 1,
      "review_status": "APPROVED",
      "generation_status": "READY",
      "source_panel_ids": ["panel_1_1"],
      "voice_profile_id": "voice_aria",
      "performance_intent": "Low, measured delivery building ancient atmosphere."
    },
    {
      "narration_segment_id": "seg_005",
      "sequence": 5,
      "scene_id": "scene_2",
      "linked_to_scene": true,
      "scene_offset_sec": 1.2,
      "speaker": "Archon Malakor",
      "text": "Look closely upon this seal, mortal. Once broken, the dark cadence cannot be silenced.",
      "text_revision": 2,
      "content_hash": "c83b129e",
      "emotion": "Angry",
      "speed": 0.9,
      "estimated_duration_sec": 7.2,
      "measured_duration_sec": null,
      "audio_asset_uri": null,
      "previous_audio_asset_uri": "/assets/demo/seg_005_take1_archived.mp3",
      "generated_audio_revision": 1,
      "review_status": "NEEDS_REVIEW",
      "generation_status": "OUTDATED",
      "source_panel_ids": ["panel_2_2"],
      "voice_profile_id": "voice_malakor",
      "performance_intent": "Deep ominous resonance; script updated after take 1."
    }
  ]
}
```

#### Future Chapter 3 Timeline Adapter

When Chapter 3 timeline editing is ready to consume Narration Studio outputs, the following adapter can be implemented without changing Chapter 5A types:

```typescript
export function adaptNarrationToTimelineClips(
  contract: NarrationToTimelineContract,
  scenes: Array<{ id: string; start_time_sec: number; duration_sec: number }>
): TimelineNarrationClip[] {
  let fallbackCursorSec = 0;

  return contract.clips
    .filter((clip) => clip.review_status === "APPROVED")
    .map((clip) => {
      const scene = scenes.find((s) => s.id === clip.scene_id);
      const sceneStart = scene ? scene.start_time_sec : fallbackCursorSec;
      
      // Calculate start time based on linked state and user offset
      const startTime = clip.linked_to_scene
        ? Math.max(0, sceneStart + clip.scene_offset_sec)
        : fallbackCursorSec + clip.scene_offset_sec;

      const duration = clip.measured_duration_sec || clip.estimated_duration_sec;
      fallbackCursorSec = startTime + duration + 0.3; // 300ms pause

      return {
        id: clip.narration_segment_id,
        scene_id: clip.scene_id,
        panel_id: clip.source_panel_ids[0],
        speaker: clip.speaker,
        text: clip.text,
        text_revision: clip.text_revision,
        emotion: clip.emotion,
        speed: clip.speed,
        start_time_sec: startTime,
        duration_sec: duration,
        audio_url: clip.audio_asset_uri || clip.previous_audio_asset_uri || undefined,
        is_outdated_audio: clip.generation_status === "OUTDATED",
        linked_to_scene: clip.linked_to_scene,
      };
    });
}
```

---

### 4. Verification & Quality Assurance Results

| Metric | Verification Result |
|---|---|
| **TypeScript Compilation** | `npx tsc --noEmit` exited with `0` errors across entire `@panelflow/desktop` |
| **Domain & Unit Test Suite** | 24 / 24 tests passed across 10 test suites in `~85ms` |
| **Decision 1 Coverage** | Scene binding retention, unlinking, and relative offset calculation verified |
| **Decision 2 Coverage** | Outdated triggers, revision increment, FNV-1a hashing, previous take preservation, and stale async rejection verified |
| **Override Protection** | Safe propagation preserving custom overrides and explicit overwrite verified |
| **File Isolation** | `0` modifications to `App.tsx`, `StoryEditorScreen.tsx`, `StoryEditorTimeline.tsx`, `VideoCompositionCanvas.tsx`, or motion services |
| **Branch Safety** | Staged cleanly on `feature/chapter-5a-narration-studio` |
