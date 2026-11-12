import React, { useState, useEffect } from "react";
import { api } from "@panelflow/api-client";
import type { StoryboardBeatCard, CandidateIteration } from "@panelflow/api-client";
import type { ImageEditorTarget } from "./ImageEditorModal";
import {
  X,
  Sparkles,
  Layers,
  CheckCircle2,
  AlertTriangle,
  ZoomIn,
  Wand2,
  ChevronRight,
  Info,
  Check,
  Maximize2,
} from "lucide-react";

export interface CandidateInspectorModalProps {
  isOpen: boolean;
  onClose: () => void;
  storySlug: string;
  episodeSlug?: string;
  beat: StoryboardBeatCard | null;
  onSelectCandidate?: (candidateN: number) => Promise<void> | void;
  onOpenInpaint: (target: ImageEditorTarget) => void;
}

export const CandidateInspectorModal: React.FC<CandidateInspectorModalProps> = ({
  isOpen,
  onClose,
  storySlug,
  episodeSlug,
  beat,
  onSelectCandidate,
  onOpenInpaint,
}) => {
  const [selectedIterationIndex, setSelectedIterationIndex] = useState<number>(0);
  const [showBoundingBoxes, setShowBoundingBoxes] = useState<boolean>(true);
  const [isSubmittingCanonical, setIsSubmittingCanonical] = useState<boolean>(false);

  useEffect(() => {
    if (beat && beat.iterations && beat.iterations.length > 0) {
      const activeIdx = beat.iterations.findIndex((it) => it.n === beat.selected_candidate);
      setSelectedIterationIndex(activeIdx >= 0 ? activeIdx : 0);
    } else {
      setSelectedIterationIndex(0);
    }
  }, [beat]);

  if (!isOpen || !beat) return null;

  const iterations: CandidateIteration[] =
    beat.iterations && beat.iterations.length > 0
      ? beat.iterations
      : [
          {
            n: beat.selected_candidate || 1,
            file: `panels/${beat.panel_id}.png`,
            kind: "generate",
            score: beat.score,
          },
        ];

  const activeIteration = iterations[selectedIterationIndex] || iterations[0];
  const candidateN = activeIteration.n;
  const activeImageUrl = api.getOriginalPanelImageUrl(
    storySlug,
    beat.panel_id,
    episodeSlug,
    candidateN
  );

  const isCurrentCanonical = (activeIteration.n === beat.selected_candidate);

  const handleSetCanonical = async () => {
    if (!onSelectCandidate) return;
    try {
      setIsSubmittingCanonical(true);
      await onSelectCandidate(candidateN);
    } finally {
      setIsSubmittingCanonical(false);
    }
  };

  const handleInpaintClick = () => {
    onOpenInpaint({
      mode: "story",
      storySlug,
      episodeSlug,
      panelId: beat.panel_id,
      imageSrc: activeImageUrl,
    });
    onClose();
  };

  // Check for defect bbox in active iteration or beat
  const bbox = activeIteration.bbox;

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="relative w-full max-w-5xl bg-zinc-950 border border-zinc-800 rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[92vh]">
        {/* Modal Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-zinc-800/80 bg-zinc-900/50">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-indigo-500/10 text-indigo-400 border border-indigo-500/20">
              <Layers className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-semibold text-zinc-100">
                  Candidate Inspector — #{beat.order} ({beat.panel_id})
                </h2>
                <span className="text-xs px-2 py-0.5 rounded-full bg-zinc-800 text-zinc-400 font-mono">
                  {beat.shot || "standard shot"}
                </span>
                {beat.status && (
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                      beat.status === "accept"
                        ? "bg-emerald-950 text-emerald-400 border border-emerald-700/60"
                        : beat.status === "accept_low"
                        ? "bg-amber-950 text-amber-400 border border-amber-700/60"
                        : beat.status === "needs_review"
                        ? "bg-rose-950 text-rose-400 border border-rose-700/60"
                        : beat.status === "repaired"
                        ? "bg-purple-950 text-purple-400 border border-purple-700/60"
                        : "bg-zinc-800 text-zinc-300 border border-zinc-700"
                    }`}
                  >
                    {beat.status.replace("_", " ").toUpperCase()}
                  </span>
                )}
              </div>
              <p className="text-xs text-zinc-400 line-clamp-1 max-w-2xl mt-0.5">
                {beat.caption || beat.action || "No narrative text available"}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="p-1.5 text-zinc-400 hover:text-zinc-100 rounded-lg hover:bg-zinc-800 transition-colors"
              title="Close modal"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Modal Body: Split view (Image canvas + candidate details & strip) */}
        <div className="flex-1 overflow-hidden grid grid-cols-1 lg:grid-cols-12 min-h-0">
          {/* Main Inspection Canvas */}
          <div className="lg:col-span-8 bg-zinc-950/80 p-6 flex flex-col items-center justify-center relative min-h-[350px] lg:min-h-[500px]">
            <div className="relative max-w-full max-h-[60vh] rounded-lg overflow-hidden border border-zinc-800 shadow-xl bg-zinc-900 group">
              <img
                src={activeImageUrl}
                alt={`Candidate ${candidateN}`}
                className="max-h-[58vh] w-auto object-contain block"
              />

              {/* Defect Bounding Box Overlay if available */}
              {showBoundingBoxes && bbox && bbox.length === 4 && (
                <div
                  className="absolute border-2 border-rose-500 bg-rose-500/20 pointer-events-none transition-all duration-200"
                  style={{
                    left: `${bbox[0] * 100}%`,
                    top: `${bbox[1] * 100}%`,
                    width: `${(bbox[2] - bbox[0]) * 100}%`,
                    height: `${(bbox[3] - bbox[1]) * 100}%`,
                  }}
                >
                  <span className="absolute -top-5 left-0 bg-rose-600 text-[10px] text-white px-1.5 py-0.5 rounded font-mono font-bold shadow">
                    DEFECT REGION
                  </span>
                </div>
              )}

              {/* Status / Iteration watermark */}
              <div className="absolute bottom-2 left-2 bg-black/70 backdrop-blur-md px-2.5 py-1 rounded-md text-[11px] text-zinc-300 font-mono border border-white/10">
                Iteration #{candidateN} ({activeIteration.kind || "generation"})
              </div>
            </div>

            {/* Canvas Toolbar Controls */}
            <div className="mt-4 flex items-center gap-4 text-xs text-zinc-400">
              {bbox && bbox.length === 4 && (
                <label className="flex items-center gap-1.5 cursor-pointer hover:text-zinc-200">
                  <input
                    type="checkbox"
                    checked={showBoundingBoxes}
                    onChange={(e) => setShowBoundingBoxes(e.target.checked)}
                    className="rounded border-zinc-700 bg-zinc-900 text-indigo-600 focus:ring-0"
                  />
                  <span>Show Defect Bounding Box</span>
                </label>
              )}
              <span>•</span>
              <span>Audio duration: {beat.audio_duration ? `${beat.audio_duration}s` : "Pending"}</span>
            </div>
          </div>

          {/* Right Sidebar: Candidate selector & metadata */}
          <div className="lg:col-span-4 border-t lg:border-t-0 lg:border-l border-zinc-800/80 bg-zinc-900/30 p-5 flex flex-col justify-between overflow-y-auto">
            <div className="space-y-5">
              {/* Iteration Selector Strip */}
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wider text-zinc-400 mb-2.5 flex items-center justify-between">
                  <span>Candidate Iterations ({iterations.length})</span>
                </h3>
                <div className="grid grid-cols-3 gap-2">
                  {iterations.map((iter, idx) => {
                    const isSelected = idx === selectedIterationIndex;
                    const isCanonical = iter.n === beat.selected_candidate;
                    const iterThumbUrl = api.getOriginalPanelImageUrl(
                      storySlug,
                      beat.panel_id,
                      episodeSlug,
                      iter.n
                    );
                    return (
                      <button
                        key={iter.n}
                        onClick={() => setSelectedIterationIndex(idx)}
                        className={`relative rounded-lg overflow-hidden border p-1 text-left transition-all ${
                          isSelected
                            ? "border-indigo-500 bg-indigo-500/10 ring-2 ring-indigo-500/30"
                            : "border-zinc-800 bg-zinc-900/60 hover:border-zinc-700"
                        }`}
                      >
                        <div className="aspect-video w-full rounded overflow-hidden bg-black mb-1">
                          <img
                            src={iterThumbUrl}
                            alt={`Cand ${iter.n}`}
                            className="w-full h-full object-cover"
                          />
                        </div>
                        <div className="flex items-center justify-between px-1">
                          <span className="text-[11px] font-mono text-zinc-300 font-medium">
                            c00{iter.n}
                          </span>
                          {isCanonical && (
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" title="Canonical" />
                          )}
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Candidate Metadata Card */}
              <div className="rounded-xl border border-zinc-800/80 bg-zinc-900/50 p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-zinc-400">VQA Consistency Score</span>
                  <span className="text-xs font-bold font-mono text-zinc-100">
                    {activeIteration.score != null
                      ? `${Math.round(activeIteration.score * 100)}%`
                      : beat.score != null
                      ? `${Math.round(beat.score * 100)}%`
                      : "Unscored"}
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-xs text-zinc-400">Creation Kind</span>
                  <span className="text-xs font-mono text-zinc-300 capitalize">
                    {activeIteration.kind || "Initial generation"}
                  </span>
                </div>

                {activeIteration.seed !== undefined && (
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-zinc-400">PRNG Seed</span>
                    <span className="text-xs font-mono text-zinc-300">
                      {activeIteration.seed}
                    </span>
                  </div>
                )}

                {activeIteration.prompt && (
                  <div className="pt-2 border-t border-zinc-800">
                    <span className="text-[11px] font-semibold text-zinc-400 block mb-1">
                      Render Prompt
                    </span>
                    <p className="text-[11px] text-zinc-300 line-clamp-3 bg-zinc-950/60 p-2 rounded border border-zinc-800/60">
                      {activeIteration.prompt}
                    </p>
                  </div>
                )}
              </div>
            </div>

            {/* Action Buttons */}
            <div className="pt-4 mt-6 border-t border-zinc-800/80 space-y-2">
              <button
                type="button"
                onClick={handleInpaintClick}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-indigo-600 hover:bg-indigo-500 text-white font-medium text-xs shadow-lg shadow-indigo-600/20 transition-colors"
              >
                <Wand2 className="w-4 h-4" />
                <span>Inpaint on this Candidate</span>
              </button>

              {onSelectCandidate && !isCurrentCanonical && (
                <button
                  type="button"
                  onClick={handleSetCanonical}
                  disabled={isSubmittingCanonical}
                  className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-xl bg-zinc-800 hover:bg-zinc-700 text-zinc-200 font-medium text-xs border border-zinc-700 transition-colors disabled:opacity-50"
                >
                  <Check className="w-4 h-4 text-emerald-400" />
                  <span>Set as Canonical Active Panel</span>
                </button>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};
