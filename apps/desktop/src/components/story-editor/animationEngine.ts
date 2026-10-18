import type {
  VisualLayer,
  VideoScene,
  AnimationEasing,
  AnimatableProperty,
  PropertyKeyframe,
  PropertyTrack,
  LayerAnimationConfig,
  MotionPresetType,
  SceneCameraPreset,
  SceneCameraConfig,
  SceneTransitionType,
} from "@panelflow/shared-types";

// ========================================================
// Easing Math (Pure, Deterministic, Zero Frame-to-Frame Drift)
// ========================================================

export function applyEasing(
  t: number,
  easing: AnimationEasing = "ease_in_out",
  controlPoints?: [number, number, number, number]
): number {
  const clamped = Math.max(0, Math.min(1, t));

  switch (easing) {
    case "linear":
      return clamped;
    case "ease_in":
      return clamped * clamped;
    case "ease_out":
      return clamped * (2 - clamped);
    case "ease_in_out":
      return clamped < 0.5
        ? 2 * clamped * clamped
        : -1 + (4 - 2 * clamped) * clamped;
    case "cubic_bezier": {
      if (!controlPoints) return clamped;
      const [p1x, p1y, p2x, p2y] = controlPoints;
      // Approximate cubic bezier evaluation
      const u = 1 - clamped;
      return 3 * u * u * clamped * p1y + 3 * u * clamped * clamped * p2y + clamped * clamped * clamped;
    }
    default:
      return clamped;
  }
}

// ========================================================
// Interpolate Property Track Keyframes
// ========================================================

export function interpolateTrackKeyframes(
  track: PropertyTrack,
  timeOffsetSec: number,
  baseValue: number
): number {
  if (!track.enabled || !track.keyframes || track.keyframes.length === 0) {
    return baseValue;
  }

  const sorted = [...track.keyframes].sort((a, b) => a.time_offset_sec - b.time_offset_sec);

  // Before first keyframe
  if (timeOffsetSec <= sorted[0].time_offset_sec) {
    return sorted[0].value;
  }

  // After last keyframe
  if (timeOffsetSec >= sorted[sorted.length - 1].time_offset_sec) {
    return sorted[sorted.length - 1].value;
  }

  // Find surrounding keyframe pair
  for (let i = 0; i < sorted.length - 1; i++) {
    const k1 = sorted[i];
    const k2 = sorted[i + 1];

    if (timeOffsetSec >= k1.time_offset_sec && timeOffsetSec <= k2.time_offset_sec) {
      const segmentDuration = k2.time_offset_sec - k1.time_offset_sec;
      if (segmentDuration <= 0) return k2.value;

      const rawProgress = (timeOffsetSec - k1.time_offset_sec) / segmentDuration;
      const easedProgress = applyEasing(rawProgress, k1.easing || "ease_in_out", k1.control_points);
      return k1.value + (k2.value - k1.value) * easedProgress;
    }
  }

  return baseValue;
}

// ========================================================
// Layer Transform Evaluation
// ========================================================

export interface EvaluatedLayerTransform {
  x: number;
  y: number;
  scale: number;
  rotation: number;
  opacity: number;
  blur: number;
  isActive: boolean;
  progress: number;
}

