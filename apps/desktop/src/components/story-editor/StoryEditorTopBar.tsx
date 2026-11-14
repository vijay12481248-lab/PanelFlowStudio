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
    <header className="min-h-[56px] min-w-0 shrink-0 border-b border-[#162049] bg-[#070b1c] px-3 py-2 flex flex-wrap gap-x-3 gap-y-2 items-center justify-between sticky top-0 z-40 select-none [&_button]:focus-visible:outline-none [&_button]:focus-visible:ring-2 [&_button]:focus-visible:ring-accent [&_svg]:shrink-0">
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
          <span aria-hidden="true" className="w-8 h-8 rounded-md bg-gradient-to-br from-accent to-accent flex items-center justify-center text-white font-black text-xl shadow-[0_0_22px_#713fff55] group-hover:from-accent transition-colors">
            P
          </span>
          <span>
            <span className="font-extrabold text-lg text-white tracking-tight leading-none flex items-center gap-1.5">
              <span>PanelFlow</span>
            </span>
            <span className="text-[10px] text-fg-dim font-medium leading-none hidden 2xl:block mt-0.5">
              Turn Manga Pages into Animated Stories
            </span>
          </span>
        </button>

        <div className="hidden 2xl:block h-6 w-px bg-[#162049] mx-2" />

        {/* Breadcrumb Path */}
        <nav aria-label="Project breadcrumb" className="hidden 2xl:flex min-w-0 items-center gap-1.5 text-xs text-fg-dim font-medium">
          <button
            type="button"
            onClick={onBackToDashboard}
            className="hover:text-fg transition-colors"
          >
            My Projects
          </button>
          <span className="text-fg-faint">›</span>
          <span aria-current="page" className="text-fg truncate max-w-[200px]" title={project.title}>
            {project.title}
          </span>
        </nav>
      </div>

      {/* Controls wrap rather than pushing primary actions outside the viewport. */}
      <div className="flex min-w-0 flex-wrap items-center justify-end gap-2">
        {/* Save Status */}
        <div role="status" aria-live="polite" className="flex items-center gap-1 text-[11px] font-medium mr-1">
          {saveStatus === "saving" ? (
            <span className="text-warn flex items-center gap-1.5">
              <span className="w-2 h-2 rounded-full bg-warn animate-pulse" />
              Saving...
            </span>
          ) : saveStatus === "unsaved" ? (
            <span className="text-fg-dim flex items-center gap-1.5" title="Changes will auto-save shortly">
              <span className="w-2 h-2 rounded-full bg-warn/80" />
              Unsaved
            </span>
          ) : (
            <span className="text-ok flex items-center gap-1.5">
              <Icons.Check className="w-3.5 h-3.5 text-ok" />
              Saved
            </span>
          )}
        </div>

        {/* Undo / Redo */}
        <div className="flex items-center gap-1 text-fg-dim">
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

        <div className="h-4 w-px bg-flat" />

        {/* Mode Toggle */}
        <div role="group" aria-label="Editor mode" className="flex shrink-0 items-center bg-[#0c1433] border border-[#162049] rounded-md p-0.5 text-xs">
          <button
            type="button"
            onClick={() => onUpdateState((s) => ({ ...s, mode: "simple" }))}
            aria-pressed={state.mode === "simple"}
            className={`h-7 px-2 rounded text-[11px] font-semibold transition-colors ${
              state.mode === "simple"
                ? "bg-gradient-to-br from-accent to-accent text-white shadow-[0_0_14px_#713fff50]"
                : "text-fg-dim hover:text-fg"
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
                ? "bg-gradient-to-br from-accent to-accent text-white shadow-[0_0_14px_#713fff50]"
                : "text-fg-dim hover:text-fg"
            }`}
            title="Advanced Multitrack Mode: Independent layers, trim handles, and precise timing"
          >
            Advanced
          </button>
        </div>

        <div className="h-4 w-px bg-flat" />

        {/* Aspect Ratio Selector */}
        <div className="h-9 flex shrink-0 items-center bg-[#0c1433] border border-[#162049] rounded-md px-2 text-xs text-fg gap-1.5 shadow-inner">
          <svg className="w-3.5 h-3.5 text-fg-dim" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
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
            className="min-w-0 bg-[#0c1433] font-medium focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent cursor-pointer text-[11px]"
          >
            <option value="16:9" className="bg-navy text-fg">16:9 Landscape</option>
            <option value="9:16" className="bg-navy text-fg">9:16 Vertical</option>
            <option value="1:1" className="bg-navy text-fg">1:1 Square</option>
          </select>
        </div>

        {/* Narration Studio Workspace Launcher */}
        {onOpenNarrationStudio && (
          <button
            type="button"
            onClick={onOpenNarrationStudio}
            className="text-xs h-8 px-3 rounded-lg border border-ok/60 bg-ok/40 text-ok hover:bg-ok/60 hover:text-ok flex items-center gap-1.5 font-semibold transition-all shadow-sm shadow-ok/20 active:scale-95"
            title="Open AI Narration & Storytelling Studio"
          >

            <Icons.Mic className="w-3.5 h-3.5 text-ok" />
            <span>Narration Studio</span>
          </button>
        )}

        {/* Audio Library Workspace Launcher */}
        {onOpenAudioLibrary && (
          <button
            type="button"
            onClick={onOpenAudioLibrary}
            className="text-xs h-8 px-3 rounded-lg border border-warn/60 bg-warn/40 text-warn hover:bg-warn/60 hover:text-warn flex items-center gap-1.5 font-semibold transition-all shadow-sm shadow-warn/20 active:scale-95"
            title="Open Music & Sound Effects Library"
          >
            <Icons.Music className="w-3.5 h-3.5 text-warn" />
            <span>Audio Library</span>
          </button>
        )}

        {/* + Add Motion Scene Button */}
        <button
          type="button"
          onClick={() => {
            const newSceneId = `scene_mg_${Date.now()}`;
            onUpdateState((s) => ({
              ...s,
              scenes: [
                ...s.scenes,
                {
                  id: newSceneId,
                  sequence: s.scenes.length + 1,
                  type: "motion_graphic",
                  motion_preset_id: "keynote_showcase",
                  duration_sec: 6.0,
                  motion_props: {
                    headline: "SYNTHESIS ONE",
                    subtitle: "The Next Generation Neural Presentation Architecture",
                    badge_text: "GLOBAL KEYNOTE 2026",
                  },
                  layers: [],
                } as any,
              ],
            }));
          }}
          className="text-xs h-8 px-3 rounded-lg border border-accent/60 bg-accent/40 text-info hover:bg-accent/60 hover:text-info flex items-center gap-1.5 font-semibold transition-all shadow-sm shadow-accent/20 active:scale-95"
          title="Add a Procedural Motion Graphic Scene"
        >
          <Icons.Sparkles className="w-3.5 h-3.5 text-info" />
          <span>+ Motion Scene</span>
        </button>

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
              ? "bg-warn text-white border-warn shadow-md shadow-warn/20 ring-1 ring-warn/50"
              : "bg-navy border-edge hover:border-fg-faint text-fg"
          }`}
        >
          {state.is_playing ? (
            <>
              <Icons.Pause className="w-3.5 h-3.5 fill-current" />
              <span>Playing</span>
            </>
          ) : (
            <>
              <Icons.Play className="w-3.5 h-3.5 text-info" />
              <span>Preview</span>
            </>
          )}
        </button>

        {/* Primary Purple Export Button */}
        <button
          type="button"
          onClick={onExportClick}
          className="bg-gradient-to-r from-accent to-accent hover:from-accent hover:to-accent text-white font-bold h-8 px-4 rounded-lg shadow-md shadow-accent/30 flex items-center gap-1.5 transition-all active:scale-95"
        >
          <Icons.ExternalLink aria-hidden="true" className="w-3.5 h-3.5" />
          <span>Export</span>
        </button>


      </div>
    </header>
  );
};
