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
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/80 backdrop-blur-sm p-4 overflow-y-auto">
      <div className="relative w-full max-w-5xl bg-navy border border-edge rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[92vh]">
        {/* Modal Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-edge bg-glass">
          <div className="flex items-center gap-3">
            <div className="flex items-center justify-center w-8 h-8 rounded-lg bg-accent-soft text-info border border-accent/20">
              <Layers className="w-4 h-4" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="text-base font-semibold text-fg">
                  Candidate Inspector — #{beat.order} ({beat.panel_id})
                </h2>
                <span className="text-xs px-2 py-0.5 rounded-full bg-glass-hi text-fg-dim font-mono">
                  {beat.shot || "standard shot"}
                </span>
                {beat.status && (
                  <span
                    className={`text-xs px-2 py-0.5 rounded-full font-medium ${
                      beat.status === "accept"
                        ? "bg-ok/10 text-ok border border-ok/40"
                        : beat.status === "accept_low"
                        ? "bg-warn/10 text-warn border border-warn/40"
                        : beat.status === "needs_review"
                        ? "bg-bad/10 text-bad border border-bad/40"
                        : beat.status === "repaired"
                        ? "bg-accent-soft text-info border border-accent/40"
                        : "bg-glass-hi text-fg-dim border border-edge"
                    }`}
                  >
                    {beat.status.replace("_", " ").toUpperCase()}
                  </span>
                )}
              </div>
              <p className="text-xs text-fg-dim line-clamp-1 max-w-2xl mt-0.5">
                {beat.caption || beat.action || "No narrative text available"}
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={onClose}
              className="p-1.5 text-fg-dim hover:text-fg rounded-lg hover:bg-glass-hi transition-colors"
              title="Close modal"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
        </div>

        {/* Modal Body: Split view (Image canvas + candidate details & strip) */}
        <div className="flex-1 overflow-hidden grid grid-cols-1 lg:grid-cols-12 min-h-0">
          {/* Main Inspection Canvas */}
          <div className="lg:col-span-8 bg-navy/80 p-6 flex flex-col items-center justify-center relative min-h-[350px] lg:min-h-[500px]">
            <div className="relative max-w-full max-h-[60vh] rounded-lg overflow-hidden border border-edge shadow-xl bg-navy group">
              <img
                src={activeImageUrl}
                alt={`Candidate ${candidateN}`}
                className="max-h-[58vh] w-auto object-contain block"
              />

              {/* Defect Bounding Box Overlay if available */}
              {showBoundingBoxes && bbox && bbox.length === 4 && (
                <div
                  className="absolute border-2 border-bad bg-bad/20 pointer-events-none transition-all duration-200"
                  style={{
                    left: `${bbox[0] * 100}%`,
                    top: `${bbox[1] * 100}%`,
                    width: `${(bbox[2] - bbox[0]) * 100}%`,
                    height: `${(bbox[3] - bbox[1]) * 100}%`,
                  }}
                >
                  <span className="absolute -top-5 left-0 bg-bad text-[10px] text-white px-1.5 py-0.5 rounded font-mono font-bold shadow">
                    DEFECT REGION
                  </span>
                </div>
              )}

              {/* Status / Iteration watermark */}
              <div className="absolute bottom-2 left-2 bg-ink/70 backdrop-blur-md px-2.5 py-1 rounded-md text-[11px] text-fg-dim font-mono border border-white/10">
                Iteration #{candidateN} ({activeIteration.kind || "generation"})
              </div>
            </div>

            {/* Canvas Toolbar Controls */}
            <div className="mt-4 flex items-center gap-4 text-xs text-fg-dim">
              {bbox && bbox.length === 4 && (
                <label className="flex items-center gap-1.5 cursor-pointer hover:text-fg">
                  <input
                    type="checkbox"
                    checked={showBoundingBoxes}
                    onChange={(e) => setShowBoundingBoxes(e.target.checked)}
                    className="rounded border-edge bg-navy text-accent focus:ring-0"
                  />
                  <span>Show Defect Bounding Box</span>
                </label>
              )}
              <span>•</span>
              <span>Audio duration: {beat.audio_duration ? `${beat.audio_duration}s` : "Pending"}</span>
            </div>
          </div>

          {/* Right Sidebar: Candidate selector & metadata */}
          <div className="lg:col-span-4 border-t lg:border-t-0 lg:border-l border-edge bg-glass/30 p-5 flex flex-col justify-between overflow-y-auto">
            <div className="space-y-5">
              {/* Iteration Selector Strip */}
              <div>
                <h3 className="text-xs font-semibold uppercase tracking-wider text-fg-dim mb-2.5 flex items-center justify-between">
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
                            ? "border-accent bg-accent-soft ring-2 ring-accent/30"
                            : "border-edge bg-glass/60 hover:border-edge"
                        }`}
                      >
                        <div className="aspect-video w-full rounded overflow-hidden bg-ink mb-1">
                          <img
                            src={iterThumbUrl}
                            alt={`Cand ${iter.n}`}
                            className="w-full h-full object-cover"
                          />
                        </div>
                        <div className="flex items-center justify-between px-1">
                          <span className="text-[11px] font-mono text-fg-dim font-medium">
                            c00{iter.n}
                          </span>
                          {isCanonical && (
                            <span className="w-1.5 h-1.5 rounded-full bg-ok" title="Canonical" />
                          )}
                        </div>
                      </button>
                    );
                  })}
                </div>
              </div>

              {/* Candidate Metadata Card */}
              <div className="rounded-xl border border-edge bg-glass p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-fg-dim">VQA Consistency Score</span>
                  <span className="text-xs font-bold font-mono text-fg">
                    {activeIteration.score != null
                      ? `${Math.round(activeIteration.score * 100)}%`
                      : beat.score != null
                      ? `${Math.round(beat.score * 100)}%`
                      : "Unscored"}
                  </span>
                </div>

                <div className="flex items-center justify-between">
                  <span className="text-xs text-fg-dim">Creation Kind</span>
                  <span className="text-xs font-mono text-fg-dim capitalize">
                    {activeIteration.kind || "Initial generation"}
                  </span>
                </div>

                {activeIteration.seed !== undefined && (
                  <div className="flex items-center justify-between">
                    <span className="text-xs text-fg-dim">PRNG Seed</span>
                    <span className="text-xs font-mono text-fg-dim">
                      {activeIteration.seed}
                    </span>
                  </div>
                )}

                {activeIteration.prompt && (
                  <div className="pt-2 border-t border-edge">
                    <span className="text-[11px] font-semibold text-fg-dim block mb-1">
                      Render Prompt
                    </span>
                    <p className="text-[11px] text-fg-dim line-clamp-3 bg-navy/60 p-2 rounded border border-edge">
                      {activeIteration.prompt}
                    </p>
                  </div>
                )}
              </div>
            </div>

            {/* Action Buttons */}
            <div className="pt-4 mt-6 border-t border-edge space-y-2">
              <button
                type="button"
                onClick={handleInpaintClick}
                className="w-full flex items-center justify-center gap-2 px-4 py-2.5 rounded-xl bg-accent hover:bg-accent/80 text-white font-medium text-xs shadow-lg shadow-accent/20 transition-colors"
              >
                <Wand2 className="w-4 h-4" />
                <span>Inpaint on this Candidate</span>
              </button>

              {onSelectCandidate && !isCurrentCanonical && (
                <button
                  type="button"
                  onClick={handleSetCanonical}
                  disabled={isSubmittingCanonical}
                  className="w-full flex items-center justify-center gap-2 px-4 py-2 rounded-xl bg-glass-hi hover:bg-glass text-fg font-medium text-xs border border-edge transition-colors disabled:opacity-50"
                >
                  <Check className="w-4 h-4 text-ok" />
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