export function evaluateLayerTransform(
  layer: VisualLayer,
  scene: VideoScene,
  playheadSec: number
): EvaluatedLayerTransform {
  const layerStart = layer.start_offset_sec ?? 0;
  const layerDuration = layer.duration_sec ?? scene.duration_sec;
  const elapsedInScene = playheadSec - scene.start_time_sec;

  // Layer active window (with small 0.05s tolerance for smooth boundaries)
  const isActive =
    elapsedInScene >= layerStart - 0.05 &&
    elapsedInScene <= layerStart + layerDuration + 0.05;

  const rawProgress = layerDuration > 0
    ? Math.max(0, Math.min(1, (elapsedInScene - layerStart) / layerDuration))
    : 0;

  const easing: AnimationEasing =
    layer.animation?.easing || layer.motion_easing || "ease_in_out";
  const progress = applyEasing(rawProgress, easing);

  const intensity = layer.animation?.intensity ?? layer.motion_intensity ?? 1.0;

  // Base transform
  let finalX = layer.transform.x;
  let finalY = layer.transform.y;
  let finalScale = layer.transform.scale;
  let finalRotation = layer.transform.rotation;
  let finalOpacity = layer.transform.opacity;
  let finalBlur = 0;

  // 1. Check if layer has custom keyframe tracks
  const animConfig = layer.animation_config || layer.animation;
  const tracksList: PropertyTrack[] = animConfig?.tracks
    ? Array.isArray(animConfig.tracks)
      ? animConfig.tracks
      : Object.values(animConfig.tracks)
    : [];

  if (animConfig?.enabled && tracksList.length > 0) {
    const timeInLayer = Math.max(0, Math.min(layerDuration, elapsedInScene - layerStart));

    for (const track of tracksList) {
      if (track.enabled === false) continue;
      switch (track.property) {
        case "x":
          finalX = interpolateTrackKeyframes(track, timeInLayer, layer.transform.x);
          break;
        case "y":
          finalY = interpolateTrackKeyframes(track, timeInLayer, layer.transform.y);
          break;
        case "scale":
          finalScale = interpolateTrackKeyframes(track, timeInLayer, layer.transform.scale);
          break;
        case "rotation":
          finalRotation = interpolateTrackKeyframes(track, timeInLayer, layer.transform.rotation);
          break;
        case "opacity":
          finalOpacity = interpolateTrackKeyframes(track, timeInLayer, layer.transform.opacity);
          break;
        case "blur":
          finalBlur = interpolateTrackKeyframes(track, timeInLayer, 0);
          break;
      }
    }
  } else {
    // 2. Evaluate Preset Motion / Animation
    const preset = animConfig?.preset || layer.motion_preset || "none";
    const direction = animConfig?.direction || layer.motion_direction || "right";

    switch (preset) {
      case "slow_zoom_in":
        finalScale = layer.transform.scale * (1.0 + 0.16 * progress * intensity);
        break;
      case "slow_zoom_out":
        finalScale = layer.transform.scale * (1.16 - 0.16 * progress * intensity);
        break;
      case "pan_left":
        finalX = layer.transform.x + (8 * (0.5 - progress) * intensity);
        break;
      case "pan_right":
        finalX = layer.transform.x - (8 * (0.5 - progress) * intensity);
        break;
      case "pan_up":
        finalY = layer.transform.y + (6 * (0.5 - progress) * intensity);
        break;
      case "pan_down":
        finalY = layer.transform.y - (6 * (0.5 - progress) * intensity);
        break;
      case "diagonal_pan":
        finalX = layer.transform.x + (6 * (0.5 - progress) * intensity);
        finalY = layer.transform.y + (4 * (0.5 - progress) * intensity);
        break;
      case "slide_in_left":
        if (progress < 0.4) {
          finalX = layer.transform.x - (1 - progress / 0.4) * 28 * intensity;
        }
        break;
      case "slide_in_right":
        if (progress < 0.4) {
          finalX = layer.transform.x + (1 - progress / 0.4) * 28 * intensity;
        }
        break;
      case "slide_in_top":
        if (progress < 0.4) {
          finalY = layer.transform.y - (1 - progress / 0.4) * 25 * intensity;
        }
        break;
      case "slide_in_bottom":
        if (progress < 0.4) {
          finalY = layer.transform.y + (1 - progress / 0.4) * 25 * intensity;
        }
        break;
      case "slide_out_left":
        if (progress > 0.6) {
          finalX = layer.transform.x - ((progress - 0.6) / 0.4) * 30 * intensity;
        }
        break;
      case "slide_out_right":
        if (progress > 0.6) {
          finalX = layer.transform.x + ((progress - 0.6) / 0.4) * 30 * intensity;
        }
        break;
      case "move_left":
        finalX = layer.transform.x - progress * 15 * intensity;
        break;
      case "move_right":
        finalX = layer.transform.x + progress * 15 * intensity;
        break;
      case "move_up":
        finalY = layer.transform.y - progress * 12 * intensity;
        break;
      case "move_down":
        finalY = layer.transform.y + progress * 12 * intensity;
        break;
      case "rise":
        finalY = layer.transform.y + (1 - progress) * 15 * intensity;
        finalOpacity = layer.transform.opacity * Math.min(1, 0.4 + 0.6 * progress);
        break;
      case "fall":
        finalY = layer.transform.y - (1 - progress) * 15 * intensity;
        finalOpacity = layer.transform.opacity * Math.min(1, 0.4 + 0.6 * progress);
        break;
      case "scale_up":
        finalScale = layer.transform.scale * (0.9 + 0.25 * progress * intensity);
        break;
      case "scale_down":
        finalScale = layer.transform.scale * (1.2 - 0.25 * progress * intensity);
        break;
      case "rotate_cw":
        finalRotation = layer.transform.rotation + progress * 15 * intensity;
        break;
      case "rotate_ccw":
        finalRotation = layer.transform.rotation - progress * 15 * intensity;
        break;
      case "fade_in":
        finalOpacity = layer.transform.opacity * (progress < 0.35 ? progress / 0.35 : 1.0);
        break;
      case "fade_out":
        finalOpacity = layer.transform.opacity * (progress > 0.65 ? Math.max(0, (1 - progress) / 0.35) : 1.0);
        break;
      case "fade_in_out":
        if (progress < 0.25) {
          finalOpacity = layer.transform.opacity * (progress / 0.25);
        } else if (progress > 0.75) {
          finalOpacity = layer.transform.opacity * Math.max(0, (1 - progress) / 0.25);
        }
        break;
      case "opacity_reveal":
        finalOpacity = layer.transform.opacity * (0.2 + 0.8 * progress);
        finalScale = layer.transform.scale * (0.95 + 0.05 * progress);
        break;
      case "blur":
        finalBlur = (1 - progress) * 10 * intensity;
        break;
      case "flash":
        if (progress < 0.15) {
          finalOpacity = 1.0;
        } else if (progress < 0.4) {
          finalOpacity = 0.4 + 0.6 * ((0.4 - progress) / 0.25);
        }
        break;
      case "shake_impact":
        if (progress < 0.25) {
          const decay = 1 - progress / 0.25;
          finalX += Math.sin(progress * 50) * 2.5 * intensity * decay;
          finalY += Math.cos(progress * 50) * 2.5 * intensity * decay;
        }
        break;
      default:
        break;
    }
  }

  return {
    x: finalX,
    y: finalY,
    scale: Math.max(0.01, finalScale),
    rotation: finalRotation,
    opacity: Math.max(0, Math.min(1, finalOpacity)),
    blur: Math.max(0, finalBlur),
    isActive,
    progress,
  };
}

