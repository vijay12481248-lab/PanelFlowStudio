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
        <div className="flex items-center bg-zinc-900 border border-zinc-800 rounded px-2 py-1 text-xs text-zinc-200">
          <select
            value={state.aspect_ratio}
            onChange={(e) =>
              onUpdateState((s) => ({ ...s, aspect_ratio: e.target.value as any }))
            }
            className="bg-transparent font-medium focus:outline-none cursor-pointer"
          >
            <option value="16:9">16:9 (Landscape)</option>
            <option value="9:16">9:16 (Vertical)</option>
            <option value="1:1">1:1 (Square)</option>
          </select>
        </div>

        {/* Narration Studio Workspace Launcher */}
        {onOpenNarrationStudio && (
          <Button
            variant="secondary"
            size="sm"
            onClick={onOpenNarrationStudio}
            className="text-xs h-8 px-3 border border-emerald-700/70 bg-emerald-950/40 text-emerald-300 hover:bg-emerald-900/60 hover:text-emerald-100 flex items-center gap-1.5 font-semibold"
            title="Open AI Narration & Storytelling Studio"
          >
            <Icons.Mic className="w-3.5 h-3.5 text-emerald-400" />
            Narration Studio
          </Button>
        )}

        {/* Audio Library Workspace Launcher */}
        {onOpenAudioLibrary && (
          <Button
            variant="secondary"
            size="sm"
            onClick={onOpenAudioLibrary}
            className="text-xs h-8 px-3 border border-amber-700/70 bg-amber-950/40 text-amber-300 hover:bg-amber-900/60 hover:text-amber-100 flex items-center gap-1.5 font-semibold"
            title="Open Music & Sound Effects Library"
          >
            <Icons.Music className="w-3.5 h-3.5 text-amber-400" />
            Audio Library
          </Button>
        )}

        {/* Preview Button */}
        <Button
          variant="secondary"
          size="sm"
          onClick={() =>
            onUpdateState((s) => ({ ...s, is_playing: !s.is_playing }))
          }
          className="text-xs h-8 px-3 border border-zinc-700 hover:border-zinc-500"
        >
          <Icons.Play className="w-3.5 h-3.5 mr-1 text-indigo-400" />
          Preview
        </Button>

        {/* Primary Purple Export Button */}
        <Button
          variant="primary"
          size="sm"
          onClick={onExportClick}
          className="bg-indigo-600 hover:bg-indigo-500 text-white font-bold h-8 px-4 rounded-lg shadow-md shadow-indigo-600/30"
        >
          <Icons.Film className="w-3.5 h-3.5 mr-1.5" />
          Export
        </Button>

        {/* Window controls mimic */}
        <div className="flex items-center gap-1.5 text-zinc-500 ml-2">
          <button className="hover:text-zinc-300 p-1" title="Minimize Window">_</button>
          <button className="hover:text-zinc-300 p-1" title="Maximize Window">□</button>
          <button onClick={onBackToDashboard} className="hover:text-rose-400 p-1" title="Close">✕</button>
        </div>
      </div>
    </header>
  );
};
