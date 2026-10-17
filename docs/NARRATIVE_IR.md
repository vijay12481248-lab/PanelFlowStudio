# PanelFlow Studio — Narrative IR Specification (Layer B)

## 1. Overview & Vision
The **Narrative Intermediate Representation (Narrative IR)** is the canonical semantic spine of PanelFlow Studio. It bridges raw comic visual perception (pages, panels, bounding boxes, OCR text) and downstream motion comic generation (script adaptation, TTS audio, sound effects, motion graphics, and video composition).

Rather than directly transforming OCR text into YouTube scripts via prompt stuffing, PanelFlow Studio enforces an explicit intermediate world model that captures characters, locations, events, utterances, speaker attributions, and dramatic beats with full bidirectional provenance.

---

## 2. The Three Truth Layers
PanelFlow Studio strictly enforces a three-layer boundary separating human-verified ground truth from derived interpretations and adaptive presentations:

```
┌────────────────────────────────────────────────────────┐
│ Layer A: Source Truth (IMMUTABLE)                      │
│ - Normalized pages & SHA-256 digests                  │
│ - Panel bboxes & reading order                         │
│ - Text region bounding boxes                           │
│ - Raw OCR transcriptions & human corrections           │
│ - Strict Gate: OCR_APPROVED                            │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│ Layer B: Narrative Interpretation (RE-GENERABLE)        │
│ - Character entities, canonical names, and aliases     │
│ - Location entities & visual cues                     │
│ - Panel visual observations & character presences      │
│ - Utterances, emotions, and speaker attributions      │
│ - Events (actions, discoveries, movements)             │
│ - Scene boundaries & dramatic story beats              │
│ - Continuity warnings & resolution states             │
│ - Strict Gate: STORY_APPROVED                          │
└───────────────────────────┬────────────────────────────┘
                            │
                            ▼
┌────────────────────────────────────────────────────────┐
│ Layer C: Script Adaptation (PRESENTATION)             │
│ - Video script segments (dialogue vs narration)        │
│ - Pacing & duration estimations (WPM + pauses)         │
│ - Adaptation profiles (Faithful, Condensed, etc.)     │
│ - Advisory production intent (camera motion, SFX, music)│
│ - Faithfulness validation & hallucination audit       │
│ - Strict Gate: SCRIPT_APPROVED                         │
└────────────────────────────────────────────────────────┘
```

### Architectural Guardrails:
1. **Source Immutability**: Layer B operations never modify Layer A source pages, panels, or raw OCR transcripts.
2. **Re-generability**: If OCR or panels change, Layer B machine-derived entities can be invalidated and regenerated while preserving manual overrides (`manual_override = true`).
3. **No Adaptation Pollution**: Layer C narrator summaries or creative pacing lines are never written back into Layer A or Layer B as source facts.

---

## 3. Narrative IR Schema

The complete Narrative IR is serialized to `narrative.json` within the project's `story/` workspace directory and stored in the SQLite database (`narratives` table).

