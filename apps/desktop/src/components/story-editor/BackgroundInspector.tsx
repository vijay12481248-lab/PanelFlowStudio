import React, { useEffect, useRef, useState } from "react";
import { api } from "@panelflow/api-client";
import type { SmartBackgroundPreset, SmartBackgroundSettings, StoryEditorState, VideoScene } from "@panelflow/shared-types";
import { createBackgroundPreset, resolveBackground } from "./backgroundSettings";

interface Props {
  state: StoryEditorState;
  scene: VideoScene;
  projectId?: string;
  onUpdateState: (updater: (prev: StoryEditorState) => StoryEditorState) => void;
}
const presets: [SmartBackgroundPreset, string, string][] = [
  ["none", "None", "transparent"], ["solid", "Solid Color", "#27272a"],
  ["duplicate_blur", "Duplicate Blur", "radial-gradient(ellipse at 35% 50%, #b493b7, #302c4f 65%, #171525)"],
  ["gradient", "Gradient", "linear-gradient(135deg, #09090b, #636673)"],
  ["mirror", "Mirror", "linear-gradient(90deg, #675b7e, #c2afbf, #675b7e)"],
  ["edge_stretch", "Edge Stretch", "linear-gradient(90deg, #74618c, #c4b6bd 50%, #74618c)"],
  ["custom_image", "Custom Image", "linear-gradient(145deg, #314d57, #9caa92)"],
];
const inputClass = "w-full min-w-0 rounded border border-zinc-700 bg-zinc-950 px-2 py-1.5 text-xs text-zinc-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-400";
const buttonClass = "rounded border border-zinc-700 px-2 py-1.5 text-xs text-zinc-300 hover:bg-zinc-800 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-400 disabled:opacity-40";

