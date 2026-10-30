import React, { useEffect, useState, useCallback, useRef, useMemo } from "react";
import { api } from "@panelflow/api-client";
import type { MotionPresetInfo, StoryEditorState, VideoScene } from "@panelflow/shared-types";

interface Props {
  state: StoryEditorState;
  scene: VideoScene;
  onUpdateState: (updater: (prev: StoryEditorState) => StoryEditorState) => void;
}

const inputClass =
  "w-full min-w-0 rounded border border-zinc-700 bg-zinc-950 px-2.5 py-1.5 text-xs text-zinc-200 focus-visible:outline focus-visible:outline-2 focus-visible:outline-indigo-400";
const labelClass = "text-[11px] font-medium uppercase tracking-wider text-zinc-400 mb-1 block";

// ── Adobe After Effects & Animora Bezier Solver for Interactive SVG Graph ────

interface BezierPreset {
  id: string;
  name: string;
  x1: number;
  y1: number;
  x2: number;
  y2: number;
  desc: string;
}

const BEZIER_PRESETS: BezierPreset[] = [
  { id: "ae_smooth_glide", name: "Smooth Glide (25/25)", x1: 0.25, y1: 0.1, x2: 0.25, y2: 1.0, desc: "Ultra-smooth continuous keynote deceleration with zero freeze" },
  { id: "liquid_light_wipe", name: "Liquid Light Wipe", x1: 0.25, y1: 0.1, x2: 0.25, y2: 1.0, desc: "Continuous Hermite light beam wipe with specular leading edge" },
  { id: "masked_baseline_reveal", name: "Baseline Track Matte", x1: 0.25, y1: 0.1, x2: 0.25, y2: 1.0, desc: "AE track matte baseline rise with expanding horizon laser" },
  { id: "ae_hero", name: "AE Hero (60/80)", x1: 0.60, y1: 0.0, x2: 0.20, y2: 1.0, desc: "After Effects 60% out / 80% in punchy curve" },
  { id: "ae_pop", name: "AE Pop (15/85)", x1: 0.15, y1: 0.0, x2: 0.15, y2: 1.0, desc: "After Effects explosive onset with smooth settle" },
  { id: "easy_ease", name: "AE Easy Ease (F9)", x1: 0.333, y1: 0.0, x2: 0.667, y2: 1.0, desc: "Standard 33.3% symmetric After Effects ease" },
  { id: "ease_out_expo", name: "Out Expo", x1: 0.16, y1: 1.0, x2: 0.3, y2: 1.0, desc: "Ultra-crisp exponential keynote stop" },
  { id: "ease_out_back", name: "Overshoot", x1: 0.34, y1: 1.56, x2: 0.64, y2: 1.0, desc: "Animora snappy spring pop-in" },
];

function solveBezier(t: number, x1: number, y1: number, x2: number, y2: number): number {
  if (t <= 0) return 0;
  if (t >= 1) return 1;
  let bt = t;
  for (let i = 0; i < 8; i++) {
    const u = 1 - bt;
    const x = 3 * u * u * bt * x1 + 3 * u * bt * bt * x2 + bt * bt * bt - t;
    if (Math.abs(x) < 0.001) break;
    const dx = 3 * u * u * x1 + 6 * u * bt * (x2 - x1) + 3 * bt * bt * (1 - x2);
    if (Math.abs(dx) < 0.0001) break;
    bt -= x / dx;
  }
  bt = Math.max(0, Math.min(1, bt));
  const u = 1 - bt;
  return 3 * u * u * bt * y1 + 3 * u * bt * bt * y2 + bt * bt * bt;
}

