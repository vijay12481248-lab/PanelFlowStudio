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
  icon: React.FC<{ className?: string }>;
  color: string;
  activeBg: string;
  description: string;
}> = [
  { name: "Neutral", icon: Icons.Sliders, color: "text-fg-dim", activeBg: "bg-glass-hi/80 border-fg-faint", description: "Even, balanced, matter-of-fact" },
  { name: "Happy", icon: Icons.Sparkles, color: "text-warn", activeBg: "bg-warn/80 border-warn", description: "Warm, light, optimistic tone" },
  { name: "Sad", icon: Icons.ChevronDown, color: "text-info", activeBg: "bg-accent/80 border-accent", description: "Melancholic, subdued, heavy" },
  { name: "Angry", icon: Icons.AlertTriangle, color: "text-bad", activeBg: "bg-bad/80 border-bad", description: "Sharp, aggressive, commanding" },
  { name: "Fearful", icon: Icons.Zap, color: "text-warn", activeBg: "bg-warn/80 border-warn", description: "Trembling, anxious, panicked" },
  { name: "Suspenseful", icon: Icons.Eye, color: "text-info", activeBg: "bg-accent/80 border-accent", description: "Tense, hushed, building anticipation" },
  { name: "Excited", icon: Icons.Sparkles, color: "text-warn", activeBg: "bg-warn/80 border-warn", description: "High energy, breathless, fast" },
  { name: "Whispering", icon: Icons.Mic, color: "text-info", activeBg: "bg-info/80 border-info", description: "Intimate, breathy, secretive" },
  { name: "Serious", icon: Icons.ShieldCheck, color: "text-info", activeBg: "bg-accent/80 border-accent", description: "Grounded, grave, authoritative" },
  { name: "Mysterious", icon: Icons.Globe, color: "text-info", activeBg: "bg-accent/80 border-accent", description: "Ethereal, veiled, enigmatic" },
  { name: "Determined", icon: Icons.CheckCircle, color: "text-ok", activeBg: "bg-ok/80 border-ok", description: "Resolute, steely, unwavering" },
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
        <span className="text-xs font-bold uppercase tracking-wider text-fg-dim">
          Emotional Delivery
        </span>
        <span className="text-xs font-semibold px-2 py-0.5 rounded-full bg-accent/20 text-info border border-accent/40">
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
                  : "bg-navy/60 border-edge hover:border-edge hover:bg-navy"
              }`}
            >
              <opt.icon className={`w-3.5 h-3.5 shrink-0 ${isSelected ? "text-white" : opt.color}`} />
              <span className={`text-[11px] font-semibold truncate ${isSelected ? "text-white" : opt.color}`}>
                {opt.name}
              </span>
            </button>
          );
        })}
      </div>

      {/* Delivery Intensity Slider */}
      <div className="space-y-1.5 bg-navy/40 p-2.5 rounded-lg border border-edge">
        <div className="flex items-center justify-between text-xs">
          <span className="text-fg-dim font-medium">Delivery Intensity</span>
          <span className="font-mono font-bold text-fg">
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
          className="w-full accent-accent cursor-pointer h-1.5 bg-flat rounded-lg appearance-none"
        />
        <div className="flex justify-between text-[9px] font-medium text-fg-faint px-0.5">
          <span>Subtle</span>
          <span>Moderate</span>
          <span>Dramatic</span>
          <span>Extreme</span>
        </div>
      </div>

      {/* Speech Speed / Pacing Slider */}
      <div className="space-y-1.5 bg-navy/40 p-2.5 rounded-lg border border-edge">
        <div className="flex items-center justify-between text-xs">
          <span className="text-fg-dim font-medium">Speech Speed</span>
          <span className="font-mono font-bold text-info">
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
          className="w-full accent-accent cursor-pointer h-1.5 bg-flat rounded-lg appearance-none"
        />
        <div className="flex justify-between text-[9px] font-medium text-fg-faint px-0.5">
          <button
            type="button"
            onClick={() => handleSpeedChange(0.85)}
            className="hover:text-fg-dim underline"
          >
            Deliberate (0.85x)
          </button>
          <button
            type="button"
            onClick={() => handleSpeedChange(1.0)}
            className="hover:text-fg-dim underline"
          >
            Natural (1.0x)
          </button>
          <button
            type="button"
            onClick={() => handleSpeedChange(1.25)}
            className="hover:text-fg-dim underline"
          >
            Urgent (1.25x)
          </button>
        </div>
      </div>

      {/* Progressive Disclosure Toggle */}
      <button
        type="button"
        onClick={() => setShowAdvanced((v) => !v)}
        className="w-full py-1.5 text-xs text-fg-dim hover:text-fg flex items-center justify-center gap-1.5 rounded bg-navy/80 border border-edge hover:bg-flat transition-colors"
      >
        <span>{showAdvanced ? "Hide Advanced Directing" : "Show Advanced Directing (Pauses & Subtext)"}</span>
        <span className="text-[10px]">{showAdvanced ? "▲" : "▼"}</span>
      </button>

      {/* Advanced Performance & Directing Controls */}
      {showAdvanced && (
        <div className="space-y-3 pt-2 border-t border-edge text-xs">
          {/* Pause Presets */}
          <div className="space-y-1.5">
            <span className="text-fg-dim font-medium block text-[11px]">
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
                        ? "bg-accent text-white shadow-sm"
                        : "bg-navy text-fg-dim border border-edge hover:bg-flat"
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
              <span className="text-fg-dim font-medium block text-[11px]">
                Pause Placement
              </span>
              <select
                value={delivery.pause?.placement || "after_first_sentence"}
                onChange={(e) => handlePausePlacement(e.target.value as any)}
                className="w-full bg-navy border border-edge text-xs text-fg rounded p-1.5 focus:outline-none focus:border-accent"
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
            <span className="text-fg-dim font-medium block text-[11px]">
              Performance & Subtext Instructions
            </span>
            <textarea
              value={delivery.performance_notes}
              onChange={(e) => onChangeDelivery({ performance_notes: e.target.value })}
              rows={2}
              placeholder="e.g., Quiet, tense, gradually increasing suspense..."
              className="w-full p-2 rounded bg-navy border border-edge text-xs text-fg placeholder-fg-faint focus:outline-none focus:border-accent leading-relaxed"
            />
          </div>

          {/* Engineering / TTS Verification Notice */}
          <div className="p-2 rounded bg-ink border border-edge text-[10px] text-fg-faint leading-normal">
            ℹ️ <span className="font-semibold text-fg-dim">Notice:</span> Emotional parameters are structured for future TTS integration. Engine mapping will verify specific model support during Chapter 6 binding.
          </div>
        </div>
      )}
    </div>
  );
};
