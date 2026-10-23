import type { SmartBackgroundPreset, SmartBackgroundSettings, StoryEditorState, VideoScene } from "@panelflow/shared-types";

export const DEFAULT_BACKGROUND: Readonly<SmartBackgroundSettings> = Object.freeze({
  version: 1, enabled: true, preset: "duplicate_blur", source_mode: "follow_active_visual",
  color: "#09090b", color_secondary: "#27272a", blur_sigma: 32, zoom: 1,
  focal_x: .5, focal_y: .5, brightness: -.04, saturation: .85, tint: "#000000",
  tint_opacity: 0, opacity: 1, vignette: 0, edge_shadow: 0, glow: 0,
  motion: "none", motion_amount: .08, foreground_fit: "contain", foreground_x: .5,
  foreground_y: .5, auto_only_when_needed: true,
});

export function createBackgroundPreset(preset: SmartBackgroundPreset): SmartBackgroundSettings {
  return { ...DEFAULT_BACKGROUND, preset, enabled: preset !== "none",
    ...(preset !== "duplicate_blur" ? { blur_sigma: 0, brightness: 0, saturation: 1 } : {}),
    ...(preset === "solid" || preset === "gradient" || preset === "custom_image" ? { auto_only_when_needed: false } : {}),
    ...(preset === "custom_image" ? { source_mode: "custom_image" as const } : {}),
  };
}

export function normalizeBackground(input: Partial<SmartBackgroundSettings>): SmartBackgroundSettings {
  const result = { ...DEFAULT_BACKGROUND, ...input, version: 1 as const };
  const bounds: Partial<Record<keyof SmartBackgroundSettings, [number, number]>> = {
    blur_sigma: [0, 100], zoom: [1, 3], focal_x: [0, 1], focal_y: [0, 1], brightness: [-1, 1],
    saturation: [0, 2], tint_opacity: [0, 1], opacity: [0, 1], vignette: [0, 1], edge_shadow: [0, 1],
    glow: [0, 1], motion_amount: [0, .5], foreground_x: [0, 1], foreground_y: [0, 1],
  };
  for (const [key, [min, max]] of Object.entries(bounds)) {
    const value = input[key as keyof SmartBackgroundSettings];
    (result as any)[key] = typeof value === "number" && Number.isFinite(value)
      ? Math.min(max, Math.max(min, value)) : DEFAULT_BACKGROUND[key as keyof SmartBackgroundSettings];
  }
  for (const key of ["color", "color_secondary", "tint"] as const) {
    if (!/^#[\da-f]{6}$/i.test(result[key])) result[key] = DEFAULT_BACKGROUND[key];
  }
  return result;
}

export function resolveBackground(state: Pick<StoryEditorState, "background_default">, scene?: VideoScene | null): SmartBackgroundSettings | undefined {
  const input = scene?.background ?? state.background_default;
  return input ? normalizeBackground(input) : undefined;
}
