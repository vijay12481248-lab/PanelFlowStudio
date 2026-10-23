import React from "react";
import { Icons } from "@panelflow/ui";
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
    <header className="min-h-[56px] min-w-0 shrink-0 border-b border-[#262a3b] bg-[#0b0d15] px-3 py-2 flex flex-wrap gap-x-3 gap-y-2 items-center justify-between sticky top-0 z-40 select-none [&_button]:focus-visible:outline-none [&_button]:focus-visible:ring-2 [&_button]:focus-visible:ring-violet-400 [&_svg]:shrink-0">
      {/* Left: Branding & Breadcrumbs */}
      <div className="flex min-w-0 items-center gap-3">
        {/* Brand Icon & Name */}
        <button
          type="button"
          aria-label="Return to Projects Dashboard"
          onClick={onBackToDashboard}
          className="flex shrink-0 items-center gap-3 rounded-md text-left cursor-pointer group"
          title="Return to Projects Dashboard"
        >
          <span aria-hidden="true" className="w-8 h-8 rounded-md bg-gradient-to-br from-violet-500 to-indigo-700 flex items-center justify-center text-white font-black text-xl shadow-[0_0_22px_#713fff55] group-hover:from-violet-400 transition-colors">
            P
          </span>
          <span>
            <span className="font-extrabold text-lg text-white tracking-tight leading-none flex items-center gap-1.5">
              <span>PanelFlow</span>
            </span>
            <span className="text-[10px] text-slate-400 font-medium leading-none hidden 2xl:block mt-0.5">
              Turn Manga Pages into Animated Stories
            </span>
          </span>
        </button>

        <div className="hidden 2xl:block h-6 w-px bg-[#262a3b] mx-2" />

        {/* Breadcrumb Path */}
        <nav aria-label="Project breadcrumb" className="hidden 2xl:flex min-w-0 items-center gap-1.5 text-xs text-slate-400 font-medium">
          <button
            type="button"
            onClick={onBackToDashboard}
            className="hover:text-zinc-200 transition-colors"
          >
            My Projects
          </button>
          <span className="text-zinc-600">›</span>
          <span aria-current="page" className="text-slate-200 truncate max-w-[200px]" title={project.title}>
            {project.title}
          </span>
        </nav>
      </div>

      {/* Controls wrap rather than pushing primary actions outside the viewport. */}
      <div className="flex min-w-0 flex-wrap items-center justify-end gap-2">
        {/* Save Status */}
        <div role="status" aria-live="polite" className="flex items-center gap-1 text-[11px] font-medium mr-1">
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
            aria-label="Undo"
            disabled={!canUndo}
            className="h-8 w-7 flex items-center justify-center rounded hover:bg-white/5 hover:text-white disabled:opacity-30 transition-colors"
            title="Undo (Ctrl+Z)"
          >
            <Icons.Undo className="w-3.5 h-3.5" />
          </button>
          <button
            type="button"
            onClick={onRedo}
            aria-label="Redo"
            disabled={!canRedo}
            className="h-8 w-7 flex items-center justify-center rounded hover:bg-white/5 hover:text-white disabled:opacity-30 transition-colors"
            title="Redo (Ctrl+Y)"
          >
            <Icons.Redo className="w-3.5 h-3.5" />
          </button>
        </div>

        <div className="h-4 w-px bg-zinc-800" />

        {/* Mode Toggle */}
        <div role="group" aria-label="Editor mode" className="flex shrink-0 items-center bg-[#141722] border border-[#292d40] rounded-md p-0.5 text-xs">
          <button
            type="button"
            onClick={() => onUpdateState((s) => ({ ...s, mode: "simple" }))}
            aria-pressed={state.mode === "simple"}
            className={`h-7 px-2 rounded text-[11px] font-semibold transition-colors ${
              state.mode === "simple"
                ? "bg-gradient-to-br from-violet-500 to-indigo-600 text-white shadow-[0_0_14px_#713fff50]"
                : "text-zinc-400 hover:text-zinc-200"
            }`}
            title="Simple Storyboard Mode: Quick drag-and-drop story scenes"
          >
            Simple
          </button>
          <button
            type="button"
            onClick={() => onUpdateState((s) => ({ ...s, mode: "advanced" }))}
            aria-pressed={state.mode === "advanced"}
            className={`h-7 px-2 rounded text-[11px] font-semibold transition-colors ${
              state.mode === "advanced"
                ? "bg-gradient-to-br from-violet-500 to-indigo-600 text-white shadow-[0_0_14px_#713fff50]"
                : "text-zinc-400 hover:text-zinc-200"
            }`}
            title="Advanced Multitrack Mode: Independent layers, trim handles, and precise timing"
          >
            Advanced
          </button>
        </div>

        <div className="h-4 w-px bg-zinc-800" />

        {/* Aspect Ratio Selector */}
        <div className="h-9 flex shrink-0 items-center bg-[#10131e] border border-[#292d40] rounded-md px-2 text-xs text-slate-200 gap-1.5 shadow-inner">
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
            aria-label="Aspect ratio"
            value={state.aspect_ratio}
            onChange={(e) =>
              onUpdateState((s) => ({ ...s, aspect_ratio: e.target.value as StoryEditorState["aspect_ratio"] }))
            }
            className="min-w-0 bg-[#10131e] font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-violet-400 cursor-pointer text-[11px]"
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
          aria-label={state.is_playing ? "Pause preview" : "Preview"}
          aria-pressed={state.is_playing}
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
          <Icons.ExternalLink aria-hidden="true" className="w-3.5 h-3.5" />
          <span>Export</span>
        </button>


      </div>
    </header>
  );
};
