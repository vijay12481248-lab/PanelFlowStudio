import React, { useState } from "react";
import { Icons, Badge } from "@panelflow/ui";
import type {
  EmotionalDeliveryConfig,
  NarrationEmotion,
  PausePreset,
} from "./NarrationStudio.types";

interface EmotionDeliveryControlsProps {
  delivery: EmotionalDeliveryConfig;
  onChangeDelivery: (updates: Partial<EmotionalDeliveryConfig>) => void;
  className?: string;
}

const EMOTION_OPTIONS: Array<{
  name: NarrationEmotion;
  icon: string;
  color: string;
  activeBg: string;
  description: string;
}> = [
  { name: "Neutral", icon: "⚖️", color: "text-zinc-300", activeBg: "bg-zinc-700/80 border-zinc-500", description: "Even, balanced, matter-of-fact" },
  { name: "Happy", icon: "✨", color: "text-amber-300", activeBg: "bg-amber-950/80 border-amber-500", description: "Warm, light, optimistic tone" },
  { name: "Sad", icon: "🌧️", color: "text-blue-300", activeBg: "bg-blue-950/80 border-blue-500", description: "Melancholic, subdued, heavy" },
  { name: "Angry", icon: "🔥", color: "text-rose-400", activeBg: "bg-rose-950/80 border-rose-500", description: "Sharp, aggressive, commanding" },
  { name: "Fearful", icon: "⚡", color: "text-yellow-400", activeBg: "bg-yellow-950/80 border-yellow-500", description: "Trembling, anxious, panicked" },
  { name: "Suspenseful", icon: "👁️", color: "text-purple-300", activeBg: "bg-purple-950/80 border-purple-500", description: "Tense, hushed, building anticipation" },
  { name: "Excited", icon: "💥", color: "text-orange-300", activeBg: "bg-orange-950/80 border-orange-500", description: "High energy, breathless, fast" },
  { name: "Whispering", icon: "🤫", color: "text-teal-300", activeBg: "bg-teal-950/80 border-teal-500", description: "Intimate, breathy, secretive" },
  { name: "Serious", icon: "🛡️", color: "text-indigo-300", activeBg: "bg-indigo-950/80 border-indigo-500", description: "Grounded, grave, authoritative" },
  { name: "Mysterious", icon: "🔮", color: "text-violet-400", activeBg: "bg-violet-950/80 border-violet-500", description: "Ethereal, veiled, enigmatic" },
  { name: "Determined", icon: "⚔️", color: "text-emerald-300", activeBg: "bg-emerald-950/80 border-emerald-500", description: "Resolute, steely, unwavering" },
];