export const BackgroundInspector: React.FC<Props> = ({ state, scene, projectId, onUpdateState }) => {
  const settings = resolveBackground(state, scene) ?? createBackgroundPreset("none");
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [applyScope, setApplyScope] = useState<"scene" | "all">("scene");
  const uploadToken = useRef(0);
  useEffect(() => { uploadToken.current++; setUploading(false); setError(null); return () => { uploadToken.current++; }; }, [scene.id]);
  const applySettingsToScenes = (
    prev: StoryEditorState,
    targetSettings: SmartBackgroundSettings,
    allScenes: boolean
  ): StoryEditorState => {
    if (allScenes) {
      return {
        ...prev,
        background_default: { ...targetSettings },
        scenes: prev.scenes.map((current) => ({
          ...current,
          background: {
            ...targetSettings,
            ...(targetSettings.source_mode === "pinned_layer" && current.id !== scene.id
              ? { source_mode: "follow_active_visual" as const, source_layer_id: undefined }
              : {}),
          },
        })),
      };
    }
    return {
      ...prev,
      scenes: prev.scenes.map((current) =>
        current.id === scene.id
          ? { ...current, background: { ...targetSettings } }
          : current
      ),
    };
  };
  const change = (patch: Partial<SmartBackgroundSettings>) => onUpdateState(prev => {
    const currentResolved = resolveBackground(prev, scene) ?? createBackgroundPreset("duplicate_blur");
    const nextSettings = { ...currentResolved, ...patch };
    return applySettingsToScenes(prev, nextSettings, applyScope === "all");
  });
  const choosePreset = (preset: SmartBackgroundPreset) => {
    const presetSettings = createBackgroundPreset(preset);
    onUpdateState(prev => applySettingsToScenes(prev, presetSettings, applyScope === "all"));
  };
  const copyToAllScenes = (overrideSettings?: SmartBackgroundSettings) => {
    onUpdateState(prev => {
      const currentScene = prev.scenes.find(s => s.id === scene.id) ?? scene;
      const active = (overrideSettings && typeof overrideSettings === "object" && "preset" in overrideSettings)
        ? overrideSettings
        : resolveBackground(prev, currentScene) ?? createBackgroundPreset("duplicate_blur");
      const target = { ...active, enabled: active.preset !== "none" ? true : active.enabled };
      return applySettingsToScenes(prev, target, true);
    });
  };
  const slider = (key: keyof SmartBackgroundSettings, label: string, min: number, max: number, step = .01) => <label key={key} className="block space-y-1 text-xs text-zinc-400">
    <span className="flex items-center justify-between gap-2"><span>{label}</span><output className="font-mono text-zinc-200">{Number(settings[key]).toFixed(step >= 1 ? 0 : 2)}</output></span>
    <input aria-label={label} type="range" min={min} max={max} step={step} value={Number(settings[key])} onChange={event => change({ [key]: Number(event.target.value) })} className="w-full accent-indigo-400" />
  </label>;
  const color = (key: "color" | "color_secondary" | "tint", label: string) => <label className="flex items-center justify-between gap-2 text-xs text-zinc-400">{label}<input aria-label={label} type="color" value={settings[key]} onChange={event => change({ [key]: event.target.value })} className="h-8 w-12 cursor-pointer rounded border border-zinc-700 bg-zinc-950" /></label>;
  const upload = async (file?: File) => {
    if (!file) return;
    const token = ++uploadToken.current;
    setUploading(true); setError(null);
    try {
      const result = await api.uploadBackgroundImage(projectId || state.project_id, file);
      if (token === uploadToken.current) change({ preset: "custom_image", enabled: true, source_mode: "custom_image", custom_image_url: result.image_url });
    } catch (cause) { if (token === uploadToken.current) setError(cause instanceof Error ? cause.message : "Image upload failed. Please retry."); }
    finally { if (token === uploadToken.current) setUploading(false); }
  };
  return <section aria-label="Scene background" className="space-y-4 pb-4">
    <div className="flex flex-wrap items-center justify-between gap-2">
      <h4 className="text-xs font-semibold text-zinc-200">Background</h4>
      <span className="text-[10px] text-zinc-500">
        {applyScope === "all"
          ? "Applying to all timeline panels"
          : scene.background
          ? "Scene override"
          : state.background_default
          ? "Inherits project default"
          : "No background"}
      </span>
    </div>
    <div className="grid grid-cols-2 gap-2" aria-label="Background presets">
      {presets.map(([preset, name, background]) => <button type="button" key={preset} onClick={() => choosePreset(preset)} aria-pressed={settings.preset === preset} className={`${buttonClass} text-left ${settings.preset === preset ? "border-indigo-400 bg-indigo-950/40" : ""}`}>
        <span aria-hidden="true" className="mb-1.5 block h-10 overflow-hidden rounded border border-white/10" style={{ background }}><span className="mx-auto mt-1 block h-8 w-5 rounded-sm border border-white/30 bg-white/25" /></span>{name}
      </button>)}
    </div>
    <div className="flex items-center gap-1.5 p-1 rounded-md bg-zinc-900 border border-zinc-800" role="group" aria-label="Background application scope">
      <span className="text-[11px] text-zinc-400 font-medium pl-1">Apply to:</span>
      <button
        type="button"
        aria-pressed={applyScope === "scene"}
        onClick={() => setApplyScope("scene")}
        className={`flex-1 rounded px-2 py-1 text-xs font-medium transition-all ${
          applyScope === "scene"
            ? "bg-indigo-600 text-white shadow-sm"
            : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/60"
        }`}
      >
        Current Panel
      </button>
      <button
        type="button"
        aria-pressed={applyScope === "all"}
        onClick={() => {
          setApplyScope("all");
          copyToAllScenes();
        }}
        className={`flex-1 rounded px-2 py-1 text-xs font-medium transition-all ${
          applyScope === "all"
            ? "bg-indigo-600 text-white shadow-sm"
            : "text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800/60"
        }`}
      >
        All Panels in Timeline
      </button>
    </div>
    <label className="flex items-center gap-2 text-xs text-zinc-200"><input type="checkbox" checked={settings.enabled} onChange={event => change({ enabled: event.target.checked, ...(settings.preset === "none" && event.target.checked ? { preset: "duplicate_blur" as const } : {}) })} />Enable background</label>
    <div className="flex flex-wrap gap-2">
      <button type="button" className={buttonClass} onClick={() => onUpdateState(prev => ({ ...prev, scenes: prev.scenes.map(current => current.id === scene.id ? { ...current, background: undefined } : current) }))}>Use project default</button>
      <button type="button" className={buttonClass} onClick={() => onUpdateState(prev => ({ ...prev, background_default: { ...settings }, scenes: prev.scenes.map(current => current.id === scene.id ? { ...current, background: undefined } : current) }))}>Set as project default</button>
      <button type="button" className={buttonClass} onClick={() => copyToAllScenes()}>Apply to all panels</button>
    </div>
    <label className="block space-y-1 text-xs text-zinc-400"><span>Source</span><select aria-label="Background source" className={inputClass} value={settings.source_mode} onChange={event => change({ source_mode: event.target.value as SmartBackgroundSettings["source_mode"] })}>
      <option value="follow_active_visual">Follow current visual</option><option value="pinned_layer">Pin to visual layer</option><option value="custom_image">Custom image</option>
    </select></label>
    {settings.source_mode === "pinned_layer" && <label className="block space-y-1 text-xs text-zinc-400"><span>Pinned visual layer</span><select aria-label="Pinned visual layer" value={settings.source_layer_id || ""} onChange={event => change({ source_layer_id: event.target.value })} className={inputClass}>
      <option value="">Choose an image layer</option>{scene.layers.map(layer => <option key={layer.id} value={layer.id}>{layer.name || layer.id}</option>)}
    </select><span className="block text-[10px]">Pinned artwork stays fixed when the active visual changes.</span></label>}
    {settings.source_mode === "custom_image" && <div className="space-y-2"><label className="block space-y-1 text-xs text-zinc-400"><span>{uploading ? "Uploading image…" : "Upload background image"}</span><input aria-label="Upload background image" type="file" accept="image/png,image/jpeg,image/webp" disabled={uploading} onChange={event => { void upload(event.target.files?.[0]); event.target.value = ""; }} className={inputClass} /></label>{settings.custom_image_url && <img src={settings.custom_image_url} alt="Custom background" className="h-16 w-full rounded object-cover" />}{error && <p role="alert" className="text-xs text-rose-300">{error}</p>}</div>}
    <fieldset className="space-y-3 border-t border-zinc-800 pt-3"><legend className="text-xs text-zinc-300">Fill and effects</legend>
      {color("color", "Base color")}{settings.preset === "gradient" && color("color_secondary", "Gradient second color")}
      {slider("blur_sigma", "Blur (1080p)", 0, 100, 1)}{slider("zoom", "Background zoom", 1, 3)}
      {slider("focal_x", "Background focus X", 0, 1)}{slider("focal_y", "Background focus Y", 0, 1)}
      {slider("brightness", "Brightness", -1, 1)}{slider("saturation", "Saturation", 0, 2)}
      {color("tint", "Tint color")}{slider("tint_opacity", "Tint intensity", 0, 1)}{slider("opacity", "Background opacity", 0, 1)}
      {slider("vignette", "Vignette", 0, 1)}{slider("edge_shadow", "Edge shadow", 0, 1)}{slider("glow", "Ambient glow", 0, 1)}
      <label className="block space-y-1 text-xs text-zinc-400"><span>Background motion</span><select aria-label="Background motion" value={settings.motion} className={inputClass} onChange={event => change({ motion: event.target.value as SmartBackgroundSettings["motion"] })}><option value="none">Static</option><option value="slow_zoom">Slow zoom</option><option value="pan_left">Pan left</option><option value="pan_right">Pan right</option></select></label>
      {settings.motion !== "none" && slider("motion_amount", "Motion amount", 0, .5)}
    </fieldset>
    <fieldset className="space-y-3 border-t border-zinc-800 pt-3"><legend className="text-xs text-zinc-300">Sharp foreground</legend>
      <label className="block space-y-1 text-xs text-zinc-400"><span>Foreground fit</span><select aria-label="Foreground fit" value={settings.foreground_fit} onChange={event => change({ foreground_fit: event.target.value as "contain" | "cover" })} className={inputClass}><option value="contain">Contain — show full artwork</option><option value="cover">Cover — fill canvas</option></select></label>
      {slider("foreground_x", "Foreground position X", 0, 1)}{slider("foreground_y", "Foreground position Y", 0, 1)}
      <label className="flex items-center gap-2 text-xs text-zinc-400"><input type="checkbox" checked={settings.auto_only_when_needed} onChange={event => change({ auto_only_when_needed: event.target.checked })} />Only fill when aspect ratios differ</label>
    </fieldset>
    <div className="flex flex-wrap gap-2 border-t border-zinc-800 pt-3">
      <button type="button" className={buttonClass} aria-pressed={!!state.background_preview_disabled} onClick={() => onUpdateState(prev => ({ ...prev, background_preview_disabled: !prev.background_preview_disabled }))}>Before / After</button>
      <button type="button" className={buttonClass} onClick={() => choosePreset(settings.preset)}>Reset preset</button>
      <button type="button" className={buttonClass} onClick={() => copyToAllScenes()}>Copy to all scenes</button>
    </div>
    <p className="text-[10px] text-zinc-500">Before / After changes preview only. Use the editor’s Undo and Redo for background edits.</p>
  </section>;
};