```json
{
  "project_id": "0cc85ed6-7fea-4415-83f1-8f3302145afc",
  "version": "1.0",
  "language": "en",
  "characters": [
    {
      "character_id": "char_9a4b1c2e",
      "project_id": "0cc85ed6-7fea-4415-83f1-8f3302145afc",
      "display_name": "Explorer",
      "canonical_name": "Explorer",
      "aliases": ["The Traveler", "Scout"],
      "description": "Determined seeker exploring ancient crystalline ruins.",
      "visual_traits": ["ivory coat", "dark boots", "gauntlets"],
      "role": "PROTAGONIST",
      "first_panel_id": "p_001",
      "reference_panel_ids": ["p_001", "p_003"],
      "status": "CONFIRMED",
      "manual_override": false
    }
  ],
  "locations": [
    {
      "location_id": "loc_f4e190a2",
      "name": "Ancient Subterranean Ruins",
      "canonical_name": "Crystalline Caverns",
      "description": "Deep underground stone chambers with dormant energy conduits.",
      "visual_cues": ["crystal pillars", "glowing stone", "water ripples"],
      "panel_ids": ["p_001", "p_002", "p_003", "p_004"],
      "status": "CONFIRMED",
      "manual_override": false
    }
  ],
  "scenes": [
    {
      "scene_id": "scene_81a2bc0f",
      "sequence": 1,
      "title": "Entry into the Ruins",
      "panel_start": "p_001",
      "panel_end": "p_002",
      "location_id": "loc_f4e190a2",
      "character_ids": ["char_9a4b1c2e"],
      "summary": "The explorer descends into the ancient ruins and observes the ancient conduits.",
      "confidence": 0.95,
      "boundary_reason": "LOCATION_CHANGE",
      "manual_override": false
    }
  ],
  "beats": [
    {
      "beat_id": "beat_33df710a",
      "scene_id": "scene_81a2bc0f",
      "sequence": 1,
      "panel_ids": ["p_001", "p_002"],
      "event_ids": ["evt_c901a4e1"],
      "summary": "Arrival and initial inspection of the chamber.",
      "dramatic_function": "INTRODUCTION",
      "importance": "HIGH",
      "intensity": 0.4,
      "confidence": 0.95,
      "music_intent": "MYSTERIOUS",
      "sfx_intent": "FOOTSTEP"
    }
  ],
  "events": [
    {
      "event_id": "evt_c901a4e1",
      "event_type": "ENTER",
      "actor_character_id": "char_9a4b1c2e",
      "target_character_id": null,
      "object_name": "chamber entrance",
      "location_id": "loc_f4e190a2",
      "panel_ids": ["p_001"],
      "description": "The explorer breaches the entrance of the subterranean ruins.",
      "confidence": 0.95,
      "evidence": {
        "panel_ids": ["p_001"],
        "text_region_ids": [],
        "confidence": 0.95
      }
    }
  ],
  "utterances": [
    {
      "utterance_id": "utt_tr_001",
      "text_region_id": "tr_001",
      "panel_id": "p_001",
      "speaker_character_id": "char_9a4b1c2e",
      "source_text": "The energy here is still alive...",
      "corrected_text": "The energy here is still alive...",
      "utterance_type": "DIALOGUE",
      "emotion": "DETERMINED",
      "emotion_confidence": 0.92,
      "intensity": 0.6,
      "valence": 0.2,
      "arousal": 0.5,
      "sequence": 1,
      "provenance": {
        "panel_ids": ["p_001"],
        "text_region_ids": ["tr_001"],
        "confidence": 0.92
      }
    }
  ],
  "speaker_attributions": [
    {
      "text_region_id": "tr_001",
      "speaker_character_id": "char_9a4b1c2e",
      "confidence": 0.92,
      "method": "BALLOON_GEOMETRY",
      "evidence_panel_ids": ["p_001"],
      "reason_code": "SOLITARY_CHARACTER"
    }
  ],
  "continuity_warnings": [],
  "analysis_metadata": {
    "provider": "mock",
    "model": "mock-narrative-v1",
    "analyzed_at": "2026-10-17T09:40:00Z",
    "total_panels": 4,
    "total_utterances": 4
  }
}
```

---

## 4. Controlled Enums

### DramaticFunction
- `INTRODUCTION`: Opening introduction of setting or situation.
- `SETUP`: Exposition and preparation.
- `DISCOVERY`: Character discovers key item or information.
- `CONFLICT`: Active dispute, threat, or opposition.
- `ESCALATION`: Tension increases.
- `REVELATION`: Plot twist or secret unveiled.
- `REVERSAL`: Sudden shift in fortune.
- `CLIMAX`: Peak dramatic intensity.
- `REACTION`: Characters respond to climactic events.
- `RESOLUTION`: Closure or settling of the scene.
- `TRANSITION`: Interlude bridging to the next scene.

### BoundaryReason
- `LOCATION_CHANGE`: Shift to a different physical setting.
- `TIME_CHANGE`: Flashback, time skip, or temporal transition.
- `NARRATIVE_SHIFT`: Radical change in narrative focus or point of view.
- `CHAPTER_BOUNDARY`: Hard chapter break in source material.
- `MANUAL`: User-specified scene boundary.

### EmotionType
`NEUTRAL`, `JOYFUL`, `SAD`, `ANGRY`, `FEARFUL`, `SURPRISED`, `DISGUSTED`, `CONFUSED`, `DETERMINED`, `EXCITED`, `CALM`, `TENSE`, `GRIEVING`, `SARCASTIC`, `UNKNOWN`.
