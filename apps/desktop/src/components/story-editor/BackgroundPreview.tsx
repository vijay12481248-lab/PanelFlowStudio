import React, { useEffect, useId, useState } from "react";
import type { SmartBackgroundSettings, StoryEditorState, VideoScene, VisualLayer } from "@panelflow/shared-types";
import { evaluateLayerTransform } from "./animationEngine";

function trackVisible(state: StoryEditorState, key: string, alias: string) {
  return (state.track_states?.[key] ?? state.track_states?.[alias])?.visible !== false;
}

export function isBackgroundSourceVisible(state: StoryEditorState, scene: VideoScene, layer: VisualLayer): boolean {
  if (!trackVisible(state, "Visuals", "visuals") || layer.visible === false) return false;
  if (scene.layers.indexOf(layer) > 0 && !trackVisible(state, "Layer 2", "layer2")) return false;
  const elapsed = state.playhead_sec - scene.start_time_sec;
  const start = layer.start_offset_sec ?? 0;
  const end = start + (layer.duration_sec ?? scene.duration_sec);
  return elapsed >= start && elapsed < end && evaluateLayerTransform(layer, scene, state.playhead_sec).opacity > 0;
}

export function resolveBackgroundSource(state: StoryEditorState, scene: VideoScene, settings: SmartBackgroundSettings): VisualLayer | undefined {
  if (settings.source_mode === "custom_image") return undefined;
  if (settings.source_mode === "pinned_layer") return scene.layers.find(layer => layer.id === settings.source_layer_id);
  return scene.layers.find(layer => isBackgroundSourceVisible(state, scene, layer));
}

export function foregroundSize(sourceWidth: number, sourceHeight: number, canvasWidth: number, canvasHeight: number, fit: "contain" | "cover") {
  if (sourceWidth <= 0 || sourceHeight <= 0) return undefined;
  const scale = (fit === "cover" ? Math.max : Math.min)(canvasWidth / sourceWidth, canvasHeight / sourceHeight);
  return { width: sourceWidth * scale, height: sourceHeight * scale };
}

interface Props {
  settings: SmartBackgroundSettings;
  sourceUrl?: string;
  width: number;
  height: number;
  progress: number;
  sourceLayer?: VisualLayer;
}

