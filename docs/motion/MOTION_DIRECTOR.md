# PanelFlow Studio — Motion Director Architecture

## 1. Overview & Purpose

The **Motion Director** is the central visual sequencing engine of PanelFlow Studio. It bridges the gap between static comic/manga illustrations, upstream narrative understanding, and downstream video rendering:

```
+-------------------------------------------------------------------------------+
| UPSTREAM CONTRACTS                                                            |
|                                                                               |
|  [Approved Script]        [Source Visuals]      [Master Audio Timeline]       |
|  - ScriptSegments         - Normalized Panels   - Real speech timestamps      |
|  - Emotion & Intent       - Bounding Boxes      - Authoritative clock         |
|  - Character Speakers     - Speech Balloons     - Pause/Silence detections    |
+-------------------------------------------------------------------------------+
                                      |
                                      v
+-------------------------------------------------------------------------------+
| MOTION DIRECTOR FOUNDATION (engine/motion/)                                   |
|                                                                               |
|  Audio Clock Resolver     -> Locks all shot cuts to speech audio intervals    |
|  Focus Target Selector    -> Conservative bounding box & balloon framing      |
|  Dialogue Framer          -> Natural multi-speaker conversational pans        |
|  Timing Director          -> Pacing heuristics, shot merging, minimum holds   |
|  Camera Bounds Validator  -> Strict frustum clamping to [0.0, 1.0] coordinates|
|  Effect Director          -> Restrained impact shakes, flashes, & vignettes   |
|  Parallax Planner         -> 2.5D multi-plane depth motion with flat fallback |
|  Invalidation Manager     -> Selective scene regeneration & override lock     |
|  Composition Validator    -> Pre-render audit (zero gaps, bounds safety)      |
+-------------------------------------------------------------------------------+
                                      |
                                      v
+-------------------------------------------------------------------------------+
| ARTIFACT OUTPUT: VISUAL TIMELINE (JSON)                                       |
|                                                                               |
|  - Render-ready Shot Plan                                                     |
|  - Deterministic SHA-256 Input & Output Hashes                                |
|  - Full Pre-Render Coverage Audit & Diagnostic Warnings                       |
+-------------------------------------------------------------------------------+
```

---

## 2. Key Architecture Principles

1. **Authoritative Audio Clock Locking**:
   Shot durations and cut boundaries are never estimated from text word counts. The `MasterAudioTimeline` provides exact floating-point intervals (seconds) derived from real synthesized speech or verified audio fixtures.

2. **Deterministic & Inspectable**:
   Given identical inputs, seeds, and style profiles, `MotionDirector` produces bit-for-bit identical camera paths and JSON timelines. No random drifting or unexplainable cuts.

3. **Conservative Focus Framing (No Hallucinated Coordinates)**:
   If character bounding boxes or speech balloons are unavailable for a line, the system does NOT fabricate focal coordinates. It falls back gracefully and conservatively to environmental wide compositions (`ENVIRONMENT_WIDE`).

4. **Guaranteed Frame Bounds**:
   The camera frustum is strictly validated and clamped by `CameraBoundsValidator`. A camera view never reveals canvas areas outside the source visual asset ($[0, 1] \times [0, 1]$). Sub-1.0 zooms are prohibited to prevent black margins.

5. **Restrained Visual Polish**:
   Cinematic effects (shakes, flashes, vignettes) are strictly governed by an `EffectBudget`. Maximum effects per scene and mandatory cooldowns prevent visual noise.

6. **Selective Invalidation & Non-Destructive Editing**:
   When a user edits a single scene or adjusts a script segment, only the affected scene is replanned. Locked shots (`ShotOverride(locked=True)`) and sibling scenes are preserved intact.

---

## 3. Directory Layout

- `engine/motion/models/`: Strongly-typed Pydantic schemas (camera, effects, transitions, cues, layers, overrides, timeline).
- `engine/motion/camera/`: Coordinate math, bounds validator, interpolators, and aspect ratio fitting.
- `engine/motion/timing/`: Audio clock synchronization and duration rules.
- `engine/motion/planning/`: Shot planning, focus selection, dialogue framing, visual repetition detection, and invalidation.
- `engine/motion/effects/`: Bounded effect generation and budget enforcement.
- `engine/motion/depth/`: 2.5D multi-plane parallax and flat fallback.
- `engine/motion/validation/`: Comprehensive timeline coverage and composition audit.
- `engine/motion/hashing.py`: Cryptographic SHA-256 caching.
- `engine/motion/preview.py`: Lightweight PIL-based preview generator.
- `engine/motion/director.py`: Unified public facade.