export const MotionGraphicInspector: React.FC<Props> = ({ scene, onUpdateState }) => {
  const [presets, setPresets] = useState<MotionPresetInfo[]>([]);
  const [loadingPresets, setLoadingPresets] = useState(false);
  const [previewImage, setPreviewImage] = useState<string | null>(null);
  const [scrubTime, setScrubTime] = useState<number>(1.5);
  const [loadingPreview, setLoadingPreview] = useState(false);

  // Extract current motion graphic configuration from scene
  const motionPresetId = scene.motion_preset_id || "keynote_showcase";
  const motionProps = scene.motion_props || {};
  const duration = scene.duration_sec || 6.0;
  const currentEasing = motionProps.easing_curve || "ae_hero";

  // Selected Bezier preset
  const activeBezier = useMemo(() => {
    return BEZIER_PRESETS.find((p) => p.id === currentEasing) || BEZIER_PRESETS[0];
  }, [currentEasing]);

  // Load presets catalog
  useEffect(() => {
    let active = true;
    setLoadingPresets(true);
    api
      .getMotionPresets()
      .then((res) => {
        if (active) setPresets(res);
      })
      .catch(() => {})
      .finally(() => {
        if (active) setLoadingPresets(false);
      });
    return () => {
      active = false;
    };
  }, []);

  // Update scene props
  const updateMotionConfig = useCallback(
    (presetId: string, newProps: Record<string, any>) => {
      onUpdateState((prev) => ({
        ...prev,
        scenes: prev.scenes.map((s) => {
          if (s.id !== scene.id) return s;
          return {
            ...s,
            type: "motion_graphic",
            motion_preset_id: presetId,
            motion_props: { ...motionProps, ...newProps },
          };
        }),
      }));
    },
    [onUpdateState, scene.id, motionProps]
  );

  // Request single frame preview
  const fetchPreview = useCallback(
    async (presetId: string, props: Record<string, any>, time: number) => {
      setLoadingPreview(true);
      try {
        const res = await api.previewMotionFrame({
          preset_id: presetId,
          timestamp: time,
          duration_sec: duration,
          width: 640,
          height: 360,
          props: props,
          aspect_ratio: props.aspect_ratio || "16:9",
        });
        setPreviewImage(`data:image/jpeg;base64,${res.image_base64}`);
      } catch {
        // Silently preserve previous preview
      } finally {
        setLoadingPreview(false);
      }
    },
    [duration]
  );

  // Debounced preview update on scrub or props change
  const debounceRef = useRef<number | null>(null);
  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = window.setTimeout(() => {
      fetchPreview(motionPresetId, motionProps, scrubTime);
    }, 150);
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [motionPresetId, motionProps, scrubTime, fetchPreview]);

  // Bezier curve SVG geometry calculations
  const svgWidth = 280;
  const svgHeight = 110;
  const padLeft = 24;
  const padRight = 16;
  const padTop = 18;
  const padBottom = 22;
  const plotW = svgWidth - padLeft - padRight;
  const plotH = svgHeight - padTop - padBottom;

  const toPxX = (t: number) => padLeft + t * plotW;
  const toPxY = (val: number) => padTop + (1.0 - (val / 1.4)) * plotH;

  const curvePath = useMemo(() => {
    const steps = 36;
    let d = "";
    for (let i = 0; i <= steps; i++) {
      const t = i / steps;
      const y = solveBezier(t, activeBezier.x1, activeBezier.y1, activeBezier.x2, activeBezier.y2);
      const px = toPxX(t);
      const py = toPxY(y);
      d += `${i === 0 ? "M" : "L"} ${px.toFixed(1)} ${py.toFixed(1)} `;
    }
    return d;
  }, [activeBezier]);

  const scrubProgress = Math.max(0, Math.min(1, scrubTime / Math.max(0.1, duration)));
  const currentCurveVal = solveBezier(
    scrubProgress,
    activeBezier.x1,
    activeBezier.y1,
    activeBezier.x2,
    activeBezier.y2
  );
  const scrubDotX = toPxX(scrubProgress);
  const scrubDotY = toPxY(currentCurveVal);

  return (
    <div className="flex flex-col gap-4 p-3 text-xs text-zinc-300">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-zinc-800 pb-2">
        <span className="font-semibold text-zinc-100 flex items-center gap-1.5">
          <span className="h-2 w-2 rounded-full bg-indigo-500 animate-pulse" />
          Super Motion Graphics
        </span>
        <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-zinc-800 text-zinc-400">
          After Effects &bull; 60fps
        </span>
      </div>

      {/* Live Preview Display */}
      <div className="flex flex-col gap-1.5">
        <div className="relative aspect-video w-full overflow-hidden rounded-lg border border-zinc-800 bg-zinc-950 flex items-center justify-center">
          {previewImage ? (
            <img src={previewImage} alt="Motion Preview" className="h-full w-full object-contain" />
          ) : (
            <span className="text-zinc-600 text-[11px]">Loading procedural preview...</span>
          )}
          {loadingPreview && (
            <div className="absolute top-2 right-2 flex items-center gap-1 rounded bg-black/60 px-1.5 py-0.5 text-[10px] text-zinc-400 backdrop-blur-sm">
              <span className="h-1.5 w-1.5 rounded-full bg-indigo-400 animate-ping" />
              Scrubbing
            </div>
          )}
        </div>

        {/* Scrub Slider */}
        <div className="flex items-center gap-2 mt-1">
          <input
            type="range"
            min="0"
            max={duration}
            step="0.05"
            value={scrubTime}
            onChange={(e) => setScrubTime(parseFloat(e.target.value))}
            className="w-full accent-indigo-500 cursor-pointer h-1.5 bg-zinc-800 rounded-lg"
          />
          <span className="font-mono text-[10px] text-zinc-400 min-w-[36px]">
            {scrubTime.toFixed(2)}s
          </span>
        </div>
      </div>

      {/* Interactive Bezier & AE Speed Graph Inspector */}
      <div className="flex flex-col gap-2 rounded-lg border border-zinc-800 bg-zinc-950/70 p-2.5">
        <div className="flex items-center justify-between">
          <label className="text-[11px] font-medium uppercase tracking-wider text-indigo-400">
            AE Velocity & Speed Graph
          </label>
          <span className="font-mono text-[10px] text-zinc-400">
            P({activeBezier.x1.toFixed(2)}, {activeBezier.y1.toFixed(2)}, {activeBezier.x2.toFixed(2)}, {activeBezier.y2.toFixed(2)})
          </span>
        </div>

        {/* SVG Bezier Curve Visualizer */}
        <div className="relative overflow-hidden rounded border border-zinc-800/80 bg-zinc-900/60 p-1">
          <svg viewBox={`0 0 ${svgWidth} ${svgHeight}`} className="w-full h-auto select-none">
            {/* Grid Lines */}
            <line
              x1={padLeft}
              y1={toPxY(0.0)}
              x2={padLeft + plotW}
              y2={toPxY(0.0)}
              stroke="#3f3f46"
              strokeDasharray="2,2"
              strokeWidth="0.8"
            />
            <line
              x1={padLeft}
              y1={toPxY(1.0)}
              x2={padLeft + plotW}
              y2={toPxY(1.0)}
              stroke="#52525b"
              strokeDasharray="3,3"
              strokeWidth="1"
            />
            <line
              x1={toPxX(0.5)}
              y1={padTop}
              x2={toPxX(0.5)}
              y2={toPxY(0.0)}
              stroke="#27272a"
              strokeDasharray="2,2"
              strokeWidth="0.8"
            />

            {/* Axis Labels */}
            <text x={padLeft - 4} y={toPxY(0.0) + 3} fill="#71717a" fontSize="8" textAnchor="end">
              0.0
            </text>
            <text x={padLeft - 4} y={toPxY(1.0) + 3} fill="#a1a1aa" fontSize="8" textAnchor="end">
              1.0
            </text>
            <text x={padLeft} y={svgHeight - 6} fill="#71717a" fontSize="8" textAnchor="middle">
              0%
            </text>
            <text x={padLeft + plotW} y={svgHeight - 6} fill="#71717a" fontSize="8" textAnchor="middle">
              100%
            </text>

            {/* Bezier Tangent Handle Lines */}
            <line
              x1={toPxX(0)}
              y1={toPxY(0)}
              x2={toPxX(activeBezier.x1)}
              y2={toPxY(activeBezier.y1)}
              stroke="#06b6d4"
              strokeWidth="1.2"
              strokeDasharray="2,1"
              opacity="0.8"
            />
            <circle
              cx={toPxX(activeBezier.x1)}
              cy={toPxY(activeBezier.y1)}
              r="3.5"
              fill="#06b6d4"
            />

            <line
              x1={toPxX(1)}
              y1={toPxY(1)}
              x2={toPxX(activeBezier.x2)}
              y2={toPxY(activeBezier.y2)}
              stroke="#f59e0b"
              strokeWidth="1.2"
              strokeDasharray="2,1"
              opacity="0.8"
            />
            <circle
              cx={toPxX(activeBezier.x2)}
              cy={toPxY(activeBezier.y2)}
              r="3.5"
              fill="#f59e0b"
            />

            {/* Evaluated Easing Curve Path */}
            <path d={curvePath} fill="none" stroke="#818cf8" strokeWidth="2.2" strokeLinecap="round" />

            {/* Real-time Scrub Indicator Dot on Curve */}
            <circle
              cx={scrubDotX}
              cy={scrubDotY}
              r="5"
              fill="#ec4899"
              stroke="#ffffff"
              strokeWidth="1.5"
            />
          </svg>

          {/* Realtime readout overlay */}
          <div className="flex items-center justify-between text-[10px] text-zinc-400 px-1 pt-1 font-mono">
            <span>Progress: {(scrubProgress * 100).toFixed(0)}%</span>
            <span className="text-pink-400 font-semibold">Value: {currentCurveVal.toFixed(3)}</span>
          </div>
        </div>

        {/* Bezier Preset Chips */}
        <div className="grid grid-cols-2 gap-1.5 pt-1">
          {BEZIER_PRESETS.map((preset) => {
            const isSelected = preset.id === currentEasing;
            return (
              <button
                key={preset.id}
                type="button"
                onClick={() => updateMotionConfig(motionPresetId, { easing_curve: preset.id })}
                className={`flex flex-col items-start rounded border px-2 py-1.5 text-left transition-colors ${
                  isSelected
                    ? "border-indigo-500 bg-indigo-950/60 text-indigo-200"
                    : "border-zinc-800 bg-zinc-900/40 text-zinc-400 hover:border-zinc-700 hover:bg-zinc-800/60"
                }`}
              >
                <span className="font-medium text-zinc-200 text-[10px]">{preset.name}</span>
                <span className="text-[9px] text-zinc-500 truncate w-full">{preset.desc}</span>
              </button>
            );
          })}
        </div>
      </div>

      {/* After Effects Motion Engine Controls (Range Selectors, Blur, Expressions) */}
      <div className="flex flex-col gap-2.5 rounded-lg border border-zinc-800 bg-zinc-950/70 p-2.5">
        <label className="text-[11px] font-medium uppercase tracking-wider text-indigo-400">
          After Effects Engine Controls
        </label>

        {/* Range Selector Shape */}
        <div>
          <label className={labelClass}>Text Range Selector Shape</label>
          <div className="grid grid-cols-4 gap-1">
            {["ramp_up", "smooth", "triangle", "square"].map((shape) => {
              const active = (motionProps.range_shape || "ramp_up") === shape;
              return (
                <button
                  key={shape}
                  type="button"
                  onClick={() => updateMotionConfig(motionPresetId, { range_shape: shape })}
                  className={`py-1 rounded border text-[10px] uppercase font-mono transition-colors ${
                    active
                      ? "border-indigo-500 bg-indigo-950/60 text-indigo-300"
                      : "border-zinc-800 bg-zinc-900 text-zinc-400 hover:border-zinc-700"
                  }`}
                >
                  {shape.replace("_", " ")}
                </button>
              );
            })}
          </div>
        </div>

        {/* 180° Motion Blur Shutter Angle */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <label className="text-[11px] font-medium uppercase tracking-wider text-zinc-400">
              180&deg; Shutter Motion Blur
            </label>
            <span className="font-mono text-[10px] text-indigo-400">
              {motionProps.shutter_angle !== undefined ? motionProps.shutter_angle : 180}&deg;
            </span>
          </div>
          <input
            type="range"
            min="0"
            max="360"
            step="15"
            value={motionProps.shutter_angle !== undefined ? motionProps.shutter_angle : 180}
            onChange={(e) => updateMotionConfig(motionPresetId, {
              shutter_angle: parseInt(e.target.value, 10),
              enable_motion_blur: parseInt(e.target.value, 10) > 0,
            })}
            className="w-full accent-indigo-500 cursor-pointer h-1.5 bg-zinc-800 rounded-lg"
          />
        </div>

        {/* Expressions Toggles */}
        <div className="flex gap-2 pt-1">
          <button
            type="button"
            onClick={() => updateMotionConfig(motionPresetId, {
              enable_wiggle: !(motionProps.enable_wiggle ?? true),
            })}
            className={`flex-1 py-1.5 px-2 rounded border text-[10px] font-medium transition-colors flex items-center justify-center gap-1.5 ${
              (motionProps.enable_wiggle ?? true)
                ? "border-cyan-500 bg-cyan-950/40 text-cyan-300"
                : "border-zinc-800 bg-zinc-900 text-zinc-500"
            }`}
          >
            <span>&sim;</span>
            <span>Camera Wiggle</span>
          </button>

          <button
            type="button"
            onClick={() => updateMotionConfig(motionPresetId, {
              enable_inertia_bounce: !(motionProps.enable_inertia_bounce ?? true),
            })}
            className={`flex-1 py-1.5 px-2 rounded border text-[10px] font-medium transition-colors flex items-center justify-center gap-1.5 ${
              (motionProps.enable_inertia_bounce ?? true)
                ? "border-amber-500 bg-amber-950/40 text-amber-300"
                : "border-zinc-800 bg-zinc-900 text-zinc-500"
            }`}
          >
            <span>&uarr;&darr;</span>
            <span>Inertia Bounce</span>
          </button>
        </div>

        {/* Kinetic Typography Mechanics */}
        <div className="pt-1">
          <label className={labelClass}>Typography Reveal Mechanics</label>
          <div className="grid grid-cols-2 gap-1.5">
            {[
              { id: "liquid_light_wipe", name: "Liquid Light Wipe", desc: "Hermite beam sweep & bloom" },
              { id: "masked_baseline", name: "Baseline Track Matte", desc: "AE baseline slice & horizon" },
              { id: "buttery_kinetic", name: "Living Ribbon Flow", desc: "Fixed anchor & organic wave" },
              { id: "smooth_words", name: "Smooth Word Stagger", desc: "Natural word cascade" },
            ].map((mech) => {
              const active = (motionProps.typography_mechanic || "liquid_light_wipe") === mech.id;
              return (
                <button
                  key={mech.id}
                  type="button"
                  onClick={() => updateMotionConfig(motionPresetId, { typography_mechanic: mech.id })}
                  className={`flex flex-col items-start rounded border px-2 py-1.5 text-left transition-colors ${
                    active
                      ? "border-cyan-500 bg-cyan-950/60 text-cyan-200"
                      : "border-zinc-800 bg-zinc-900 text-zinc-400 hover:border-zinc-700 hover:bg-zinc-800/60"
                  }`}
                >
                  <span className="font-medium text-[10px] text-zinc-200">{mech.name}</span>
                  <span className="text-[9px] text-zinc-500 truncate w-full">{mech.desc}</span>
                </button>
              );
            })}
          </div>
        </div>
      </div>

      {/* Preset Selector */}
      <div>
        <label className={labelClass}>Style Preset</label>
        <div className="grid grid-cols-2 gap-1.5">
          {presets.map((preset) => {
            const isSelected = preset.id === motionPresetId;
            return (
              <button
                key={preset.id}
                type="button"
                onClick={() => updateMotionConfig(preset.id, preset.default_props)}
                className={`flex flex-col items-start rounded border p-2 text-left transition-colors ${
                  isSelected
                    ? "border-indigo-500 bg-indigo-950/40 text-indigo-200"
                    : "border-zinc-800 bg-zinc-900/60 text-zinc-400 hover:border-zinc-700 hover:bg-zinc-800"
                }`}
              >
                <span className="font-medium text-zinc-200 text-[11px] truncate w-full">
                  {preset.name}
                </span>
                <span className="text-[10px] text-zinc-400 truncate w-full mt-0.5">
                  {preset.category}
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {/* Configurable Parameters */}
      <div className="flex flex-col gap-3 pt-2 border-t border-zinc-800">
        <div>
          <label className={labelClass}>Master Headline</label>
          <input
            type="text"
            value={motionProps.headline || motionProps.title || ""}
            onChange={(e) => updateMotionConfig(motionPresetId, { headline: e.target.value, title: e.target.value })}
            placeholder="Headline or Title"
            className={inputClass}
          />
        </div>

        <div>
          <label className={labelClass}>Subtitle / Manifesto</label>
          <input
            type="text"
            value={motionProps.subtitle || motionProps.warning_text || ""}
            onChange={(e) => updateMotionConfig(motionPresetId, { subtitle: e.target.value, warning_text: e.target.value })}
            placeholder="Subtitle or Description"
            className={inputClass}
          />
        </div>

        <div>
          <label className={labelClass}>Category Badge / Status</label>
          <input
            type="text"
            value={motionProps.badge_text || motionProps.status || ""}
            onChange={(e) => updateMotionConfig(motionPresetId, { badge_text: e.target.value, status: e.target.value })}
            placeholder="Badge text (e.g. GLOBAL KEYNOTE)"
            className={inputClass}
          />
        </div>

        {/* Aspect Ratio Selector */}
        <div>
          <label className={labelClass}>Aspect Ratio</label>
          <div className="flex gap-2">
            <button
              type="button"
              onClick={() => updateMotionConfig(motionPresetId, { aspect_ratio: "16:9" })}
              className={`flex-1 py-1 px-2 rounded border text-[11px] font-medium transition-colors ${
                (motionProps.aspect_ratio || "16:9") === "16:9"
                  ? "border-indigo-500 bg-indigo-950/50 text-indigo-300"
                  : "border-zinc-800 bg-zinc-900 text-zinc-400 hover:border-zinc-700"
              }`}
            >
              16:9 Widescreen
            </button>
            <button
              type="button"
              onClick={() => updateMotionConfig(motionPresetId, { aspect_ratio: "9:16" })}
              className={`flex-1 py-1 px-2 rounded border text-[11px] font-medium transition-colors ${
                motionProps.aspect_ratio === "9:16"
                  ? "border-indigo-500 bg-indigo-950/50 text-indigo-300"
                  : "border-zinc-800 bg-zinc-900 text-zinc-400 hover:border-zinc-700"
              }`}
            >
              9:16 Vertical
            </button>
          </div>
        </div>
      </div>
    </div>
  );
};