/** Derived image only: it deliberately lives outside the scene-camera transform. */
export const BackgroundPreview: React.FC<Props> = ({ settings: s, sourceUrl, width, height, progress, sourceLayer }) => {
  const filterId = `background-${useId().replace(/:/g, "")}`;
  const [image, setImage] = useState<{ url: string; width: number; height: number } | null>(null);
  useEffect(() => {
    setImage(null);
    if (!sourceUrl) return;
    let disposed = false;
    const img = new Image();
    img.onload = () => { if (!disposed) setImage({ url: sourceUrl, width: img.naturalWidth, height: img.naturalHeight }); };
    img.onerror = () => { if (!disposed) setImage(null); };
    img.src = sourceUrl;
    return () => { disposed = true; img.onload = null; img.onerror = null; };
  }, [sourceUrl]);
  if (!s.enabled || s.preset === "none") return null;
  const loaded = image?.url === sourceUrl ? image : null;
  const sourceScaledDown = (sourceLayer?.transform?.scale ?? 1) < 0.999 || Math.abs(sourceLayer?.transform?.x ?? 0) > 0.5 || Math.abs(sourceLayer?.transform?.y ?? 0) > 0.5 || (sourceLayer?.transform?.rotation ?? 0) !== 0 || (sourceLayer?.transform?.opacity ?? 1) < 0.995;
  if (["duplicate_blur", "mirror", "edge_stretch", "gradient"].includes(s.preset) && s.auto_only_when_needed && loaded && Math.abs(loaded.width / loaded.height - width / height) < .001 && !sourceScaledDown) return <div aria-hidden="true" className="absolute inset-0 pointer-events-none" style={{ background: s.color }} />;
  const p = Math.max(0, Math.min(1, progress));
  const amount = s.motion_amount ?? .08;
  const pan = s.motion === "pan_left" || s.motion === "pan_right";
  const zoom = s.zoom * (s.motion === "slow_zoom" ? 1 + amount * p : pan ? 1 + amount : 1);
  const focalX = Math.max(0, Math.min(1, s.focal_x + (pan ? (s.motion === "pan_right" ? 1 : -1) * amount * (p - .5) : 0)));
  const sigma = s.blur_sigma * height / 1080;
  const cover = loaded ? foregroundSize(loaded.width, loaded.height, width, height, "cover") : undefined;
  const stretch = s.preset === "edge_stretch";
  const imageWidth = (stretch ? width : cover?.width ?? width) * zoom;
  const imageHeight = (stretch ? height : cover?.height ?? height) * zoom;
  const saturation = s.saturation;
  const weights = [.299, .587, .114];
  const saturationMatrix = [0, 1, 2].flatMap(row => [...weights.map((weight, column) => weight * (1 - saturation) + (row === column ? saturation : 0)), 0, 0]).concat([0, 0, 0, 1, 0]).join(" ");
  const vignetteStops = Array.from({ length: 17 }, (_, index) => { const t = index / 16; return `rgba(0,0,0,${s.vignette * t * t}) ${t * 100}%`; }).join(",");
  const imageFill = !["solid", "gradient"].includes(s.preset) && sourceUrl;
  return <div aria-hidden="true" data-background-preset={s.preset} className="absolute inset-0 overflow-hidden pointer-events-none" style={{ background: s.color }}>
    <svg width="0" height="0" className="absolute" aria-hidden="true"><defs><filter id={filterId} x="0" y="0" width="100%" height="100%" colorInterpolationFilters="sRGB">
      <feGaussianBlur in="SourceGraphic" stdDeviation={sigma} edgeMode="duplicate" result="soft" />
      <feColorMatrix in="soft" type="matrix" values={saturationMatrix} result="saturated" />
      <feComponentTransfer in="saturated" result="adjusted"><feFuncR type="linear" slope="1" intercept={s.brightness} /><feFuncG type="linear" slope="1" intercept={s.brightness} /><feFuncB type="linear" slope="1" intercept={s.brightness} /></feComponentTransfer>
      <feFlood floodColor={s.tint} result="tint" />
      <feComposite in="tint" in2="adjusted" operator="arithmetic" k1="0" k2={s.tint_opacity ?? 0} k3={1 - (s.tint_opacity ?? 0)} k4="0" result="tinted" />
      <feGaussianBlur in="tinted" stdDeviation={((s.glow ?? 0) > 0 ? 40 : 0) * height / 1080} edgeMode="duplicate" result="light" />
      <feBlend in="tinted" in2="light" mode="screen" result="screened" />
      <feComposite in="tinted" in2="screened" operator="arithmetic" k1="0" k2={1 - (s.glow ?? 0)} k3={s.glow ?? 0} k4="0" />
    </filter></defs></svg>
    <div className="absolute inset-0 overflow-hidden" style={{ opacity: s.opacity }}>
      <div className="absolute inset-0" style={{ filter: `url(#${filterId})` }}><div className="absolute inset-0 overflow-hidden" style={{ background: s.preset === "gradient" ? `linear-gradient(to bottom, ${s.color}, ${s.color_secondary})` : s.color }}>
        {imageFill && <img src={sourceUrl} alt="" draggable={false} style={{ position: "absolute", maxWidth: "none", width: imageWidth, height: imageHeight, left: -(imageWidth - width) * focalX, top: -(imageHeight - height) * s.focal_y, objectFit: stretch ? "fill" : "cover", objectPosition: `${focalX * 100}% ${s.focal_y * 100}%`, transform: s.preset === "mirror" ? "scaleX(-1)" : undefined, clipPath: sourceLayer?.clip_path || (sourceLayer?.polygon_points && sourceLayer.polygon_points.length >= 3 ? `polygon(${sourceLayer.polygon_points.map(point => `${point.x}% ${point.y}%`).join(",")})` : undefined) }} />}
      </div></div>
      {s.vignette > 0 && <div className="absolute inset-0" style={{ background: `radial-gradient(ellipse 70.710678% 70.710678% at center, ${vignetteStops})` }} />}
    </div>
  </div>;
};
