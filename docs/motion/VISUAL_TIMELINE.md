# Visual Timeline Data Model Specification

## 1. Overview

The `VisualTimeline` is the authoritative intermediate representation produced by the Motion Director. It specifies the complete sequence of scenes, shots, camera states, focus cues, layered depth parameters, effects, and transitions required to render a high-production motion comic.

---

## 2. Hierarchy

```
VisualTimeline
├── timeline_id: str
├── project_id: str
├── total_duration_sec: float
├── timeline_source: TimelineSourceType (REAL_AUDIO_TIMELINE | DEVELOPMENT_TIMELINE_FIXTURE)
├── target_resolution: TargetResolution (width, height, fps, aspect_ratio)
├── style_profile: MotionStyleProfile (preset, max_zoom, max_pan, speed, easing)
├── hash: str (Deterministic SHA-256)
├── warnings: List[MotionWarning]
└── scenes: List[MotionScene]
    ├── scene_id: str
    ├── sequence: int
    ├── title: str
    ├── start_time: float
    ├── end_time: float
    └── shots: List[Shot]
        ├── shot_id: str
        ├── scene_id: str
        ├── sequence_in_scene: int
        ├── sequence_global: int
        ├── source_asset_id: str
        ├── source_panel_id: Optional[str]
        ├── start_time: float
        ├── end_time: float
        ├── duration: float
        ├── frame_region: NormalizedRect (x, y, width, height)
        ├── camera_start: CameraState (center_x, center_y, zoom, rotation)
        ├── camera_end: CameraState (center_x, center_y, zoom, rotation)
        ├── easing: EasingFunction
        ├── motion_type: MotionType
        ├── focus_targets: List[FocusTarget]
        ├── layer_instructions: List[LayerInstruction]
        ├── effect_instructions: List[EffectInstruction]
        ├── transition_in: TransitionInstruction
        ├── transition_out: TransitionInstruction
        ├── caption_cues: List[CaptionCue]
        └── locked: bool
```

---

## 3. Shot Data Model Breakdown

### Normalized Camera States
- `camera_start`: Coordinates and zoom factor when the shot enters.
- `camera_end`: Coordinates and zoom factor when the shot exits.
- Center coordinates $(center\_x, center\_y)$ and zoom $z \ge 1.0$ strictly satisfy `CameraBoundsValidator` constraints.

### Transitions
- Supported types: `CUT`, `CROSS_DISSOLVE`, `FADE_TO_BLACK`, `FADE_FROM_BLACK`, `MATCH_HOLD`.
- Preserves visual continuity when adjacent shots share the same illustrated panel.

### Focus Targets & Explainability
- Every shot records its `focus_targets` (e.g. `SPEAKER`, `CHARACTER`, `SPEECH_BALLOON`, `ENVIRONMENT_WIDE`).
- Records confidence score and attribution rationale.
- UNKNOWN subjects remain explicit without hallucinated bounding coordinates.

### Captions & Subtitles
- `CaptionCue` contains subtitle text synchronized exactly to the speech interval $[start\_time, end\_time]$.
- Links directly to `script_segment_id` and `speaker_character_id`.

---

## 4. JSON Serialization Sample

```json
{
  "timeline_id": "vtl_98f42e1a",
  "project_id": "proj_demo",
  "version": "1.0",
  "timeline_source": "REAL_AUDIO_TIMELINE",
  "total_duration_sec": 15.2,
  "target_resolution": {
    "width": 1920,
    "height": 1080,
    "fps": 30,
    "aspect_ratio": "16:9"
  },
  "style_profile": {
    "preset": "cinematic",
    "max_zoom": 1.25,
    "max_pan_distance": 0.35,
    "movement_speed": 1.0,
    "camera_easing": "EASE_IN_OUT",
    "speech_balloon_policy": "BALANCED"
  },
  "scenes": [
    {
      "scene_id": "sc_01",
      "sequence": 1,
      "title": "Confrontation",
      "start_time": 0.0,
      "end_time": 15.2,
      "shots": [
        {
          "shot_id": "shot_sc_01_01",
          "scene_id": "sc_01",
          "sequence_in_scene": 1,
          "sequence_global": 1,
          "source_asset_id": "panel_01",
          "start_time": 0.0,
          "end_time": 4.5,
          "motion_type": "ESTABLISHING_MOVE",
          "camera_start": {
            "center_x": 0.5,
            "center_y": 0.5,
            "zoom": 1.0,
            "rotation": 0.0
          },
          "camera_end": {
            "center_x": 0.5,
            "center_y": 0.5,
            "zoom": 1.08,
            "rotation": 0.0
          },
          "easing": "SMOOTHSTEP",
          "locked": false
        }
      ]
    }
  ],
  "total_shots": 1,
  "warnings": [],
  "hash": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855"
}
```
