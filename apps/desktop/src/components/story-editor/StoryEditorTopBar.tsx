import React from "react";
import { Icons, Button } from "@panelflow/ui";
import type { Project, StoryEditorState } from "@panelflow/shared-types";

interface StoryEditorTopBarProps {
  project: Project;
  state: StoryEditorState;
  onUpdateState: (updater: (prev: StoryEditorState) => StoryEditorState) => void;
  canUndo: boolean;
  canRedo: boolean;
  onUndo: () => void;
  onRedo: () => void;
  onBackToDashboard: () => void;
  onExportClick: () => void;
  saveStatus: "saved" | "saving" | "unsaved";
  onOpenNarrationStudio?: () => void;
  onOpenAudioLibrary?: () => void;
}

export const StoryEditorTopBar: React.FC<StoryEditorTopBarProps> = ({
  project,
  state,
  onUpdateState,
  canUndo,
  canRedo,
  onUndo,
  onRedo,
  onBackToDashboard,
  onExportClick,
  saveStatus,
  onOpenNarrationStudio,
  onOpenAudioLibrary,
}) => {
  return (
    <header className="h-13 border-b border-zinc-800 bg-zinc-950 px-4 flex items-center justify-between sticky top-0 z-40 select-none">
      {/* Left: Branding & Breadcrumbs */}
      <div className="flex items-center gap-3">
        {/* Brand Icon & Name */}
        <div
          onClick={onBackToDashboard}
          className="flex items-center gap-2 cursor-pointer group"
          title="Return to Projects Dashboard"
        >
          <div className="w-7 h-7 rounded-lg bg-indigo-600 flex items-center justify-center text-white font-black text-sm shadow-md shadow-indigo-600/30 group-hover:bg-indigo-500 transition-colors">
            P
          </div>
          <div>
            <div className="font-extrabold text-sm text-white tracking-tight leading-none flex items-center gap-1.5">
              <span>PanelFlow</span>
            </div>
            <span className="text-[10px] text-zinc-400 font-medium leading-none block mt-0.5">
              Turn Manga Pages into Animated Stories
            </span>
          </div>
        </div>

        <div className="h-5 w-px bg-zinc-800 mx-2" />

        {/* Breadcrumb Path */}
        <div className="flex items-center gap-1.5 text-xs text-zinc-400 font-medium">
          <button
            type="button"
            onClick={onBackToDashboard}
            className="hover:text-zinc-200 transition-colors"
          >
            My Projects
          </button>
          <span className="text-zinc-600">›</span>
          <span className="text-zinc-200 truncate max-w-[160px]" title={project.title}>
            {project.title}
          </span>
          <span className="text-zinc-600">›</span>
          <span className="text-indigo-400 font-semibold">Chapter 01</span>
        </div>
      </div>

      {/* Right Controls: Saved status, Undo/Redo, Aspect Ratio, Preview, Export, Window Controls */}
      <div className="flex items-center gap-3">
        {/* Save Status */}
        <div className="flex items-center gap-1 text-xs font-medium mr-1">
          {saveStatus === "saving" ? (
            <span className="text-amber-400 flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-amber-400 animate-pulse" />
              Saving...
            </span>
          ) : saveStatus === "unsaved" ? (
            <span className="text-zinc-400 flex items-center gap-1.5" title="Changes will auto-save shortly">
              <span className="w-2 h-2 rounded-full bg-amber-500/80" />
              Unsaved
            </span>
          ) : (
            <span className="text-emerald-400 flex items-center gap-1.5">
              <Icons.Check className="w-3.5 h-3.5 text-emerald-400" />
              Saved
            </span>
          )}
        </div>

        {/* Undo / Redo */}
        <div className="flex items-center gap-1 text-zinc-400">
          <button
            type="button"
            onClick={onUndo}
            disabled={!canUndo}
            className="p-1 rounded hover:text-white disabled:opacity-30 transition-colors"
            title="Undo (Ctrl+Z)"
          >
            <Icons.Undo className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={onRedo}
            disabled={!canRedo}
            className="p-1 rounded hover:text-white disabled:opacity-30 transition-colors"
            title="Redo (Ctrl+Y)"
          >
            <Icons.Redo className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="h-4 w-px bg-zinc-800" />

        {/* Mode Toggle: Simple vs Advanced (Chapter 3) */}
        <div className="flex items-center bg-zinc-900 border border-zinc-800 rounded p-0.5 text-xs">
          <button
            type="button"
            onClick={() => onUpdateState((s) => ({ ...s, mode: "simple" }))}
            className={`px-2 py-0.5 rounded text-[11px] font-semibold transition-colors ${
              state.mode === "simple"
                ? "bg-indigo-600 text-white shadow-sm"
                : "text-zinc-400 hover:text-zinc-200"
            }`}
            title="Simple Storyboard Mode: Quick drag-and-drop story scenes"
          >
            Simple
          </button>
          <button
            type="button"
            onClick={() => onUpdateState((s) => ({ ...s, mode: "advanced" }))}
            className={`px-2 py-0.5 rounded text-[11px] font-semibold transition-colors ${
              state.mode === "advanced"
                ? "bg-indigo-600 text-white shadow-sm"
                : "text-zinc-400 hover:text-zinc-200"
            }`}
            title="Advanced Multitrack Mode: Independent layers, trim handles, and precise timing"
          >
            Advanced
          </button>
        </div>

        <div className="h-4 w-px bg-zinc-800" />

        {/* Aspect Ratio Selector */}
        <div className="flex items-center bg-zinc-900 border border-zinc-800 rounded-lg px-2.5 py-1 text-xs text-zinc-200 gap-1.5 shadow-inner">
          <svg className="w-3.5 h-3.5 text-zinc-400" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
            {state.aspect_ratio === "9:16" ? (
              <rect x="7" y="2" width="10" height="20" rx="2" />
            ) : state.aspect_ratio === "1:1" ? (
              <rect x="4" y="4" width="16" height="16" rx="2" />
            ) : (
              <rect x="2" y="5" width="20" height="14" rx="2" />
            )}
          </svg>
          <select
            value={state.aspect_ratio}
            onChange={(e) =>
              onUpdateState((s) => ({ ...s, aspect_ratio: e.target.value as any }))
            }
            className="bg-transparent font-medium focus:outline-none cursor-pointer text-[11px]"
          >
            <option value="16:9" className="bg-zinc-900 text-zinc-100">16:9 Landscape</option>
            <option value="9:16" className="bg-zinc-900 text-zinc-100">9:16 Vertical</option>
            <option value="1:1" className="bg-zinc-900 text-zinc-100">1:1 Square</option>
          </select>
        </div>

        {/* Narration Studio Workspace Launcher */}
        {onOpenNarrationStudio && (
          <button
            type="button"
            onClick={onOpenNarrationStudio}
            className="text-xs h-8 px-3 rounded-lg border border-emerald-600/60 bg-emerald-950/40 text-emerald-300 hover:bg-emerald-900/60 hover:text-emerald-100 flex items-center gap-1.5 font-semibold transition-all shadow-sm shadow-emerald-950 active:scale-95"
            title="Open AI Narration & Storytelling Studio"
          >
            <span className="w-2 h-2 rounded-full bg-emerald-400 animate-pulse" />
            <Icons.Mic className="w-3.5 h-3.5 text-emerald-400" />
            <span>Narration Studio</span>
          </button>
        )}

        {/* Audio Library Workspace Launcher */}
        {onOpenAudioLibrary && (
          <button
            type="button"
            onClick={onOpenAudioLibrary}
            className="text-xs h-8 px-3 rounded-lg border border-amber-600/60 bg-amber-950/40 text-amber-300 hover:bg-amber-900/60 hover:text-amber-100 flex items-center gap-1.5 font-semibold transition-all shadow-sm shadow-amber-950 active:scale-95"
            title="Open Music & Sound Effects Library"
          >
            <Icons.Music className="w-3.5 h-3.5 text-amber-400" />
            <span>Audio Library</span>
          </button>
        )}

        {/* Preview Button */}
        <button
          type="button"
          onClick={() =>
            onUpdateState((s) => ({ ...s, is_playing: !s.is_playing }))
          }
          className={`text-xs h-8 px-3 rounded-lg border font-semibold flex items-center gap-1.5 transition-all active:scale-95 ${
            state.is_playing
              ? "bg-amber-600 text-white border-amber-500 shadow-md shadow-amber-950 ring-1 ring-amber-400/50"
              : "bg-zinc-900 border-zinc-700 hover:border-zinc-500 text-zinc-200"
          }`}
        >
          {state.is_playing ? (
            <>
              <Icons.Pause className="w-3.5 h-3.5 fill-current" />
              <span>Playing</span>
            </>
          ) : (
            <>
              <Icons.Play className="w-3.5 h-3.5 text-indigo-400" />
              <span>Preview</span>
            </>
          )}
        </button>

        {/* Primary Purple Export Button */}
        <button
          type="button"
          onClick={onExportClick}
          className="bg-gradient-to-r from-indigo-600 to-violet-600 hover:from-indigo-500 hover:to-violet-500 text-white font-bold h-8 px-4 rounded-lg shadow-md shadow-indigo-600/30 flex items-center gap-1.5 transition-all active:scale-95"
        >
          <Icons.Film className="w-3.5 h-3.5" />
          <span>Export</span>
        </button>

        {/* Clean Window Navigation Controls */}
        <div className="flex items-center gap-1 text-zinc-500 ml-1 border-l border-zinc-800 pl-2">
          <button
            type="button"
            onClick={onBackToDashboard}
            className="hover:text-zinc-200 p-1.5 rounded-lg hover:bg-zinc-800/80 transition-colors"
            title="Return to Projects Dashboard"
          >
            <Icons.ArrowLeft className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    </header>
  );
};
