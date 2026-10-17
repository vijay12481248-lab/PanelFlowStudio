# Motion Style Profiles & Pacing Configuration

## 1. Overview

A `MotionStyleProfile` governs the aesthetic pacing, camera velocity, zoom intensity, and effect restraint applied during visual planning.

---

## 2. Standard Presets

| Parameter | Subtle | Cinematic (Default) | Energetic | Minimal |
|:---|:---:|:---:|:---:|:---:|
| `max_zoom` | 1.15 | 1.25 | 1.40 | 1.05 |
| `max_pan_distance` | 0.25 | 0.35 | 0.50 | 0.15 |
| `min_shot_duration` | 2.0s | 1.8s | 1.2s | 2.5s |
| `movement_speed` | 0.8 | 1.0 | 1.4 | 0.5 |
| `camera_easing` | `EASE_IN_OUT` | `SMOOTHSTEP` | `EASE_IN_OUT` | `LINEAR` |
| `transition_duration` | 0.4s | 0.5s | 0.3s | 0.6s |
| `allow_camera_shake` | `False` | `True` | `True` | `False` |

---

## 3. Speech Balloon Policies

Controls whether camera crops prioritize speaker artwork, speech bubbles, or full panel framing:

1. **`AVOID_BALLOONS`**:
   The camera pushes directly into character faces and silhouettes, attempting to crop out or minimize textual speech bubbles when character coordinates exist.

2. **`BALANCED` (Default)**:
   Balances character framing with surrounding narrative context. Ideal for wide webtoon panels.

3. **`SHOW_BALLOONS`**:
   Frames speech balloons explicitly when dialogue begins, aiding viewer reading comfort in rapid pacing.

---

## 4. Effect Budget Parameters

Restrains visual effects to avoid over-stimulating viewers:

- `max_effects_per_scene`: Maximum 3 visual effects per scene.
- `min_shake_interval_sec`: Minimum 4.0 seconds between camera shake effects.
- `max_shake_duration_sec`: Maximum 0.6 seconds per shake burst.
- `max_flash_intensity`: Maximum 0.8 brightness level.
