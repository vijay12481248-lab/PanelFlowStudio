import React from "react";
import { Zap, Plus, FolderInput, BookOpen, Sliders, Wrench } from "lucide-react";

interface QuickActionsPanelProps {
  onNewProject: () => void;
  onImportPages?: () => void;
  onOpenLibrary?: () => void;
  onModelSettings?: () => void;
  onEngineSettings?: () => void;
}

export const QuickActionsPanel: React.FC<QuickActionsPanelProps> = ({
  onNewProject,
  onImportPages,
  onOpenLibrary,
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
