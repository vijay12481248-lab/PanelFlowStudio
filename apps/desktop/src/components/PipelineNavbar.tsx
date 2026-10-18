import React from "react";
import type { PipelineStage } from "@panelflow/shared-types";
import { Badge, Icons } from "@panelflow/ui";

interface PipelineNavbarProps {
  currentStage: PipelineStage;
  onNavigate: (stage: string) => void;
  staleStages?: string[];
  currentScreen?: string;
}

interface StageEntry {
  id: string;
  label: string;
  screenKey: string;
  minStage: PipelineStage[];
}

const PIPELINE_STAGES: StageEntry[] = [
  { id: "source", label: "Source", screenKey: "acquisition", minStage: ["NEW", "RIGHTS_APPROVED"] },
  { id: "panels", label: "Panels", screenKey: "panels", minStage: ["ACQUIRED", "NORMALIZED", "PANELS_DETECTED"] },
  { id: "ocr", label: "OCR", screenKey: "ocr", minStage: ["OCR_COMPLETE", "OCR_APPROVED"] },
  { id: "story", label: "Story", screenKey: "story", minStage: ["STORY_ANALYZED", "STORY_APPROVED"] },
  { id: "script", label: "Script", screenKey: "script", minStage: ["SCRIPT_GENERATED", "SCRIPT_APPROVED"] },
  { id: "audio", label: "Audio", screenKey: "audio", minStage: ["VOICE_GENERATED", "AUDIO_APPROVED"] },
  { id: "motion", label: "Motion", screenKey: "motion", minStage: ["SHOT_PLAN_GENERATED", "MOTION_APPROVED"] },
  { id: "render", label: "Render", screenKey: "render", minStage: ["RENDERED", "QA_APPROVED", "EXPORTED"] },
];

const STAGE_ORDER: PipelineStage[] = [
  "NEW",
  "RIGHTS_APPROVED",
  "ACQUIRED",
  "NORMALIZED",
  "PANELS_DETECTED",
  "OCR_COMPLETE",
  "OCR_APPROVED",
  "STORY_ANALYZED",
  "STORY_APPROVED",
  "SCRIPT_GENERATED",
  "SCRIPT_APPROVED",
  "VOICE_GENERATED",
  "AUDIO_APPROVED",
  "SHOT_PLAN_GENERATED",
  "MOTION_APPROVED",
  "RENDERED",
  "QA_APPROVED",
  "EXPORTED",
];

function stageIndex(stage: PipelineStage): number {
  const idx = STAGE_ORDER.indexOf(stage);
  return idx >= 0 ? idx : 0;
}

type StageStatus = "COMPLETE" | "ACTIVE" | "STALE" | "UPCOMING" | "NOT_STARTED";

function getStageStatus(entry: StageEntry, currentStage: PipelineStage, staleStages?: string[]): StageStatus {
  if (staleStages && staleStages.includes(entry.id)) {
    return "STALE";
  }
  const currentIdx = stageIndex(currentStage);
  const entryMinIdx = Math.min(...entry.minStage.map((s) => stageIndex(s)));
  const entryMaxIdx = Math.max(...entry.minStage.map((s) => stageIndex(s)));

  if (currentIdx > entryMaxIdx) return "COMPLETE";
  if (currentIdx >= entryMinIdx && currentIdx <= entryMaxIdx) return "ACTIVE";
  if (currentIdx === entryMinIdx - 1) return "UPCOMING";
  return "NOT_STARTED";
}

const statusStyles: Record<StageStatus, string> = {
  COMPLETE: "bg-emerald-600/20 text-emerald-400 border-emerald-600/40",
  ACTIVE: "bg-indigo-600/20 text-indigo-400 border-indigo-500/50 ring-1 ring-indigo-500/30",
  STALE: "bg-amber-600/20 text-amber-400 border-amber-500/50 ring-1 ring-amber-500/30",
  UPCOMING: "bg-zinc-800/50 text-zinc-400 border-zinc-700 hover:border-zinc-600",
  NOT_STARTED: "bg-zinc-900/30 text-zinc-600 border-zinc-800 cursor-not-allowed opacity-50",
};

const statusDotStyles: Record<StageStatus, string> = {
  COMPLETE: "bg-emerald-400",
  ACTIVE: "bg-indigo-400 animate-pulse",
  STALE: "bg-amber-400 animate-pulse",
  UPCOMING: "bg-zinc-500",
  NOT_STARTED: "bg-zinc-700",
};

export const PipelineNavbar: React.FC<PipelineNavbarProps> = ({ currentStage, onNavigate, staleStages, currentScreen }) => {
  return (
    <div className="flex items-center gap-1.5 overflow-x-auto py-2 px-1 scrollbar-thin scrollbar-thumb-zinc-700">
      {PIPELINE_STAGES.map((entry, idx) => {
        const status = getStageStatus(entry, currentStage, staleStages);
        const isCurrentView = currentScreen === entry.screenKey;
        const isClickable = status !== "NOT_STARTED" || isCurrentView;

        return (
          <React.Fragment key={entry.id}>
            {idx > 0 && (
              <div
                className={`w-4 h-px flex-shrink-0 ${
                  status === "COMPLETE" ? "bg-emerald-600/50" : status === "STALE" ? "bg-amber-600/50" : "bg-zinc-800"
                }`}
              />
            )}
            <button
              onClick={() => isClickable && onNavigate(entry.screenKey)}
              disabled={!isClickable}
              className={`flex items-center gap-1.5 px-3 py-1.5 rounded-lg border text-[11px] font-semibold
                transition-all whitespace-nowrap flex-shrink-0 ${statusStyles[status]} ${
                isCurrentView ? "ring-2 ring-indigo-400 border-indigo-400 bg-indigo-500/20 text-white shadow-md shadow-indigo-500/20" : ""
              }`}
            >
              <span className={`w-1.5 h-1.5 rounded-full ${isCurrentView ? "bg-indigo-300 ring-2 ring-indigo-400/50" : statusDotStyles[status]}`} />
              {entry.label}{status === "STALE" ? " (STALE)" : ""}
            </button>
          </React.Fragment>
        );
      })}

      <div className="w-px h-5 bg-zinc-800 mx-1 flex-shrink-0" />

      <button
        onClick={() => onNavigate("story_editor")}
        className="ml-auto flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-indigo-500/50 bg-indigo-600/25 hover:bg-indigo-600/40 text-indigo-200 text-[11px] font-semibold transition-all whitespace-nowrap shadow-sm shadow-indigo-600/20 flex-shrink-0"
        title="Open unified video-first story editor"
      >
        <Icons.Film className="w-3.5 h-3.5 text-indigo-400" />
        Story Editor
      </button>
    </div>
  );
};
