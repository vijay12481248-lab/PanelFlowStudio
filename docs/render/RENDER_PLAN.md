# PanelFlow Studio — RenderPlan Specification

## 1. Overview

The `RenderPlan` is a compiled, frame-accurate recipe that fully specifies the audio-visual instructions required to produce an MP4 video file. It acts as an immutable boundary between high-level editorial/motion planning (`VisualTimeline`, `MasterAudioTimeline`) and low-level rasterization and encoding (`FrameComposer`, `AudioMixer`, `FFmpegEncoder`).

---

## 2. Model Structure

### `RenderPlan`
- `plan_id` (`str`): Unique identifier (e.g. `rplan_c5bde528`).
- `project_id` (`str`): Associated project UUID.
- `total_duration_sec` (`float`): Planned timeline duration in seconds.
- `total_frames` (`int`): Exact integer frame count at target frame rate ($30\text{ fps}$).
- `profile` (`RenderProfile`): Target resolution, framerate, video/audio codec, and CRF parameters.
- `shots` (`List[RenderShotPlan]`): Ordered sequence of frame-accurate shot instructions.
- `audio_tracks` (`List[RenderAudioTrack]`): Multi-track audio definitions for dialogue, music, and SFX.
- `music_policy` (`MusicDurationPolicy`): Policy for background music looping, padding, or truncation.
- `hash` (`str`): SHA-256 fingerprint computed across shot IDs, audio paths, duration, and profile.

### `RenderShotPlan`
- `shot_id` (`str`): Identifier of the shot.
- `scene_id` (`str`): Narrative scene membership.
- `sequence_global` (`int`): 1-indexed global shot index.
- `source_asset_path` (`str`): Absolute filesystem path to the visual source image.
- `start_frame` (`int`): 0-indexed inclusive starting frame.
- `end_frame` (`int`): 0-indexed exclusive ending frame ($[f_{\text{start}}, f_{\text{end}})$).
- `total_frames` (`int`): Number of frames allocated to this shot ($f_{\text{end}} - f_{\text{start}}$).
- `camera_start` (`CameraState`): Camera position $(x, y)$ and zoom at $t = 0.0$.
- `camera_end` (`CameraState`): Camera position $(x, y)$ and zoom at $t = 1.0$.
- `easing` (`EasingFunction`): Interpolation curve (`LINEAR`, `EASE_IN`, `EASE_OUT`, `EASE_IN_OUT`, `SMOOTHSTEP`).
- `motion_type` (`MotionType`): Motion primitive (e.g. `SLOW_ZOOM_IN`, `PAN_RIGHT`, `STATIC_HOLD`).
- `scale_policy` (`ScalePolicy`): `COVER` (full bleed canvas crop) or `CONTAIN` (letterbox/pillarbox).
- `fill_policy` (`BackgroundFillPolicy`): `BLACK`, `BLURRED_SOURCE`, or `SOLID_COLOR`.
- `effects` (`List[EffectInstruction]`): Active visual effects (impact shake, flashes, vignettes).
- `transition_in` / `transition_out` (`TransitionInstruction`): Shot transitions (`HARD_CUT`, `CROSS_DISSOLVE`).
- `captions` (`List[CaptionCue]`): Dialogue subtitle cues displayed during this shot.

### `RenderAudioTrack`
- `track_id` (`str`): Audio track identifier.
- `track_type` (`str`): `dialogue`, `music`, `sfx`, or `ambience`.
- `file_path` (`str`): Absolute path to audio asset (.wav, .ogg, .mp3).
- `start_time` (`float`): Start timestamp in seconds on the master timeline.
- `end_time` (`float`): End timestamp in seconds on the master timeline.
- `gain_db` (`float`): Volume gain offset in decibels.
- `ducking_intervals` (`List[Tuple[float, float, float]]`): Precalculated ducking intervals $(t_{\text{start}}, t_{\text{end}}, \Delta\text{dB})$.

---

## 3. Deterministic Hashing

The plan hash guarantees reproducibility. The SHA-256 hash is computed over a normalized JSON representation:
```json
{
  "project_id": "...",
  "duration": 69.675,
  "frames": 2090,
  "shots": ["shot_scene_01_01", "shot_scene_01_02", ...],
  "audio": ["C:/Tools/.../01_hook.wav", "C:/Tools/.../someone_stayed.ogg", ...],
  "profile": { ... }
}
```

---

## 4. Preflight Validation Contract

Before initiating expensive rasterization, `RenderEngine.preflight_check()` validates:
1. **FFmpeg Runtime**: `ffmpeg` and `ffprobe` executables are discoverable and support `libx264`/`h264_nvenc` and `aac`.
2. **Visual Source Assets**: All paths in `shot.source_asset_path` exist on disk and can be read by PIL.
3. **Audio Tracks**: All paths in `audio_tracks.file_path` exist on disk and can be decoded by `soundfile`.
4. **Frame Continuity**: Total frames $> 0$, shot frame intervals are strictly sequential with zero gaps.