// ========================================================
// Camera Transform Evaluation (Logically Separate)
// ========================================================

export interface EvaluatedCameraTransform {
  zoom: number;
  panX: number;
  panY: number;
}

export function evaluateCameraTransform(
  scene: VideoScene,
  playheadSec: number
): EvaluatedCameraTransform {
  if (!scene.camera_motion || scene.camera_motion.preset === "static") {
    return { zoom: 1.0, panX: 0, panY: 0 };
  }

  const cam = scene.camera_motion;
  const startOffset = cam.start_offset_sec ?? 0;
  const duration = cam.duration_sec ?? scene.duration_sec;
  const elapsed = playheadSec - scene.start_time_sec;

  const rawProgress = duration > 0 ? Math.max(0, Math.min(1, (elapsed - startOffset) / duration)) : 0;
  const progress = applyEasing(rawProgress, cam.easing || "ease_in_out");

  let zoom = 1.0;
  let panX = 0;
  let panY = 0;

  switch (cam.preset) {
    case "slow_zoom_in":
      zoom = 1.0 + 0.15 * progress;
      break;
    case "slow_zoom_out":
      zoom = 1.15 - 0.15 * progress;
      break;
    case "pan_left":
      panX = 6 * (0.5 - progress);
      break;
    case "pan_right":
      panX = -6 * (0.5 - progress);
      break;
    case "pan_up":
      panY = 5 * (0.5 - progress);
      break;
    case "pan_down":
      panY = -5 * (0.5 - progress);
      break;
    case "diagonal_pan":
      panX = 5 * (0.5 - progress);
      panY = 4 * (0.5 - progress);
      break;
    case "custom":
      zoom = cam.zoom_start + (cam.zoom_end - cam.zoom_start) * progress;
      panX = cam.pan_x_start + (cam.pan_x_end - cam.pan_x_start) * progress;
      panY = cam.pan_y_start + (cam.pan_y_end - cam.pan_y_start) * progress;
      break;
    default:
      break;
  }

  return { zoom, panX, panY };
}

