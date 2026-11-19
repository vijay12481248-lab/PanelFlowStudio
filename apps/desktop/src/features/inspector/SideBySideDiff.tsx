import React, { useState } from "react";

interface SideBySideDiffProps {
  originalUrl: string;
  repairedUrl: string;
  originalScore?: number;
  repairedScore?: number;
  isVideo?: boolean;
  className?: string;
}

export const SideBySideDiff: React.FC<SideBySideDiffProps> = ({
  originalUrl,
  repairedUrl,
  originalScore,
  repairedScore,
  isVideo = false,
  className = "",
}) => {
  const [sliderPos, setSliderPos] = useState<number>(50); // percentage (0-100)
  const [mode, setMode] = useState<"slider" | "split">("slider");

  const scoreDiff =
    originalScore !== undefined && repairedScore !== undefined
      ? Math.round((repairedScore - originalScore) * 10) / 10
      : null;

  return (
    <div className={`flex flex-col gap-3 rounded-2xl border border-zinc-800 bg-zinc-950/70 p-4 shadow-xl ${className}`}>
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <span className="text-xs font-semibold uppercase tracking-wider text-zinc-400">
            A/B Visual Revalidation Diff
          </span>
          {scoreDiff !== null && (
            <span
              className={`rounded-full px-2.5 py-0.5 text-xs font-bold ${
                scoreDiff >= 0
                  ? "bg-emerald-500/20 text-emerald-400 border border-emerald-500/30"
                  : "bg-rose-500/20 text-rose-400 border border-rose-500/30"
              }`}
            >
              {originalScore?.toFixed(1)} &rarr; {repairedScore?.toFixed(1)} ({scoreDiff >= 0 ? `+${scoreDiff}` : scoreDiff})
            </span>
          )}
        </div>

        <div className="flex items-center gap-1 rounded-lg bg-zinc-900 p-1 border border-zinc-800">
          <button
            type="button"
            onClick={() => setMode("slider")}
            className={`rounded px-2 py-1 text-xs font-medium transition-colors ${
              mode === "slider" ? "bg-zinc-800 text-white shadow-sm" : "text-zinc-400 hover:text-zinc-200"
            }`}
          >
            Swipe Slider
          </button>
          <button
            type="button"
            onClick={() => setMode("split")}
            className={`rounded px-2 py-1 text-xs font-medium transition-colors ${
              mode === "split" ? "bg-zinc-800 text-white shadow-sm" : "text-zinc-400 hover:text-zinc-200"
            }`}
          >
            Side-by-Side
          </button>
        </div>
      </div>

      {mode === "split" ? (
        <div className="grid grid-cols-2 gap-4">
          <div className="flex flex-col gap-1.5">
            <span className="text-xs font-medium text-rose-400 flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-rose-500" />
              Original (Defective)
            </span>
            <div className="relative overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/50">
              {isVideo ? (
                <video src={originalUrl} controls className="max-h-[460px] w-full object-contain" />
              ) : (
                <img src={originalUrl} alt="Original" className="max-h-[460px] w-full object-contain" />
              )}
            </div>
          </div>

          <div className="flex flex-col gap-1.5">
            <span className="text-xs font-medium text-emerald-400 flex items-center gap-1.5">
              <span className="h-2 w-2 rounded-full bg-emerald-500" />
              Repaired & Revalidated
            </span>
            <div className="relative overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/50">
              {isVideo ? (
                <video src={repairedUrl} controls className="max-h-[460px] w-full object-contain" />
              ) : (
                <img src={repairedUrl} alt="Repaired" className="max-h-[460px] w-full object-contain" />
              )}
            </div>
          </div>
        </div>
      ) : (
        <div className="relative select-none overflow-hidden rounded-xl border border-zinc-800 bg-zinc-900/50">
          {/* Base Layer: Repaired */}
          <div className="relative w-full">
            {isVideo ? (
              <video src={repairedUrl} controls className="max-h-[500px] w-full object-contain" />
            ) : (
              <img src={repairedUrl} alt="Repaired" className="max-h-[500px] w-full object-contain" />
            )}
            <span className="absolute bottom-3 right-3 rounded-md bg-emerald-950/80 px-2 py-0.5 text-[11px] font-semibold text-emerald-300 border border-emerald-500/30 backdrop-blur-sm">
              Repaired
            </span>
          </div>

          {/* Top Layer: Original (clipped by slider) */}
          <div
            className="absolute inset-y-0 left-0 overflow-hidden"
            style={{ width: `${sliderPos}%` }}
          >
            <div className="relative h-full w-full">
              {isVideo ? (
                <video src={originalUrl} className="max-h-[500px] w-full object-contain" />
              ) : (
                <img src={originalUrl} alt="Original" className="max-h-[500px] w-full object-contain" />
              )}
              <span className="absolute bottom-3 left-3 rounded-md bg-rose-950/80 px-2 py-0.5 text-[11px] font-semibold text-rose-300 border border-rose-500/30 backdrop-blur-sm">
                Original
              </span>
            </div>
          </div>

          {/* Slider Divider Bar */}
          <div
            className="absolute inset-y-0 w-0.5 bg-white shadow-2xl pointer-events-none"
            style={{ left: `${sliderPos}%` }}
          >
            <div className="absolute top-1/2 -left-3.5 -translate-y-1/2 flex h-7 w-7 items-center justify-center rounded-full bg-white text-zinc-900 shadow-md">
              <span className="text-xs font-black select-none">&harr;</span>
            </div>
          </div>

          {/* Invisible interactive input range covering canvas */}
          <input
            type="range"
            min="0"
            max="100"
            value={sliderPos}
            onChange={(e) => setSliderPos(Number(e.target.value))}
            className="absolute inset-0 h-full w-full opacity-0 cursor-ew-resize"
          />
        </div>
      )}
    </div>
  );
};
