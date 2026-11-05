import React from "react";
import { Zap, Plus, FolderInput, BookOpen, Sliders, Wrench, Film } from "lucide-react";

interface QuickActionsPanelProps {
  onNewProject: () => void;
  onImportPages?: () => void;
  onOpenLibrary?: () => void;
  onOpenAnimeReview?: () => void;
  onOpenOriginalStories?: () => void;
  onOpenChronoFlow?: () => void;
  onModelSettings?: () => void;
  onEngineSettings?: () => void;
}

export const QuickActionsPanel: React.FC<QuickActionsPanelProps> = ({
  onNewProject,
  onImportPages,
  onOpenLibrary,
  onOpenAnimeReview,
  onOpenOriginalStories,
  onOpenChronoFlow,
  onModelSettings,
  onEngineSettings,
}) => {
  return (
    <div className="space-y-2.5 select-none">
      {/* Title */}
      <div className="flex items-center gap-2">
        <Zap className="w-4 h-4 text-indigo-400" />
        <h3 className="text-xs font-bold uppercase tracking-wider text-zinc-200">
          Quick Actions
        </h3>
      </div>

      {/* Primary New Project Action */}
      <button
        onClick={onNewProject}
        className="w-full bg-[#4338ca] hover:bg-[#4f46e5] text-white font-semibold text-xs py-2 px-3 rounded-lg flex items-center justify-center gap-2 shadow-md shadow-indigo-600/30 transition-all"
      >
        <Plus className="w-4 h-4 text-white" />
        <span>New Project</span>
      </button>

      {onOpenAnimeReview && (
        <button
          onClick={onOpenAnimeReview}
          className="w-full bg-[#151928] hover:bg-[#1f253d] text-zinc-200 border border-[#242c44] text-xs font-semibold py-2 px-3 rounded-lg flex items-center justify-center gap-2 transition-colors"
          title="Queue anime episodes for automatic review videos"
        >
          <Zap className="w-4 h-4 text-indigo-400" />
          <span>Anime Review</span>
        </button>
      )}

      {onOpenOriginalStories && (
        <button
          onClick={onOpenOriginalStories}
          className="w-full bg-[#151928] hover:bg-[#1f253d] text-zinc-200 border border-[#242c44] text-xs font-semibold py-2 px-3 rounded-lg flex items-center justify-center gap-2 transition-colors"
          title="Write, draw, narrate and queue original story episodes"
        >
          <BookOpen className="w-4 h-4 text-indigo-400" />
          <span>Original Stories</span>
        </button>
      )}

      {onOpenChronoFlow && (
        <button
          onClick={onOpenChronoFlow}
          className="w-full bg-[#151928] hover:bg-[#1f253d] text-zinc-200 border border-[#242c44] text-xs font-semibold py-2 px-3 rounded-lg flex items-center justify-center gap-2 transition-colors group"
          title="ChronoFlow Studio: MiniMax H3 Video Chaining, Inpaint & AI Storyboard"
        >
          <Film className="w-4 h-4 text-purple-400 group-hover:text-purple-300" />
          <span>ChronoFlow Studio</span>
        </button>
      )}

      {/* 2x2 Grid of Actions */}
      <div className="grid grid-cols-2 gap-2">
        <button
          onClick={onImportPages || onNewProject}
          className="bg-[#151928] hover:bg-[#1f253d] text-zinc-200 border border-[#242c44] text-[11px] font-medium py-2 px-2 rounded-lg flex items-center justify-center gap-1.5 transition-colors"
          title="Import pages from local folder or archive"
        >
          <FolderInput className="w-3.5 h-3.5 text-zinc-400" />
          <span className="truncate">Import Pages</span>
        </button>

        <button
          onClick={onOpenLibrary}
          className="bg-[#151928] hover:bg-[#1f253d] text-zinc-200 border border-[#242c44] text-[11px] font-medium py-2 px-2 rounded-lg flex items-center justify-center gap-1.5 transition-colors"
          title="Open Audio & Asset Library"
        >
          <BookOpen className="w-3.5 h-3.5 text-zinc-400" />
          <span className="truncate">Open Library</span>
        </button>

        <button
          onClick={onModelSettings}
          className="bg-[#151928] hover:bg-[#1f253d] text-zinc-200 border border-[#242c44] text-[11px] font-medium py-2 px-2 rounded-lg flex items-center justify-center gap-1.5 transition-colors"
          title="Configure local model settings"
        >
          <Sliders className="w-3.5 h-3.5 text-zinc-400" />
          <span className="truncate">Model Settings</span>
        </button>

        <button
          onClick={onEngineSettings}
          className="bg-[#151928] hover:bg-[#1f253d] text-zinc-200 border border-[#242c44] text-[11px] font-medium py-2 px-2 rounded-lg flex items-center justify-center gap-1.5 transition-colors"
          title="Inspect engine telemetry and logs"
        >
          <Wrench className="w-3.5 h-3.5 text-zinc-400" />
          <span className="truncate">Engine Settings</span>
        </button>
      </div>
    </div>
  );
};