export const EmotionDeliveryControls: React.FC<EmotionDeliveryControlsProps> = ({
  delivery,
  onChangeDelivery,
  className = "",
}) => {
  const [showAdvanced, setShowAdvanced] = useState<boolean>(false);

  // Pause duration map
  const pausePresets: Record<PausePreset, number> = {
    none: 0,
    short: 250,
    medium: 500,
    dramatic: 900,
    custom: delivery.pause?.duration_ms || 400,
  };

  const handleSelectEmotion = (emotion: NarrationEmotion) => {
    onChangeDelivery({ emotion });
  };

  const handleIntensityChange = (intensity: number) => {
    onChangeDelivery({ intensity });
  };

  const handleSpeedChange = (speech_speed: number) => {
    onChangeDelivery({ speech_speed });
  };

  const handlePausePreset = (preset: PausePreset) => {
    const duration_ms = pausePresets[preset];
    onChangeDelivery({
      pause: {
        preset,
        duration_ms,
        placement: delivery.pause?.placement || "after_first_sentence",
        instruction: delivery.pause?.instruction || "",
      },
    });
  };

  const handlePausePlacement = (placement: "before" | "after_first_sentence" | "after" | "custom") => {
    onChangeDelivery({
      pause: {
        ...delivery.pause,
        placement,
      },
    });
  };

  const handlePauseInstruction = (instruction: string) => {
    onChangeDelivery({
      pause: {
        ...delivery.pause,
        instruction,
      },
    });
  };

  return (
    <div className={`space-y-4 select-none ${className}`}>
      {/* Emotion Selection Title & Active Badge */}
      <div className="flex items-center justify-between">
        <span className="text-xs font-bold uppercase tracking-wider text-zinc-300">
          Emotional Delivery
        </span>
        <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-indigo-950 text-indigo-400 border border-indigo-800">
          {delivery.emotion} ({Math.round(delivery.intensity * 100)}%)
        </span>
      </div>

      {/* Emotion Grid (11 options) */}
      <div className="grid grid-cols-3 gap-1.5">
        {EMOTION_OPTIONS.map((opt) => {
          const isSelected = delivery.emotion === opt.name;
          return (
            <button
              key={opt.name}
              type="button"
              onClick={() => handleSelectEmotion(opt.name)}
              title={opt.description}
              className={`p-1.5 rounded-lg border text-left flex items-center gap-1.5 transition-all ${
                isSelected
                  ? `${opt.activeBg} ring-1 ring-white/20 shadow-md scale-[1.02]`
                  : "bg-zinc-900/60 border-zinc-800 hover:border-zinc-700 hover:bg-zinc-900"
              }`}
            >
              <span className="text-sm shrink-0">{opt.icon}</span>
              <span className={`text-[11px] font-semibold truncate ${isSelected ? "text-white" : opt.color}`}>
                {opt.name}
              </span>
            </button>
          );
        })}
      </div>

      {/* Delivery Intensity Slider */}
      <div className="space-y-1.5 bg-zinc-900/40 p-2.5 rounded-lg border border-zinc-800">
        <div className="flex items-center justify-between text-xs">
          <span className="text-zinc-400 font-medium">Delivery Intensity</span>
          <span className="font-mono font-bold text-zinc-200">
            {Math.round(delivery.intensity * 100)}%
          </span>
        </div>
        <input
          type="range"
          min="0.1"
          max="1.0"
          step="0.05"
          value={delivery.intensity}
          onChange={(e) => handleIntensityChange(parseFloat(e.target.value))}
          className="w-full accent-indigo-500 cursor-pointer h-1.5 bg-zinc-800 rounded-lg appearance-none"
        />
        <div className="flex justify-between text-[9px] font-medium text-zinc-500 px-0.5">
          <span>Subtle</span>
          <span>Moderate</span>
          <span>Dramatic</span>
          <span>Extreme</span>
        </div>
      </div>

      {/* Speech Speed / Pacing Slider */}
      <div className="space-y-1.5 bg-zinc-900/40 p-2.5 rounded-lg border border-zinc-800">
        <div className="flex items-center justify-between text-xs">
          <span className="text-zinc-400 font-medium">Speech Speed</span>
          <span className="font-mono font-bold text-indigo-400">
            {delivery.speech_speed.toFixed(2)}x
          </span>
        </div>
        <input
          type="range"
          min="0.75"
          max="1.5"
          step="0.05"
          value={delivery.speech_speed}
          onChange={(e) => handleSpeedChange(parseFloat(e.target.value))}
          className="w-full accent-indigo-500 cursor-pointer h-1.5 bg-zinc-800 rounded-lg appearance-none"
        />
        <div className="flex justify-between text-[9px] font-medium text-zinc-500 px-0.5">
          <button
            type="button"
            onClick={() => handleSpeedChange(0.85)}
            className="hover:text-zinc-300 underline"
          >
            Deliberate (0.85x)
          </button>
          <button
            type="button"
            onClick={() => handleSpeedChange(1.0)}
            className="hover:text-zinc-300 underline"
          >
            Natural (1.0x)
          </button>
          <button
            type="button"
            onClick={() => handleSpeedChange(1.25)}
            className="hover:text-zinc-300 underline"
          >
            Urgent (1.25x)
          </button>
        </div>
      </div>

      {/* Progressive Disclosure Toggle */}
      <button
        type="button"
        onClick={() => setShowAdvanced((v) => !v)}
        className="w-full py-1.5 text-xs text-zinc-400 hover:text-zinc-200 flex items-center justify-center gap-1.5 rounded bg-zinc-900/80 border border-zinc-800 hover:bg-zinc-800 transition-colors"
      >
        <span>{showAdvanced ? "Hide Advanced Directing" : "Show Advanced Directing (Pauses & Subtext)"}</span>
        <span className="text-[10px]">{showAdvanced ? "▲" : "▼"}</span>
      </button>

      {/* Advanced Performance & Directing Controls */}
      {showAdvanced && (
        <div className="space-y-3 pt-2 border-t border-zinc-800 text-xs">
          {/* Pause Presets */}
          <div className="space-y-1.5">
            <span className="text-zinc-400 font-medium block text-[11px]">
              Intentional Dramatic Pause
            </span>
            <div className="grid grid-cols-4 gap-1">
              {(["none", "short", "medium", "dramatic"] as PausePreset[]).map((p) => {
                const isSelected = delivery.pause?.preset === p;
                return (
                  <button
                    key={p}
                    type="button"
                    onClick={() => handlePausePreset(p)}
                    className={`py-1 rounded text-[10px] font-semibold transition-colors capitalize ${
                      isSelected
                        ? "bg-indigo-600 text-white shadow-sm"
                        : "bg-zinc-900 text-zinc-400 border border-zinc-800 hover:bg-zinc-800"
                    }`}
                  >
                    {p === "none" ? "None" : `${p} (${pausePresets[p]}ms)`}
                  </button>
                );
              })}
            </div>
          </div>

          {/* Pause Placement */}
          {delivery.pause?.preset !== "none" && (
            <div className="space-y-1.5">
              <span className="text-zinc-400 font-medium block text-[11px]">
                Pause Placement
              </span>
              <select
                value={delivery.pause?.placement || "after_first_sentence"}
                onChange={(e) => handlePausePlacement(e.target.value as any)}
                className="w-full bg-zinc-900 border border-zinc-800 text-xs text-zinc-200 rounded p-1.5 focus:outline-none focus:border-indigo-500"
              >
                <option value="after_first_sentence">Short pause after the first sentence</option>
                <option value="before">Pause before beginning speaking</option>
                <option value="after">Pause at the end of segment</option>
                <option value="custom">Custom placement</option>
              </select>
            </div>
          )}

          {/* Structured Performance Instructions */}
          <div className="space-y-1.5">
            <span className="text-zinc-400 font-medium block text-[11px]">
              Performance & Subtext Instructions
            </span>
            <textarea
              value={delivery.performance_notes}
              onChange={(e) => onChangeDelivery({ performance_notes: e.target.value })}
              rows={2}
              placeholder="e.g., Quiet, tense, gradually increasing suspense..."
              className="w-full p-2 rounded bg-zinc-900 border border-zinc-800 text-xs text-zinc-200 placeholder-zinc-500 focus:outline-none focus:border-indigo-500 leading-relaxed"
            />
          </div>

          {/* Engineering / TTS Verification Notice */}
          <div className="p-2 rounded bg-zinc-950 border border-zinc-800 text-[10px] text-zinc-500 leading-normal">
            ℹ️ <span className="font-semibold text-zinc-400">Notice:</span> Emotional parameters are structured for future TTS integration. Engine mapping will verify specific model support during Chapter 6 binding.
          </div>
        </div>
      )}
    </div>
  );
};
