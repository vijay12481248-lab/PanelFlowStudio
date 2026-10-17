# PanelFlow Studio — v1.0.0 End-to-End Pipeline Architecture

This document describes the complete 18-stage lifecycle of PanelFlow Studio, detailing the data contracts, operational responsibilities, verification gates, and caching policies across every subsystem.

---

## 1. Pipeline Overview

```
Acquisition (Source Images)
  ↓
Normalization (Webtoon / Manga / Comic Pages)
  ↓
Panel Detection (Bounding Boxes, Reading Order)
  ↓
OCR & Text Extraction (Bounding Boxes, Confidences, Transcripts)
  ↓
Narrative Understanding & Story IR (Scenes, Characters, Utterances)
  ↓
Script Adaptation (Spoken Dialogue, Emotion, Pacing Intent)
  ↓
Audio Director (F5-TTS Neural Voice, ACE-Step Score, MasterAudioTimeline)
  ↓
Motion Director (Camera Framing Trajectories, VisualTimeline)
  ↓
Production Renderer (FFmpeg H.264/AAC, Letterbox Containment, Validation Audit)
```

---

## 2. Stage-by-Stage Specification

### Stage 1: Project Initialization (`NEW` / `RIGHTS_APPROVED`)
- **Input**: Local folder path, ZIP archive, or authorized URL.
- **Contract**: `ProjectRecord`, `RightsStatus` (e.g. `PUBLIC_DOMAIN`, `CREATIVE_COMMONS`, `USER_OWNED`, `LICENSED`).
- **Gate**: User must declare rights status and acknowledge legal compliance before any ingestion proceeds.

### Stage 2: Acquisition & Page Ingestion (`ACQUIRED`)
- **Operations**: Inspects source, extracts image files, orders pages naturally (natural numerical sort e.g. `1, 2, 10`), hashes assets (`SHA-256`), records dimensions.
- **Contract**: `PageRecord` with byte size, resolution, and sequence index.

### Stage 3: Normalization (`NORMALIZED`)
- **Operations**: Corrects page orientations, calculates aspect ratios, prepares canonical working image format.
- **Contract**: Normalized page files on disk with verified dimensions.

### Stage 4: Panel Detection (`PANELS_DETECTED`)
- **Operations**: Connected component analysis, contour discovery, gutter segmentation, and reading order sequencing (`LTR`, `RTL`, `VERTICAL_WEBTOON`).
- **Contract**: `PanelRecord` with bounding boxes `[x, y, width, height]` and normalized coordinates `[0.0 - 1.0]`.

### Stage 5: OCR & Text Region Detection (`OCR_COMPLETE` / `OCR_APPROVED`)
- **Operations**: Speech balloon localization, OCR transcript extraction, confidence scoring, text clean-up, and speaker pre-assignment.
- **Contract**: `OCRRecord`, `TextRegionRecord`.
- **Gate**: User reviews transcript accuracy and approves text regions.

### Stage 6: Narrative Understanding (`STORY_ANALYZED` / `STORY_APPROVED`)
- **Operations**: Local LLM (Ollama / Qwen2.5 / Gemma) analyzes dialogue, infers scenes, entities, character roles, and continuity.
- **Contract**: `NarrativeDocument` with characters, locations, scenes, beats, and utterances.
- **Gate**: Story Confirmation Gate ensures consistent character identity across scenes.

### Stage 7: Video Script Adaptation (`SCRIPT_GENERATED` / `SCRIPT_APPROVED`)
- **Operations**: Adapts raw speech into timed spoken script (`FAITHFUL`, `CONDENSED`, `DRAMATIC_NARRATION`, `ACCESSIBLE_RECAP`), assigns emotions and pacing intent.
- **Contract**: `VideoScriptRecord`, `ScriptSegmentRecord`.
- **Gate**: Script Validation Gate checks evidence grounding and coverage against approved OCR.

### Stage 8: Audio Director (`VOICE_GENERATED` / `AUDIO_APPROVED`)
- **Operations**: Synthesizes speech using local F5-TTS neural models or broadcast tones, measures exact WAV durations with `soundfile.info()`, adds 0.5s pause intervals, binds ACE-Step D-Minor crystal score.
- **Contract**: `AudioTimelineRecord`, `MasterAudioTimeline` (`intervals`, `total_duration_sec`, `48000 Hz`).
- **Selective Invalidation**: Re-synthesizing a single segment updates downstream start/end times while preserving all other cached speech takes.

### Stage 9: Motion Director (`SHOT_PLAN_GENERATED` / `MOTION_APPROVED`)
- **Operations**: Maps comic panels and pages to authoritative speech timings, designs camera framing trajectories (`camera_start` → `camera_end`), applies easing curves and transitions (`CUT`, `FADE`, `DISSOLVE`).
- **Contract**: `VisualTimelineRecord`, `VisualTimeline` (`shots`, `total_duration_sec`, `style_preset`).
- **Gate**: User reviews shot plan, applies manual framing overrides if desired, and approves.

### Stage 10: Production Renderer (`RENDERED` / `COMPLETE`)
- **Operations**: Compiles `RenderPlan`, mixes 48 kHz stereo audio bus (dialogue + ducked music), streams composed frames to FFmpeg pipe, encodes H.264 video with AAC audio.
- **Contract**: `RenderJobRecord`, production `.mp4` file, contact sheet `.jpg`, validation report `.json`.
- **Quality Audit**: Automated verification checks for zero timeline gaps, zero black-frame failures, zero audio clipping, and strict A/V duration alignment (±1.5s tolerance).

---

## 3. Dependency Invalidation Rules

| Modified Artifact | Invalidated Subsystems | Preserved Artifacts |
| :--- | :--- | :--- |
| **OCR Transcript Edit** | Story, Script, Audio, Motion, Render | Source Pages, Panels |
| **Character Merge/Split** | Story IR, Script, Audio, Motion, Render | Pages, Panels, OCR |
| **Script Text Edit** | Audio, Motion, Render | OCR, Characters, Scenes |
| **Single Line Regenerate** | Downstream timing in Motion & Render | All other speech WAVs, Script |
| **Motion Style Change** | VisualTimeline, Render | All speech WAVs, MasterAudioTimeline |
| **Render Profile Change** | Final MP4 only | Script, Audio, Motion Timelines |