// ========================================================
// Scene Transition Evaluation
// ========================================================

export interface EvaluatedTransitionStyle {
  opacity: number;
  filter: string;
  clipPath?: string;
  overlayColor?: string;
  overlayOpacity?: number;
}

export function evaluateSceneTransition(
  scene: VideoScene,
  playheadSec: number
): EvaluatedTransitionStyle | null {
  const transition = scene.transition_in;
  if (!transition || transition === "none" || transition === "cut") {
    return null;
  }

  const duration = scene.transition_duration_sec ?? 0.6;
  const elapsed = playheadSec - scene.start_time_sec;

  // Transition active only during entrance interval
  if (elapsed < 0 || elapsed > duration) {
    return null;
  }

  const p = Math.max(0, Math.min(1, elapsed / duration));

  switch (transition) {
    case "fade":
    case "fade_from_black":
      return {
        opacity: p,
        filter: "none",
        overlayColor: "#000000",
        overlayOpacity: 1 - p,
      };
    case "fade_to_black":
      return {
        opacity: 1,
        filter: "none",
        overlayColor: "#000000",
        overlayOpacity: p < 0.5 ? p * 2 : (1 - p) * 2,
      };
    case "impact_flash":
      return {
        opacity: 1,
        filter: p < 0.3 ? `brightness(${1 + (1 - p / 0.3) * 2})` : "none",
        overlayColor: "#ffffff",
        overlayOpacity: p < 0.4 ? (1 - p / 0.4) * 0.8 : 0,
      };
    case "cross_dissolve":
    case "dissolve":
      return {
        opacity: p,
        filter: "none",
      };
    case "wipe_left":
      return {
        opacity: 1,
        filter: "none",
        clipPath: `inset(0 0 0 ${(1 - p) * 100}%)`,
      };
    case "wipe_right":
      return {
        opacity: 1,
        filter: "none",
        clipPath: `inset(0 ${(1 - p) * 100}% 0 0)`,
      };
    default:
      return null;
  }
}

// ========================================================
// Motion Path Trajectory Visualization Points
// ========================================================

export interface MotionPathPoint {
  x: number;
  y: number;
  progress: number;
}

export function computeMotionPathPoints(
  layer: VisualLayer,
  scene: VideoScene,
  samples: number = 12
): MotionPathPoint[] {
  const points: MotionPathPoint[] = [];
  const layerStart = layer.start_offset_sec ?? 0;
  const layerDuration = layer.duration_sec ?? scene.duration_sec;

  for (let i = 0; i <= samples; i++) {
    const rawP = i / samples;
    const sampleSec = scene.start_time_sec + layerStart + rawP * layerDuration;
    const evaluated = evaluateLayerTransform(layer, scene, sampleSec);
    points.push({
      x: evaluated.x,
      y: evaluated.y,
      progress: rawP,
    });
  }

  return points;
}
