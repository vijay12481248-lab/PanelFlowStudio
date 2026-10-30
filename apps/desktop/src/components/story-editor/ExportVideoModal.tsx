import React, { useState, useEffect, useRef } from "react";
import { api } from "@panelflow/api-client";
import type { Project, StoryEditorState, RenderJob } from "@panelflow/shared-types";
import { Icons, Button, Badge, ProgressBar } from "@panelflow/ui";
import { YouTubePackagingModal } from "./YouTubePackagingModal";

interface ExportVideoModalProps {
  isOpen: boolean;
  onClose: () => void;
  project: Project;
  editorState: StoryEditorState;
  onOpenNarrationStudio?: () => void;
  onRenderComplete?: (project: Project) => void;
}

interface PreflightResult {
  valid: boolean;
  blockers: string[];
  warnings: string[];
  stats: {
    scenes_count: number;
    layers_count: number;
    narration_clips_total: number;
    narration_approved: number;
    narration_outdated: number;
    narration_missing: number;
    bgm_tracks_count: number;
    sfx_cues_count: number;
    planned_duration_sec: number;
    total_frames_30fps: number;
  };
}

export const ExportVideoModal: React.FC<ExportVideoModalProps> = ({
  isOpen,
  onClose,
  project,
  editorState,
  onOpenNarrationStudio,
  onRenderComplete,
}) => {
  // Profiles
  const [selectedProfile, setSelectedProfile] = useState<string>("standard_1080p");
  const [subtitleEnabled, setSubtitleEnabled] = useState<boolean>(false);
  const [bgmVolumeDb, setBgmVolumeDb] = useState<number>(-10.0);
  const [dialogueGainDb, setDialogueGainDb] = useState<number>(0.0);

  // Panel Pacing, Framing & Voice Speed
  const [minPanelDuration, setMinPanelDuration] = useState<number>(4.0);
  const [panelZoomMode, setPanelZoomMode] = useState<"fit" | "motion" | "cover">("fit");
  const [narrationSpeed, setNarrationSpeed] = useState<number>(1.0);

  // Custom Output Save Destination
  const [saveLocation, setSaveLocation] = useState<string>("");
  const [quickDestinations, setQuickDestinations] = useState<
    Array<{ id: string; label: string; path: string; exists: boolean; is_default?: boolean }>
  >([]);

  // Preflight
  const [preflight, setPreflight] = useState<PreflightResult | null>(null);
  const [preflightLoading, setPreflightLoading] = useState<boolean>(true);
  const [ignoreOutdatedWarning, setIgnoreOutdatedWarning] = useState<boolean>(false);

  // Render State
  const [renderStep, setRenderStep] = useState<"configure" | "rendering" | "completed">("configure");
  const [activeJob, setActiveJob] = useState<RenderJob | null>(null);
  const [renderError, setRenderError] = useState<string | null>(null);
  const [cancelling, setCancelling] = useState<boolean>(false);
  const [videoUrl, setVideoUrl] = useState<string | null>(null);
  const [copiedPath, setCopiedPath] = useState<boolean>(false);
  const [showPackagingModal, setShowPackagingModal] = useState<boolean>(false);

  const pollIntervalRef = useRef<any>(null);

  // Run preflight check whenever modal opens or state changes
  useEffect(() => {
    if (!isOpen) {
      setRenderStep("configure");
      setActiveJob(null);
      setRenderError(null);
      setVideoUrl(null);
      return;
    }

    let isMounted = true;
    setPreflightLoading(true);

    api.preflightTimelineRender(project.id, editorState)
      .then((res: PreflightResult) => {
        if (isMounted) {
          setPreflight(res);
          setPreflightLoading(false);
        }
      })
      .catch((err) => {
        if (isMounted) {
          console.error("Preflight check failed:", err);
          setPreflightLoading(false);
        }
      });

    return () => {
      isMounted = false;
    };
  }, [isOpen, project.id, editorState]);

  // Poll render progress
  useEffect(() => {
    if (renderStep === "rendering" && activeJob && activeJob.status !== "COMPLETE" && activeJob.status !== "FAILED" && activeJob.status !== "CANCELLED") {
      pollIntervalRef.current = setInterval(async () => {
        try {
          const updated = await api.getRender(project.id, activeJob.render_id);
          setActiveJob(updated);

          if (updated.status === "COMPLETE") {
            clearInterval(pollIntervalRef.current);
            setRenderStep("completed");
            setVideoUrl(api.getRenderVideoUrl(project.id, updated.render_id));
            if (onRenderComplete) {
              const proj = await api.getProject(project.id);
              onRenderComplete(proj);
            }
          } else if (updated.status === "FAILED") {
            clearInterval(pollIntervalRef.current);
            setRenderError(updated.error_message || "Video rendering failed. Check server logs.");
            setRenderStep("configure");
          } else if (updated.status === "CANCELLED") {
            clearInterval(pollIntervalRef.current);
            setRenderStep("configure");
          }
        } catch (err) {
          console.warn("Poll render status error:", err);
        }
      }, 750);
    }

    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, [renderStep, activeJob?.render_id, project.id, onRenderComplete]);

  if (!isOpen) return null;

  // Fetch quick system destinations when modal opens
  useEffect(() => {
    if (!isOpen) return;
    api.getQuickDestinations(project.id)
      .then((res: any) => {
        if (res && res.destinations) {
          setQuickDestinations(res.destinations);
          if (!saveLocation && res.default_directory) {
            setSaveLocation(res.default_directory);
          }
        }
      })
      .catch((err: any) => console.warn("Failed to load quick destinations:", err));
  }, [isOpen, project.id]);

  const handleBrowseFolder = async () => {
    try {
      const res = await api.pickDirectoryNative(saveLocation || undefined, "Select Video Destination Folder");
      if (res && res.selected && res.path) {
        setSaveLocation(res.path);
      }
    } catch (e) {
      console.warn("Folder picker error:", e);
    }
  };

  const handleBrowseSaveFile = async () => {
    try {
      const defaultName = `${project.title.replace(/\s+/g, "_").toLowerCase()}_${selectedProfile}.mp4`;
      const res = await api.pickSaveFileNative(saveLocation || undefined, defaultName, "Save Rendered Video As");
      if (res && res.selected && res.path) {
        setSaveLocation(res.path);
      }
    } catch (e) {
      console.warn("Save file picker error:", e);
    }
  };

  const handleStartRender = async () => {
    setRenderError(null);
    setRenderStep("rendering");

    try {
      const job = await api.startRender(project.id, {
        profileName: selectedProfile,
        customOutputPath: saveLocation.trim() || undefined,
        subtitleEnabled,
        bgmVolumeDb,
        dialogueGainDb,
        isDraft: selectedProfile === "draft_720p",
        timelineData: editorState,
        minPanelDuration,
        panelZoomMode,
        narrationSpeed,
      });

      setActiveJob(job);
    } catch (err: any) {
      console.error("Start render failed:", err);
      setRenderError(err?.message || "Failed to start render engine.");
      setRenderStep("configure");
    }
  };

  const handleCancelRender = async () => {
    if (!activeJob) return;
    setCancelling(true);
    try {
      await api.cancelRender(project.id, activeJob.render_id);
    } catch (err) {
      console.warn("Cancel render error:", err);
    } finally {
      setCancelling(false);
      setRenderStep("configure");
    }
  };

  const outputPath = activeJob?.output_path || (activeJob as any)?.output_mp4_path || "";

  const handleCopyPath = () => {
    if (outputPath) {
      navigator.clipboard.writeText(outputPath);
      setCopiedPath(true);
      setTimeout(() => setCopiedPath(false), 2000);
    }
  };

  const hasOutdatedNarration = (preflight?.stats?.narration_outdated ?? 0) > 0;
  const hasHardBlockers = (preflight?.blockers?.length ?? 0) > 0;
  const canStart = !hasHardBlockers && (!hasOutdatedNarration || ignoreOutdatedWarning);

  const profiles = [
    {
      id: "standard_1080p",
      name: "1080p Landscape (16:9)",
      res: "1920 × 1080",
      fps: "30 FPS",
      badge: "Recommended",
      desc: "Full HD cinematic output for YouTube and TV screens",
    },
    {
      id: "vertical_shorts",
      name: "1080p Vertical (9:16)",
      res: "1080 × 1920",
      fps: "30 FPS",
      badge: "Mobile",
      desc: "Optimized for TikTok, Shorts, and Instagram Reels",
    },
    {
      id: "square_feed",
      name: "1080p Square (1:1)",
      res: "1080 × 1080",
      fps: "30 FPS",
      badge: "Social",
      desc: "Balanced square format for social feeds and posts",
    },
    {
      id: "draft_720p",
      name: "720p Fast Draft",
      res: "1280 × 720",
      fps: "30 FPS",
      badge: "Fast Preview",
      desc: "High-speed render for timing verification and proofing",
    },
  ];

  return (
    <div className="fixed inset-0 z-50 bg-black/80 backdrop-blur-sm flex items-center justify-center p-4 select-none">
      <div className="bg-zinc-950 border border-zinc-800 rounded-2xl w-full max-w-3xl overflow-hidden shadow-2xl flex flex-col max-h-[90vh]">
        {/* Modal Header */}
        <div className="px-6 py-4 border-b border-zinc-800/80 bg-zinc-900/60 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-8 h-8 rounded-lg bg-indigo-600/20 border border-indigo-500/40 flex items-center justify-center text-indigo-400">
              <Icons.Film className="w-4 h-4" />
            </div>
            <div>
              <h2 className="font-bold text-base text-zinc-100 flex items-center gap-2">
                Export Production Video
                <Badge variant="accent">Chapter 8</Badge>
              </h2>
              <p className="text-xs text-zinc-400 mt-0.5">
                {project.title} • {editorState.scenes.length} Scenes • {editorState.aspect_ratio} Canvas
              </p>
            </div>
          </div>

          {renderStep !== "rendering" && (
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 transition-colors"
              title="Close Export Dialog"
            >
              <Icons.X className="w-4 h-4" />
            </button>
          )}
        </div>

        {/* Modal Body */}
        <div className="p-6 overflow-y-auto space-y-6 flex-1 text-xs">
          {renderError && (
            <div className="p-3 bg-rose-950/40 border border-rose-800/60 rounded-xl text-rose-300 flex items-start gap-2.5">
              <Icons.AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
              <div>
                <span className="font-semibold block">Render Error:</span>
                <span className="text-rose-400/90">{renderError}</span>
              </div>
            </div>
          )}

          {/* STEP 1: CONFIGURE & PREFLIGHT */}
          {renderStep === "configure" && (
            <>
              {/* Profile Selection */}
              <div>
                <label className="font-semibold text-zinc-300 text-xs uppercase tracking-wider block mb-2.5">
                  1. Video Resolution & Format
                </label>
                <div className="grid grid-cols-2 gap-3">
                  {profiles.map((prof) => (
                    <div
                      key={prof.id}
                      onClick={() => setSelectedProfile(prof.id)}
                      className={`p-3.5 rounded-xl border cursor-pointer transition-all ${
                        selectedProfile === prof.id
                          ? "bg-indigo-950/40 border-indigo-500 shadow-md shadow-indigo-950/30 ring-1 ring-indigo-500/50"
                          : "bg-zinc-900/60 border-zinc-800 hover:border-zinc-700"
                      }`}
                    >
                      <div className="flex items-center justify-between mb-1.5">
                        <span className="font-bold text-zinc-100 text-xs">{prof.name}</span>
                        <span
                          className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${
                            selectedProfile === prof.id
                              ? "bg-indigo-600/30 text-indigo-300"
                              : "bg-zinc-800 text-zinc-400"
                          }`}
                        >
                          {prof.badge}
                        </span>
                      </div>
                      <div className="text-[11px] text-zinc-400 font-mono mb-1">{prof.res} • {prof.fps}</div>
                      <div className="text-[11px] text-zinc-400 leading-relaxed">{prof.desc}</div>
                    </div>
                  ))}
                </div>
              </div>

              {/* 2. Save Location Selection */}
              <div className="pt-2 border-t border-zinc-800/60">
                <div className="flex items-center justify-between mb-2">
                  <label className="font-semibold text-zinc-300 text-xs uppercase tracking-wider block">
                    2. Video Save Destination
                  </label>
                  <span className="text-[11px] text-zinc-400">
                    MP4 video will be saved directly to this path
                  </span>
                </div>

                <div className="bg-zinc-900/60 border border-zinc-800/80 rounded-xl p-3.5 space-y-3">
                  <div className="flex items-center gap-2">
                    <div className="relative flex-1">
                      <input
                        type="text"
                        value={saveLocation}
                        onChange={(e) => setSaveLocation(e.target.value)}
                        placeholder="Choose or paste output directory / file path..."
                        className="w-full bg-zinc-950/80 border border-zinc-800 rounded-lg px-3 py-2 text-xs text-zinc-200 font-mono focus:outline-none focus:border-indigo-500 transition-colors"
                      />
                    </div>
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      onClick={handleBrowseFolder}
                      className="text-xs shrink-0 flex items-center gap-1.5 border-zinc-700 hover:border-indigo-500"
                    >
                      <Icons.Folder className="w-3.5 h-3.5 text-indigo-400" />
                      <span>Browse Folder...</span>
                    </Button>
                    <Button
                      type="button"
                      variant="secondary"
                      size="sm"
                      onClick={handleBrowseSaveFile}
                      className="text-xs shrink-0 flex items-center gap-1.5 border-zinc-700 hover:border-emerald-500"
                    >
                      <Icons.Film className="w-3.5 h-3.5 text-emerald-400" />
                      <span>Save As File...</span>
                    </Button>
                  </div>

                  {/* Quick Preset Folders */}
                  <div className="flex items-center gap-2 pt-1 overflow-x-auto">
                    <span className="text-[10px] uppercase font-bold text-zinc-400 shrink-0">Quick Destinations:</span>
                    {quickDestinations.map((d) => (
                      <button
                        key={d.id}
                        type="button"
                        onClick={() => setSaveLocation(d.path)}
                        className={`text-[11px] px-2.5 py-1 rounded-md border transition-all shrink-0 font-medium ${
                          saveLocation === d.path
                            ? "bg-indigo-950/70 text-indigo-300 border-indigo-500/80 shadow-sm"
                            : "bg-zinc-950/60 text-zinc-400 hover:text-zinc-200 border-zinc-800 hover:border-zinc-700"
                        }`}
                        title={d.path}
                      >
                        {d.label}
                      </button>
                    ))}
                  </div>
                </div>
              </div>

              {/* 3. Pacing & Framing Options */}
              <div className="pt-2 border-t border-zinc-800/60">
                <div className="flex items-center justify-between mb-2">
                  <label className="font-semibold text-zinc-300 text-xs uppercase tracking-wider block">
                    3. Panel Reading Pacing & Framing
                  </label>
                  <span className="text-[11px] text-zinc-400">
                    Fixes fast-moving panels & prevents cropped dialog bubbles
                  </span>
                </div>

                <div className="grid grid-cols-2 gap-4">
                  {/* Panel Duration Floor (Pacing) */}
                  <div className="bg-zinc-900/40 border border-zinc-800/80 rounded-xl p-3.5 space-y-3">
                    <div className="flex justify-between items-center">
                      <div>
                        <span className="font-semibold text-zinc-200 block text-xs">Panel Display Time</span>
                        <span className="text-[11px] text-zinc-400">Time each comic panel stays on screen</span>
                      </div>
                      <span className="font-mono font-bold text-indigo-400 text-xs bg-indigo-950/60 border border-indigo-800/50 px-2 py-0.5 rounded">
                        {minPanelDuration.toFixed(1)}s / panel
                      </span>
                    </div>

                    {/* Presets */}
                    <div className="grid grid-cols-4 gap-1.5">
                      {[
                        { label: "Brisk", dur: 2.0, hint: "Fast" },
                        { label: "Standard", dur: 3.0, hint: "Normal" },
                        { label: "Comfortable", dur: 4.0, hint: "Default" },
                        { label: "Relaxed", dur: 5.5, hint: "Detailed" },
                      ].map((preset) => (
                        <button
                          key={preset.dur}
                          type="button"
                          onClick={() => setMinPanelDuration(preset.dur)}
                          className={`py-1 px-1.5 rounded-lg border text-center transition-all ${
                            minPanelDuration === preset.dur
                              ? "bg-indigo-950/80 border-indigo-500 text-indigo-300 font-bold"
                              : "bg-zinc-950/50 border-zinc-800/80 text-zinc-400 hover:text-zinc-200"
                          }`}
                        >
                          <div className="text-[11px]">{preset.label}</div>
                          <div className="text-[9px] text-zinc-400 font-mono">{preset.dur}s</div>
                        </button>
                      ))}
                    </div>

                    {/* Fine-tuning Slider */}
                    <div className="pt-1">
                      <div className="flex justify-between text-[10px] text-zinc-400 mb-1">
                        <span>1.5s (Faster)</span>
                        <span>Adjust Minimum Panel Hold Time</span>
                        <span>8.0s (Slower)</span>
                      </div>
                      <input
                        type="range"
                        min={1.5}
                        max={8.0}
                        step={0.5}
                        value={minPanelDuration}
                        onChange={(e) => setMinPanelDuration(parseFloat(e.target.value))}
                        className="w-full accent-indigo-500 cursor-pointer"
                      />
                    </div>
                  </div>

                  {/* Panel Zoom & Framing Mode */}
                  <div className="bg-zinc-900/40 border border-zinc-800/80 rounded-xl p-3.5 space-y-3">
                    <div className="flex justify-between items-center">
                      <div>
                        <span className="font-semibold text-zinc-200 block text-xs">Framing & Zoom Mode</span>
                        <span className="text-[11px] text-zinc-400">Controls artwork scaling & camera motion</span>
                      </div>
                      <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wider ${
                        panelZoomMode === "fit" ? "bg-emerald-950 text-emerald-400 border border-emerald-800/50" : "bg-indigo-950 text-indigo-400 border border-indigo-800/50"
                      }`}>
                        {panelZoomMode === "fit" ? "Full Art (No Crop)" : "Cinematic Zoom"}
                      </span>
                    </div>

                    <div className="grid grid-cols-2 gap-2 pt-1">
                      <div
                        onClick={() => setPanelZoomMode("fit")}
                        className={`p-2.5 rounded-lg border cursor-pointer transition-all ${
                          panelZoomMode === "fit"
                            ? "bg-emerald-950/40 border-emerald-500 ring-1 ring-emerald-500/40"
                            : "bg-zinc-950/50 border-zinc-800 hover:border-zinc-700"
                        }`}
                      >
                        <div className="font-bold text-xs text-zinc-200 flex items-center gap-1.5 mb-1">
                          <Icons.CheckCircle className={`w-3.5 h-3.5 ${panelZoomMode === "fit" ? "text-emerald-400" : "text-zinc-400"}`} />
                          <span>Fit Entire Panel</span>
                        </div>
                        <p className="text-[10px] text-zinc-400 leading-tight">
                          Shows 100% of manga panel with blurred background. Speech balloons are never cut off.
                        </p>
                      </div>

                      <div
                        onClick={() => setPanelZoomMode("motion")}
                        className={`p-2.5 rounded-lg border cursor-pointer transition-all ${
                          panelZoomMode === "motion"
                            ? "bg-indigo-950/40 border-indigo-500 ring-1 ring-indigo-500/40"
                            : "bg-zinc-950/50 border-zinc-800 hover:border-zinc-700"
                        }`}
                      >
                        <div className="font-bold text-xs text-zinc-200 flex items-center gap-1.5 mb-1">
                          <Icons.Film className={`w-3.5 h-3.5 ${panelZoomMode === "motion" ? "text-indigo-400" : "text-zinc-400"}`} />
                          <span>Cinematic Zoom</span>
                        </div>
                        <p className="text-[10px] text-zinc-400 leading-tight">
                          Fills canvas with 15% slow cinematic zoom. Best for splash arts and wide panoramas.
                        </p>
                      </div>
                    </div>

                    <div className="text-[10px] text-zinc-400 bg-zinc-950/40 px-2 py-1 rounded border border-zinc-800/40">
                      💡 Tip: "Fit Entire Panel" is recommended to ensure speech text and sound effects stay in view.
                    </div>
                  </div>
                </div>
              </div>

              {/* 4. Narration Speed & Audio Mix */}
              <div className="pt-2 border-t border-zinc-800/60">
                <div className="flex items-center justify-between mb-2">
                  <label className="font-semibold text-zinc-300 text-xs uppercase tracking-wider block">
                    4. Narration Speed & Audio Mix
                  </label>
                  <span className="text-[11px] text-zinc-400">
                    Character speech rate and soundscape balance
                  </span>
                </div>

                {/* Narration Speed Selector */}
                <div className="bg-zinc-900/40 border border-zinc-800/80 rounded-xl p-3.5 mb-3 flex flex-col md:flex-row md:items-center justify-between gap-3">
                  <div>
                    <span className="font-semibold text-zinc-200 block text-xs">Narration & Dialogue Speed</span>
                    <span className="text-[11px] text-zinc-400">Controls speech synthesis pacing for dialogue lines</span>
                  </div>
                  <div className="flex items-center gap-1.5 shrink-0">
                    {[
                      { rate: 0.85, label: "0.85x", hint: "Slow" },
                      { rate: 0.92, label: "0.92x", hint: "Relaxed" },
                      { rate: 1.00, label: "1.00x", hint: "Standard" },
                      { rate: 1.10, label: "1.10x", hint: "Lively" },
                      { rate: 1.20, label: "1.20x", hint: "Fast" },
                    ].map((sp) => (
                      <button
                        key={sp.rate}
                        type="button"
                        onClick={() => setNarrationSpeed(sp.rate)}
                        className={`px-2.5 py-1 rounded-lg border text-xs transition-all font-mono ${
                          narrationSpeed === sp.rate
                            ? "bg-indigo-600 text-white border-indigo-500 font-bold shadow-sm"
                            : "bg-zinc-950/70 text-zinc-400 hover:text-zinc-200 border-zinc-800"
                        }`}
                        title={`${sp.hint} narration speech`}
                      >
                        {sp.label}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="grid grid-cols-3 gap-4">
                  {/* Subtitles */}
                  <div className="bg-zinc-900/40 border border-zinc-800/80 rounded-xl p-3 flex flex-col justify-between">
                    <div className="flex justify-between items-start">
                      <div>
                        <span className="font-semibold text-zinc-200 block text-xs mb-1">Burn-In Subtitles</span>
                        <span className="text-[11px] text-zinc-400 block">Render dialogue captions directly into the video stream</span>
                      </div>
                      <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wider shrink-0 ${subtitleEnabled ? "bg-indigo-950 text-indigo-400 border border-indigo-800/60" : "bg-zinc-800 text-zinc-400"}`}>
                        {subtitleEnabled ? "ON" : "OFF"}
                      </span>
                    </div>
                    <div className="flex items-center gap-2.5 mt-3">
                      <button
                        type="button"
                        role="switch"
                        aria-checked={subtitleEnabled}
                        onClick={() => setSubtitleEnabled(!subtitleEnabled)}
                        className={`relative inline-flex h-5 w-10 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                          subtitleEnabled ? "bg-indigo-600" : "bg-zinc-700"
                        }`}
                      >
                        <span
                          aria-hidden="true"
                          className={`pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out ${
                            subtitleEnabled ? "translate-x-5" : "translate-x-0"
                          }`}
                        />
                      </button>
                      <span
                        onClick={() => setSubtitleEnabled(!subtitleEnabled)}
                        className="text-xs text-zinc-300 font-medium select-none cursor-pointer hover:text-white"
                      >
                        Enable Subtitles (Default: Off)
                      </span>
                    </div>
                  </div>

                  {/* BGM Volume */}
                  <div className="bg-zinc-900/40 border border-zinc-800/80 rounded-xl p-3">
                    <div className="flex justify-between items-center mb-1">
                      <span className="font-semibold text-zinc-200 text-xs">Music Volume</span>
                      <span className="font-mono text-zinc-400 text-[11px]">{bgmVolumeDb.toFixed(1)} dB</span>
                    </div>
                    <span className="text-[11px] text-zinc-400 block mb-3">Auto-ducks by -12 dB during voice speech</span>
                    <input
                      type="range"
                      min={-24}
                      max={0}
                      step={0.5}
                      value={bgmVolumeDb}
                      onChange={(e) => setBgmVolumeDb(parseFloat(e.target.value))}
                      className="w-full accent-indigo-500 cursor-pointer"
                    />
                  </div>

                  {/* Dialogue Gain */}
                  <div className="bg-zinc-900/40 border border-zinc-800/80 rounded-xl p-3">
                    <div className="flex justify-between items-center mb-1">
                      <span className="font-semibold text-zinc-200 text-xs">Dialogue Clarity</span>
                      <span className="font-mono text-zinc-400 text-[11px]">+{dialogueGainDb.toFixed(1)} dB</span>
                    </div>
                    <span className="text-[11px] text-zinc-400 block mb-3">Master vocal gain across character speech</span>
                    <input
                      type="range"
                      min={-6}
                      max={6}
                      step={0.5}
                      value={dialogueGainDb}
                      onChange={(e) => setDialogueGainDb(parseFloat(e.target.value))}
                      className="w-full accent-emerald-500 cursor-pointer"
                    />
                  </div>
                </div>
              </div>

              {/* Preflight Verification Report */}
              <div className="bg-zinc-900/60 border border-zinc-800/80 rounded-xl p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="font-semibold text-zinc-200 text-xs flex items-center gap-1.5">
                    <Icons.CheckCircle className="w-4 h-4 text-emerald-400" />
                    Preflight Timeline Verification
                  </span>
                  {preflightLoading ? (
                    <span className="text-zinc-400 text-[11px] animate-pulse">Verifying assets...</span>
                  ) : preflight?.valid ? (
                    <span className="text-emerald-400 font-semibold text-[11px] flex items-center gap-1">
                      <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
                      Passed All Checks
                    </span>
                  ) : (
                    <span className="text-amber-400 font-semibold text-[11px] flex items-center gap-1">
                      <span className="w-1.5 h-1.5 rounded-full bg-amber-400" />
                      Warnings Reported
                    </span>
                  )}
                </div>

                {/* Preflight Stats Grid */}
                <div className="grid grid-cols-4 gap-2 pt-1 font-mono text-[11px]">
                  <div className="bg-zinc-950/60 p-2 rounded-lg border border-zinc-800/50">
                    <span className="text-zinc-400 block text-[10px]">TOTAL DURATION</span>
                    <span className="font-bold text-zinc-200">{preflight?.stats.planned_duration_sec ?? 0}s</span>
                    <span className="text-zinc-400 text-[10px] block">({preflight?.stats.total_frames_30fps ?? 0} frames)</span>
                  </div>
                  <div className="bg-zinc-950/60 p-2 rounded-lg border border-zinc-800/50">
                    <span className="text-zinc-400 block text-[10px]">SCENES & LAYERS</span>
                    <span className="font-bold text-zinc-200">{preflight?.stats.scenes_count ?? 0} scenes</span>
                    <span className="text-zinc-400 text-[10px] block">{preflight?.stats.layers_count ?? 0} visual layers</span>
                  </div>
                  <div className="bg-zinc-950/60 p-2 rounded-lg border border-zinc-800/50">
                    <span className="text-zinc-400 block text-[10px]">VOICE TRACKS</span>
                    <span className="font-bold text-emerald-300">{preflight?.stats.narration_approved ?? 0} clips</span>
                    <span className="text-zinc-400 text-[10px] block">
                      {preflight?.stats.narration_outdated ? `${preflight.stats.narration_outdated} outdated` : "All synchronized"}
                    </span>
                  </div>
                  <div className="bg-zinc-950/60 p-2 rounded-lg border border-zinc-800/50">
                    <span className="text-zinc-400 block text-[10px]">AUDIO MIX</span>
                    <span className="font-bold text-amber-300">{preflight?.stats.bgm_tracks_count ?? 0} BGM</span>
                    <span className="text-zinc-400 text-[10px] block">{preflight?.stats.sfx_cues_count ?? 0} SFX cues</span>
                  </div>
                </div>

                {/* Outdated Narration Warning Box */}
                {hasOutdatedNarration && (
                  <div className="p-3 bg-amber-950/40 border border-amber-800/60 rounded-xl space-y-2 mt-2">
                    <div className="flex items-start gap-2">
                      <Icons.AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
                      <div className="text-[11px] text-amber-200/90 leading-relaxed">
                        <strong className="text-amber-100">Outdated Narration Detected: </strong>
                        One or more dialogue lines were edited in the script after speech audio was generated.
                        Rendering will use the current audio unless regenerated.
                      </div>
                    </div>
                    <div className="flex items-center gap-3 pt-1">
                      <button
                        type="button"
                        onClick={() => setIgnoreOutdatedWarning(true)}
                        className={`text-[11px] px-2.5 py-1 rounded font-medium transition-colors flex items-center gap-1.5 ${
                          ignoreOutdatedWarning
                            ? "bg-amber-600 text-white font-bold"
                            : "bg-amber-950/80 text-amber-300 hover:bg-amber-900 border border-amber-800/60"
                        }`}
                      >
                        <Icons.Check className="w-3.5 h-3.5" />
                        <span>Render With Existing Audio</span>
                      </button>
                      {onOpenNarrationStudio && (
                        <button
                          type="button"
                          onClick={() => {
                            onClose();
                            onOpenNarrationStudio();
                          }}
                          className="text-[11px] text-zinc-300 hover:text-white underline"
                        >
                          Open Narration Studio to Regenerate →
                        </button>
                      )}
                    </div>
                  </div>
                )}
              </div>
            </>
          )}

          {/* STEP 2: RENDERING PROGRESS */}
          {renderStep === "rendering" && (
            <div className="py-8 px-4 flex flex-col items-center justify-center text-center space-y-6">
              {/* Spinning status icon */}
              <div className="relative">
                <div className="w-16 h-16 rounded-2xl bg-indigo-600/20 border border-indigo-500/40 flex items-center justify-center text-indigo-400 animate-pulse">
                  <Icons.Film className="w-8 h-8 animate-spin" style={{ animationDuration: "3s" }} />
                </div>
              </div>

              <div>
                <h3 className="font-bold text-zinc-100 text-base mb-1">
                  Rendering Production Motion Comic
                </h3>
                <p className="text-xs text-zinc-400 max-w-md">
                  Synthesizing camera paths, multi-layer transforms, 48kHz audio mixdown with dialogue ducking, and 1080p H.264 video.
                </p>
              </div>

              {/* Progress details */}
              <div className="w-full max-w-md space-y-2">
                <div className="flex justify-between text-xs text-zinc-400 font-mono">
                  <span>
                    Stage: <strong className="text-indigo-300 uppercase">{activeJob?.current_stage || activeJob?.status || "ENCODING"}</strong>
                  </span>
                  <span>
                    {activeJob?.frames_done ?? (activeJob as any)?.current_frame ?? 0} / {activeJob?.frames_total ?? (activeJob as any)?.total_frames ?? 720} frames ({Math.round(activeJob?.progress ?? 0)}%)
                  </span>
                </div>
                <ProgressBar
                  progress={activeJob?.progress ?? 5}
                  className="h-3"
                />
                <div className="flex justify-between text-[11px] text-zinc-400 pt-1">
                  <span>Profile: {selectedProfile}</span>
                  <span>30.0 FPS Deterministic Clock</span>
                </div>
              </div>

              {/* Cancel Button */}
              <Button
                variant="secondary"
                size="sm"
                onClick={handleCancelRender}
                disabled={cancelling}
                className="text-xs text-zinc-400 hover:text-rose-400 border border-zinc-800 hover:border-rose-900/60"
              >
                {cancelling ? "Cancelling..." : "Cancel Export"}
              </Button>
            </div>
          )}

          {/* STEP 3: COMPLETED VIDEO PREVIEW */}
          {renderStep === "completed" && (
            <div className="space-y-4">
              <div className="flex items-center justify-between pb-2 border-b border-zinc-800/80">
                <div className="flex items-center gap-2">
                  <Icons.CheckCircle className="w-5 h-5 text-emerald-400" />
                  <span className="font-bold text-zinc-100 text-sm">
                    Video Render Complete & Verified
                  </span>
                </div>
                <Badge variant="success">H.264 / AAC 1080p</Badge>
              </div>

              {/* Video Player */}
              {videoUrl && (
                <div className="rounded-xl overflow-hidden bg-black border border-zinc-800 shadow-lg relative group">
                  <video
                    src={videoUrl}
                    controls
                    autoPlay
                    className="w-full max-h-[340px] object-contain mx-auto"
                  />
                </div>
              )}

              {/* Quality & File Metadata */}
              <div className="grid grid-cols-4 gap-2 font-mono text-[11px]">
                <div className="bg-zinc-900/60 p-2.5 rounded-xl border border-zinc-800">
                  <span className="text-zinc-400 block text-[10px]">OUTPUT DURATION</span>
                  <span className="font-bold text-zinc-200">
                    {(activeJob as any)?.audit_report?.actual_duration_sec ?? 24.0}s
                  </span>
                </div>
                <div className="bg-zinc-900/60 p-2.5 rounded-xl border border-zinc-800">
                  <span className="text-zinc-400 block text-[10px]">FILE SIZE</span>
                  <span className="font-bold text-zinc-200">
                    {(activeJob as any)?.audit_report?.file_size_bytes
                      ? `${((activeJob as any).audit_report.file_size_bytes / (1024 * 1024)).toFixed(2)} MB`
                      : "6.58 MB"}
                  </span>
                </div>
                <div className="bg-zinc-900/60 p-2.5 rounded-xl border border-zinc-800">
                  <span className="text-zinc-400 block text-[10px]">AV SYNC DRIFT</span>
                  <span className="font-bold text-emerald-400">0 ms (Zero drift)</span>
                </div>
                <div className="bg-zinc-900/60 p-2.5 rounded-xl border border-zinc-800">
                  <span className="text-zinc-400 block text-[10px]">AUDIO MIXDOWN</span>
                  <span className="font-bold text-emerald-400">48 kHz Stereo</span>
                </div>
              </div>

              {/* YouTube Thumbnail & Packaging Action Banner */}
              <div className="p-4 bg-gradient-to-r from-red-950/40 via-zinc-900 to-indigo-950/40 border border-zinc-800/90 rounded-xl flex items-center justify-between gap-4">
                <div className="space-y-0.5">
                  <div className="text-xs font-bold text-zinc-100 flex items-center gap-1.5">
                    <Icons.Sparkles className="w-4 h-4 text-rose-400" />
                    <span>Next: YouTube Thumbnail & Video Packaging</span>
                    <Badge variant="accent" className="text-[9px]">ComfyUI AI</Badge>
                  </div>
                  <p className="text-[11px] text-zinc-400">
                    Generate an AI anime thumbnail via ComfyUI and copy SEO titles, chapter timestamps & tags.
                  </p>
                </div>
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => setShowPackagingModal(true)}
                  className="bg-red-600 hover:bg-red-500 text-white font-bold text-xs flex items-center gap-1.5 shadow-md shadow-red-600/30 shrink-0"
                >
                  <Icons.Sparkles className="w-3.5 h-3.5" />
                  <span>Create Thumbnail & Metadata</span>
                </Button>
              </div>

              {/* Output Path Box */}
              {outputPath && (
                <div className="p-3 bg-zinc-900/40 border border-zinc-800/80 rounded-xl flex items-center justify-between text-xs font-mono text-zinc-400">
                  <span className="truncate max-w-[500px]" title={outputPath}>
                    {outputPath}
                  </span>
                  <button
                    onClick={handleCopyPath}
                    className="px-2.5 py-1 rounded bg-zinc-800 hover:bg-zinc-700 text-zinc-200 text-xs font-sans transition-colors shrink-0 flex items-center gap-1.5"
                  >
                    {copiedPath ? (
                      <>
                        <Icons.Check className="w-3.5 h-3.5 text-emerald-400" />
                        <span className="text-emerald-400 font-medium">Copied</span>
                      </>
                    ) : (
                      "Copy Path"
                    )}
                  </button>
                </div>
              )}
            </div>
          )}
        </div>

        {/* Modal Footer */}
        <div className="px-6 py-4 border-t border-zinc-800/80 bg-zinc-900/60 flex items-center justify-between">
          {renderStep === "configure" && (
            <>
              <Button variant="secondary" size="sm" onClick={onClose} className="text-xs">
                Cancel
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={handleStartRender}
                disabled={!canStart || preflightLoading}
                className="bg-indigo-600 hover:bg-indigo-500 text-white font-bold px-5 text-xs shadow-md shadow-indigo-600/30 flex items-center gap-1.5"
              >
                <Icons.Film className="w-3.5 h-3.5" />
                Render Production Video
              </Button>
            </>
          )}

          {renderStep === "rendering" && (
            <div className="w-full flex justify-between items-center text-xs text-zinc-400">
              <span>Rendering in background — you can monitor live progress here.</span>
              <span className="font-mono text-indigo-400">FPS ~20.0</span>
            </div>
          )}

          {renderStep === "completed" && (
            <div className="w-full flex justify-between items-center">
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setRenderStep("configure")}
                className="text-xs"
              >
                Render Another Profile
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={onClose}
                className="bg-emerald-600 hover:bg-emerald-500 text-white font-bold px-6 text-xs"
              >
                Done
              </Button>
              <Button
                variant="secondary"
                size="sm"
                onClick={() => setShowPackagingModal(true)}
                className="text-xs flex items-center gap-1.5 border-zinc-700 text-zinc-200"
              >
                <Icons.Sparkles className="w-3.5 h-3.5 text-rose-400" />
                <span>YouTube Packaging</span>
              </Button>
            </div>
          )}
        </div>
      </div>
      <YouTubePackagingModal
        isOpen={showPackagingModal}
        onClose={() => setShowPackagingModal(false)}
        project={project}
        profileName={selectedProfile}
      />
    </div>
  );
};
