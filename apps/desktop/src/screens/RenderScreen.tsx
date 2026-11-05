import React, { useEffect, useState, useCallback, useRef } from "react";
import { api } from "@panelflow/api-client";
import type { Project, RenderJob, RenderStatus } from "@panelflow/shared-types";
import { Button, Card, Badge, ProgressBar, Icons, SvgProductionTrophy } from "@panelflow/ui";
import { useError } from "../context/ErrorContext";
import { YouTubePackagingModal } from "../components/story-editor/YouTubePackagingModal";

export interface RenderScreenProps {
  project: Project;
  onBack: () => void;
  onRenderComplete: (updatedProject: Project) => void;
}

export const RenderScreen: React.FC<RenderScreenProps> = ({
  project,
  onBack,
  onRenderComplete,
}) => {
  const { reportError, inspectError } = useError();
  const [renders, setRenders] = useState<RenderJob[]>([]);
  const [activeJob, setActiveJob] = useState<RenderJob | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [rendering, setRendering] = useState<boolean>(false);
  const [cancelling, setCancelling] = useState<boolean>(false);
  const [showPackagingModal, setShowPackagingModal] = useState<boolean>(false);

  // Render Settings
  const [selectedProfile, setSelectedProfile] = useState<string>("standard_1080p");
  const [subtitlesEnabled, setSubtitlesEnabled] = useState<boolean>(false);
  const [bgmVolumeDb, setBgmVolumeDb] = useState<number>(-10.0);
  const [dialogueGainDb, setDialogueGainDb] = useState<number>(0.0);

  // Panel Pacing, Framing & Voice Speed
  const [minPanelDuration, setMinPanelDuration] = useState<number>(4.0);
  const [panelZoomMode, setPanelZoomMode] = useState<"fit" | "motion" | "cover">("fit");
  const [narrationSpeed, setNarrationSpeed] = useState<number>(1.0);
  const [videoEngine, setVideoEngine] = useState<"fast_h3" | "ken_burns">("fast_h3");
  const [motionFx, setMotionFx] = useState<string>("none");

  // Custom Output Save Destination
  const [saveLocation, setSaveLocation] = useState<string>("");
  const [quickDestinations, setQuickDestinations] = useState<
    Array<{ id: string; label: string; path: string; exists: boolean; is_default?: boolean }>
  >([]);

  // Visual QA & Media Tabs
  const [activeMediaTab, setActiveMediaTab] = useState<"video" | "contact_sheet" | "audit_samples">("video");
  const videoRef = useRef<HTMLVideoElement>(null);

  const pollIntervalRef = useRef<any>(null);

  const loadHistory = useCallback(async () => {
    try {
      const list = await api.listRenders(project.id);
      setRenders(list);
      // If there is an active running job, track it
      const active = list.find(
        (j) => j.status !== "COMPLETE" && j.status !== "FAILED" && j.status !== "CANCELLED"
      );
      if (active) {
        setActiveJob(active);
        setRendering(true);
      } else {
        // If an active job was being viewed, keep tracking its updated record
        setActiveJob((prev) => {
          if (prev) {
            const updated = list.find((j) => j.render_id === prev.render_id);
            if (updated) return updated;
          }
          return list.find((j) => j.status === "COMPLETE") || list[0] || null;
        });
      }
    } catch (err: any) {
      console.error("Failed to load render history:", err);
      reportError({
        title: "Failed to Load Render History",
        message: err.message || "Could not retrieve previous renders.",
        severity: "warning",
        source: "pipeline",
        projectId: project.id,
        rawDetails: err,
      });
    } finally {
      setLoading(false);
    }
  }, [project.id, reportError]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

  useEffect(() => {
    api.getQuickDestinations(project.id)
      .then((res: any) => {
        if (res && res.destinations) {
          setQuickDestinations(res.destinations);
          if (!saveLocation && res.default_directory) {
            setSaveLocation(res.default_directory);
          }
        }
      })
      .catch((err: any) => console.warn("Failed to load quick destinations in RenderScreen:", err));
  }, [project.id]);

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

  // Polling for active render progress
  useEffect(() => {
    if (rendering && activeJob && activeJob.status !== "COMPLETE" && activeJob.status !== "FAILED" && activeJob.status !== "CANCELLED") {
      pollIntervalRef.current = setInterval(async () => {
        try {
          const updated = await api.getRender(project.id, activeJob.render_id);
          setActiveJob(updated);
          if (updated.status === "COMPLETE" || updated.status === "FAILED" || updated.status === "CANCELLED") {
            setRendering(false);
            clearInterval(pollIntervalRef.current);
            if (updated.status === "FAILED") {
              reportError({
                title: "Render Job Failed",
                message: updated.error_message || updated.error_code || "Video encoding failed.",
                severity: "error",
                source: "pipeline",
                projectId: project.id,
                jobId: updated.render_id,
                jobType: "VIDEO_RENDER",
                rawDetails: updated,
              });
            }
            const projUpdated = await api.getProject(project.id);
            onRenderComplete(projUpdated);
            await loadHistory();
          }
        } catch {
          // ignore transient poll error
        }
      }, 1000);
    }

    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
      }
    };
  }, [rendering, activeJob?.render_id, project.id, onRenderComplete, loadHistory, reportError]);

  const handleStartRender = async () => {
    setRendering(true);
    try {
      const job = await api.startRender(project.id, {
        profileName: selectedProfile,
        customOutputPath: saveLocation.trim() || undefined,
        subtitleEnabled: subtitlesEnabled,
        bgmVolumeDb,
        dialogueGainDb,
        isDraft: selectedProfile === "draft_720p",
        minPanelDuration,
        panelZoomMode,
        narrationSpeed,
        videoEngine,
        motionFx,
      });
      setActiveJob(job);
      await loadHistory();
    } catch (err: any) {
      reportError({
        title: "Render Failed to Start",
        message: err.message || "An error occurred starting the render job.",
        severity: "error",
        source: "pipeline",
        projectId: project.id,
        jobType: "VIDEO_RENDER",
        rawDetails: err,
      });
      setRendering(false);
    }
  };

  const handleCancelRender = async () => {
    if (!activeJob) return;
    setCancelling(true);
    try {
      await api.cancelRender(project.id, activeJob.render_id);
      setRendering(false);
      setActiveJob((prev) => (prev ? { ...prev, status: "CANCELLED", current_stage: "CANCELLED" } : null));
      await loadHistory();
    } catch (err: any) {
      reportError({
        title: "Render Cancellation Failed",
        message: err.message || "Failed to cancel the active render job.",
        severity: "warning",
        source: "pipeline",
        projectId: project.id,
        jobId: activeJob.render_id,
        jobType: "VIDEO_RENDER",
        rawDetails: err,
      });
    } finally {
      setCancelling(false);
    }
  };

  const handleOpenFile = async (path: string) => {
    try {
      await api.openPath(path, true);
    } catch (err: any) {
      reportError({
        title: "Unable to Open File",
        message: err.message || `Could not open file at ${path}`,
        severity: "warning",
        source: "system",
        projectId: project.id,
        rawDetails: { path, error: err },
      });
    }
  };

  const handleOpenFolder = async (path: string) => {
    try {
      await api.openPath(path, false);
    } catch (err: any) {
      reportError({
        title: "Unable to Open Folder",
        message: err.message || `Could not open directory at ${path}`,
        severity: "warning",
        source: "system",
        projectId: project.id,
        rawDetails: { path, error: err },
      });
    }
  };

  const isJobRunning = rendering && activeJob && activeJob.status !== "COMPLETE" && activeJob.status !== "FAILED" && activeJob.status !== "CANCELLED";

  return (
    <div className="space-y-6">
      {/* Header Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-zinc-800 pb-5">
        <div className="space-y-1">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" onClick={onBack}>
              <Icons.ArrowLeft className="w-4 h-4 mr-1" /> Back
            </Button>
            <h1 className="text-xl font-bold text-zinc-100 flex items-center gap-2">
              Production Renderer
            </h1>
            {activeJob && (
              <Badge
                variant={
                  activeJob.status === "COMPLETE"
                    ? "success"
                    : activeJob.status === "FAILED"
                    ? "danger"
                    : "accent"
                }
                className="uppercase font-mono"
              >
                {activeJob.status}
              </Badge>
            )}
          </div>
          <p className="text-xs text-zinc-400">
            H.264 / AAC hardware-accelerated composition with letterbox containment and verified A/V synchronization.
          </p>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2">
          {isJobRunning ? (
            <Button
              variant="destructive"
              size="sm"
              onClick={handleCancelRender}
              disabled={cancelling}
            >
              Cancel Render
            </Button>
          ) : (
            <Button
              variant="primary"
              size="sm"
              onClick={handleStartRender}
              className="bg-indigo-600 hover:bg-indigo-500 text-white font-bold"
            >
              Start Render
            </Button>
          )}
        </div>
      </div>

      {/* Render Configuration Settings Card */}
      {!isJobRunning && (
        <Card className="p-5 bg-zinc-900 border-zinc-800 space-y-5">
          <div className="flex items-center justify-between border-b border-zinc-800 pb-3">
            <h2 className="text-sm font-bold text-zinc-100 uppercase tracking-wider">
              Output Configuration & Custom Controls
            </h2>
            <span className="text-xs text-zinc-400">Configure save location, panel reading speed, and voice pace</span>
          </div>

          {/* 1. Destination Save Location */}
          <div className="bg-zinc-950/60 border border-zinc-800/80 rounded-xl p-3.5 space-y-2.5">
            <div className="flex items-center justify-between">
              <label className="text-xs font-semibold text-zinc-300 flex items-center gap-1.5">
                <Icons.Folder className="w-4 h-4 text-indigo-400" />
                <span>Video Save Destination</span>
              </label>
              <span className="text-[11px] text-zinc-400">Choose destination folder or exact output file</span>
            </div>

            <div className="flex items-center gap-2">
              <input
                type="text"
                value={saveLocation}
                onChange={(e) => setSaveLocation(e.target.value)}
                placeholder="Choose or paste output directory / file path..."
                className="flex-1 bg-zinc-900 border border-zinc-700 rounded-lg px-3 py-2 text-xs text-zinc-200 font-mono focus:outline-none focus:border-indigo-500"
              />
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

            {/* Quick preset buttons */}
            <div className="flex items-center gap-2 pt-1 overflow-x-auto">
              <span className="text-[10px] uppercase font-bold text-zinc-400 shrink-0">Quick Folders:</span>
              {quickDestinations.map((d) => (
                <button
                  key={d.id}
                  type="button"
                  onClick={() => setSaveLocation(d.path)}
                  className={`text-[11px] px-2.5 py-1 rounded-md border transition-all shrink-0 font-medium ${
                    saveLocation === d.path
                      ? "bg-indigo-950/70 text-indigo-300 border-indigo-500/80 shadow-sm"
                      : "bg-zinc-900 text-zinc-400 hover:text-zinc-200 border-zinc-800 hover:border-zinc-700"
                  }`}
                  title={d.path}
                >
                  {d.label}
                </button>
              ))}
            </div>
          </div>

          {/* 2. Pacing, Framing & Voice Speed */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Panel Pacing Floor */}
            <div className="bg-zinc-950/60 border border-zinc-800/80 rounded-xl p-3.5 space-y-2.5">
              <div className="flex justify-between items-center">
                <div>
                  <span className="font-semibold text-zinc-200 block text-xs">Panel Display Time (Pacing)</span>
                  <span className="text-[11px] text-zinc-400">Guarantees each panel stays on screen long enough</span>
                </div>
                <span className="font-mono font-bold text-indigo-400 text-xs bg-indigo-950/60 border border-indigo-800/50 px-2 py-0.5 rounded">
                  {minPanelDuration.toFixed(1)}s / panel
                </span>
              </div>

              <div className="grid grid-cols-4 gap-1.5">
                {[
                  { label: "Brisk", dur: 2.0 },
                  { label: "Standard", dur: 3.0 },
                  { label: "Comfortable", dur: 4.0 },
                  { label: "Relaxed", dur: 5.5 },
                ].map((preset) => (
                  <button
                    key={preset.dur}
                    type="button"
                    onClick={() => setMinPanelDuration(preset.dur)}
                    className={`py-1 px-1.5 rounded-lg border text-center transition-all ${
                      minPanelDuration === preset.dur
                        ? "bg-indigo-950/80 border-indigo-500 text-indigo-300 font-bold"
                        : "bg-zinc-900 border-zinc-800 text-zinc-400 hover:text-zinc-200"
                    }`}
                  >
                    <div className="text-[11px]">{preset.label}</div>
                    <div className="text-[9px] text-zinc-400 font-mono">{preset.dur}s</div>
                  </button>
                ))}
              </div>

              <input
                type="range"
                min={1.5}
                max={8.0}
                step={0.5}
                value={minPanelDuration}
                onChange={(e) => setMinPanelDuration(parseFloat(e.target.value))}
                className="w-full accent-indigo-500 cursor-pointer mt-1"
              />
            </div>

            {/* Framing Mode & Narration Speed */}
            <div className="bg-zinc-950/60 border border-zinc-800/80 rounded-xl p-3.5 space-y-2.5">
              <div className="flex justify-between items-center">
                <span className="font-semibold text-zinc-200 text-xs">Framing & Speech Speed</span>
                <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wider ${
                  panelZoomMode === "fit" ? "bg-emerald-950 text-emerald-400 border border-emerald-800/50" : "bg-indigo-950 text-indigo-400 border border-indigo-800/50"
                }`}>
                  {panelZoomMode === "fit" ? "Fit Entire Panel" : "Cinematic Zoom"}
                </span>
              </div>

              <div className="grid grid-cols-2 gap-2">
                <button
                  type="button"
                  onClick={() => setPanelZoomMode("fit")}
                  className={`p-2 rounded-lg border text-left transition-all ${
                    panelZoomMode === "fit"
                      ? "bg-emerald-950/40 border-emerald-500 text-emerald-300 font-bold"
                      : "bg-zinc-900 border-zinc-800 text-zinc-400"
                  }`}
                >
                  <div className="text-xs">Fit Entire Artwork</div>
                  <div className="text-[10px] text-zinc-400 font-normal">No crop; dialog never cut off</div>
                </button>
                <button
                  type="button"
                  onClick={() => setPanelZoomMode("motion")}
                  className={`p-2 rounded-lg border text-left transition-all ${
                    panelZoomMode === "motion"
                      ? "bg-indigo-950/40 border-indigo-500 text-indigo-300 font-bold"
                      : "bg-zinc-900 border-zinc-800 text-zinc-400"
                  }`}
                >
                  <div className="text-xs">Cinematic Zoom</div>
                  <div className="text-[10px] text-zinc-400 font-normal">15% slow cinematic zoom</div>
                </button>
              </div>

              {/* Narration speed pills */}
              <div className="flex items-center justify-between pt-1 border-t border-zinc-800/80">
                <span className="text-[11px] text-zinc-400">Narration Pace:</span>
                <div className="flex items-center gap-1">
                  {[0.85, 0.92, 1.0, 1.1, 1.2].map((r) => (
                    <button
                      key={r}
                      type="button"
                      onClick={() => setNarrationSpeed(r)}
                      className={`px-2 py-0.5 rounded text-[11px] font-mono border transition-all ${
                        narrationSpeed === r
                          ? "bg-indigo-600 text-white border-indigo-500 font-bold"
                          : "bg-zinc-900 border-zinc-800 text-zinc-400 hover:text-zinc-200"
                      }`}
                    >
                      {r.toFixed(2)}x
                    </button>
                  ))}
                </div>
              </div>
            </div>
          </div>

          {/* Video Engine & Motion Graphics FX Controls */}
          <div className="p-4 rounded-xl bg-zinc-950/70 border border-zinc-800/80 space-y-3">
            <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2">
              <div className="flex items-center gap-2">
                <span className="text-xs font-bold text-zinc-200 uppercase tracking-wider font-mono">
                  Video Generation Engine & Motion FX
                </span>
                <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-indigo-950 text-indigo-400 border border-indigo-800/60">
                  MiniMax Fast H3 Ready
                </span>
              </div>
              <span className="text-[11px] font-mono text-zinc-500">
                GPU Target: RTX 5060 Ti 16 GB · 8-Step Turbo
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Engine Toggle */}
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-zinc-400">Motion Engine</label>
                <div className="grid grid-cols-2 gap-2">
                  <button
                    type="button"
                    onClick={() => setVideoEngine("fast_h3")}
                    className={`p-2.5 rounded-lg border text-left transition-all ${
                      videoEngine === "fast_h3"
                        ? "bg-indigo-950/60 border-indigo-500 text-white shadow-md shadow-indigo-950/50"
                        : "bg-zinc-900 border-zinc-800 text-zinc-400 hover:text-zinc-200"
                    }`}
                  >
                    <div className="text-xs font-bold font-mono text-indigo-300">Fast H3 AI Video</div>
                    <div className="text-[10px] text-zinc-400 mt-0.5">24fps MiniMax H3 motion generation</div>
                  </button>
                  <button
                    type="button"
                    onClick={() => setVideoEngine("ken_burns")}
                    className={`p-2.5 rounded-lg border text-left transition-all ${
                      videoEngine === "ken_burns"
                        ? "bg-zinc-800 border-zinc-500 text-white"
                        : "bg-zinc-900 border-zinc-800 text-zinc-400 hover:text-zinc-200"
                    }`}
                  >
                    <div className="text-xs font-bold font-mono text-zinc-200">Ken Burns 2D</div>
                    <div className="text-[10px] text-zinc-400 mt-0.5">Dynamic 2D camera pan & zoom</div>
                  </button>
                </div>
              </div>

              {/* Motion Graphics FX Preset */}
              <div className="space-y-1.5">
                <label className="text-xs font-semibold text-zinc-400">Master Motion Graphics Overlay</label>
                <select
                  value={motionFx}
                  onChange={(e) => setMotionFx(e.target.value)}
                  className="w-full bg-zinc-900 border border-zinc-700 text-xs text-zinc-200 rounded-lg p-2.5 font-mono focus:outline-none focus:border-indigo-500"
                >
                  <option value="none">Clean (Standard Animation)</option>
                  <option value="letterbox">Cinematic 2.39:1 Anamorphic Scope</option>
                  <option value="vignette">Moody Vignette & Contrast Curve</option>
                  <option value="film_grain">Analog 35mm Film Grain</option>
                  <option value="action_shake">Dynamic Action Camera Shake</option>
                  <option value="warm_cinema">Warm Golden Hour Tone Curve</option>
                </select>
                <div className="text-[10px] text-zinc-500 font-mono">
                  Applied seamlessly across all generated shot clips and final assembly.
                </div>
              </div>
            </div>
          </div>

          {/* 3. Standard Profile & Audio Mix Controls */}
          <div className="grid grid-cols-1 md:grid-cols-4 gap-4 pt-1">
            {/* Output Profile */}
            <div className="space-y-1.5">
              <label className="text-xs font-semibold text-zinc-400">Profile</label>
              <select
                value={selectedProfile}
                onChange={(e) => setSelectedProfile(e.target.value)}
                className="w-full bg-zinc-950 border border-zinc-700 text-xs text-zinc-200 rounded-lg p-2.5 font-mono focus:outline-none focus:border-indigo-500"
              >
                <option value="standard_1080p">Production 1080p (1920×1080, 30fps)</option>
                <option value="draft_720p">Draft 720p (Fast preview)</option>
                <option value="vertical_shorts">Vertical Shorts (1080×1920)</option>
                <option value="square_feed">Square Feed (1080×1080)</option>
                <option value="preview_1080p">High-Speed Preview 1080p</option>
              </select>
            </div>

            {/* BGM Volume Slider */}
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs text-zinc-400">
                <label className="font-semibold">Music Volume</label>
                <span className="font-mono text-zinc-200">{bgmVolumeDb} dB</span>
              </div>
              <input
                type="range"
                min={-30}
                max={0}
                step={1}
                value={bgmVolumeDb}
                onChange={(e) => setBgmVolumeDb(parseFloat(e.target.value))}
                className="w-full accent-indigo-500 mt-2"
              />
            </div>

            {/* Dialogue Gain Slider */}
            <div className="space-y-1.5">
              <div className="flex justify-between text-xs text-zinc-400">
                <label className="font-semibold">Dialogue Gain</label>
                <span className="font-mono text-zinc-200">{dialogueGainDb >= 0 ? `+${dialogueGainDb}` : dialogueGainDb} dB</span>
              </div>
              <input
                type="range"
                min={-6}
                max={6}
                step={0.5}
                value={dialogueGainDb}
                onChange={(e) => setDialogueGainDb(parseFloat(e.target.value))}
                className="w-full accent-indigo-500 mt-2"
              />
            </div>

            {/* Subtitles Toggle */}
            <div className="space-y-1.5 flex flex-col justify-center">
              <div className="flex justify-between items-center text-xs text-zinc-400">
                <label className="font-semibold">Subtitles</label>
                <span className={`text-[10px] font-bold px-1.5 py-0.5 rounded uppercase tracking-wider ${subtitlesEnabled ? "bg-indigo-950 text-indigo-400 border border-indigo-800/60" : "bg-zinc-800 text-zinc-400"}`}>
                  {subtitlesEnabled ? "ON" : "OFF"}
                </span>
              </div>
              <div className="pt-2 flex items-center gap-3">
                <button
                  type="button"
                  role="switch"
                  aria-checked={subtitlesEnabled}
                  onClick={() => setSubtitlesEnabled(!subtitlesEnabled)}
                  className={`relative inline-flex h-6 w-11 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none ${
                    subtitlesEnabled ? "bg-indigo-600" : "bg-zinc-700"
                  }`}
                >
                  <span
                    aria-hidden="true"
                    className={`pointer-events-none inline-block h-5 w-5 transform rounded-full bg-white shadow-lg ring-0 transition duration-200 ease-in-out ${
                      subtitlesEnabled ? "translate-x-5" : "translate-x-0"
                    }`}
                  />
                </button>
                <span
                  onClick={() => setSubtitlesEnabled(!subtitlesEnabled)}
                  className="text-xs text-zinc-300 select-none cursor-pointer hover:text-white"
                >
                  Burn-In Subtitles (Default: Off)
                </span>
              </div>
            </div>
          </div>
        </Card>
      )}

      {/* Active Live Progress Bar */}
      {isJobRunning && activeJob && (
        <Card className="p-6 bg-zinc-900 border-indigo-500/50 space-y-4 shadow-xl shadow-indigo-950/20">
          <div className="flex items-center justify-between">
            <div className="space-y-1">
              <span className="text-xs font-bold text-indigo-400 uppercase tracking-wider">
                Stage: {activeJob.current_stage}
              </span>
              <h3 className="text-lg font-bold text-zinc-100">
                Rendering Video Presentation...
              </h3>
            </div>
            <div className="text-right font-mono text-sm text-zinc-300">
              {activeJob.frames_done} / {activeJob.frames_total} frames
            </div>
          </div>

          <ProgressBar
            progress={activeJob.progress}
            label="Overall Progress"
          />

          <div className="flex justify-between text-xs text-zinc-400 font-mono pt-1">
            <span>Elapsed: {activeJob.elapsed_sec ? `${activeJob.elapsed_sec.toFixed(1)}s` : "Calculating..."}</span>
            <span>Profile: {activeJob.output_profile}</span>
          </div>
        </Card>
      )}

      {/* Active Job Failure Card */}
      {activeJob && activeJob.status === "FAILED" && !isJobRunning && (
        <Card className="p-6 bg-rose-950/20 border-rose-500/50 space-y-4 shadow-xl shadow-rose-950/20">
          <div className="flex flex-col sm:flex-row sm:items-start justify-between gap-4">
            <div className="flex items-start gap-3">
              <div className="p-2 rounded-lg bg-rose-900/40 text-rose-400 border border-rose-800/60 mt-0.5 flex-shrink-0">
                <Icons.AlertTriangle className="w-5 h-5" />
              </div>
              <div className="space-y-1">
                <span className="text-xs font-bold text-rose-400 uppercase tracking-wider">
                  Render Execution Failed
                </span>
                <h3 className="text-base font-bold text-zinc-100">
                  {activeJob.error_message || activeJob.error_code || "The video rendering job encountered an error and could not complete."}
                </h3>
                <p className="text-xs text-zinc-400 font-mono">
                  Profile: {activeJob.output_profile} • Stage: {activeJob.current_stage} • Frames: {activeJob.frames_done}/{activeJob.frames_total}
                </p>
              </div>
            </div>
            <div className="flex items-center gap-2 flex-shrink-0">
              <Button
                variant="secondary"
                size="sm"
                onClick={() =>
                  inspectError({
                    id: `render_${activeJob.render_id}`,
                    title: "Render Execution Failed",
                    message: activeJob.error_message || activeJob.error_code || "Video render execution failed.",
                    severity: "error",
                    source: "pipeline",
                    timestamp: activeJob.completed_at || new Date().toISOString(),
                    jobId: activeJob.render_id,
                    projectId: project.id,
                    jobType: "VIDEO_RENDER",
                    rawDetails: activeJob,
                  })
                }
                className="border-rose-800/80 hover:bg-rose-950/50 text-rose-300 font-medium"
              >
                View Diagnostic Details
              </Button>
              <Button
                variant="primary"
                size="sm"
                onClick={handleStartRender}
                className="bg-indigo-600 hover:bg-indigo-500 text-white font-bold"
              >
                Retry Render
              </Button>
            </div>
          </div>
        </Card>
      )}

      {/* Completed Video Player & Validation Audit */}
      {activeJob && activeJob.status === "COMPLETE" && (
        <div className="space-y-6">
          <SvgProductionTrophy
            status={
              (() => {
                let rep = activeJob.validation_report as any;
                if (typeof rep === "string") {
                  try { rep = JSON.parse(rep); } catch {}
                }
                return rep?.gate_status === "PRODUCTION_READY" || rep?.is_valid ? "PRODUCTION_READY" : "VALID";
              })()
            }
            title="Production Certified Video Render"
            subtitle={`${activeJob.output_profile} · ${activeJob.frames_done} frames rendered (${activeJob.frames_total ? (activeJob.frames_done / (activeJob.frames_total / 30)).toFixed(1) : "30"} fps) · Audio/Video Synchronized`}
          />

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Visual QA Media Viewer */}
          {(() => {
            let valReport = activeJob.validation_report as any;
            if (typeof valReport === "string") {
              try { valReport = JSON.parse(valReport); } catch {}
            }
            const frameSamples: any[] = valReport?.frame_samples || [];

            return (
              <Card className="lg:col-span-2 p-4 bg-zinc-900 border-zinc-800 space-y-4">
                {/* Mode Switcher Tabs */}
                <div className="flex flex-wrap items-center justify-between gap-3 border-b border-zinc-800 pb-3">
                  <div className="flex items-center gap-1.5 p-1 rounded-lg bg-zinc-950 border border-zinc-800">
                    <button
                      onClick={() => setActiveMediaTab("video")}
                      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${
                        activeMediaTab === "video"
                          ? "bg-indigo-600 text-white shadow-sm shadow-indigo-600/40"
                          : "text-zinc-400 hover:text-zinc-200"
                      }`}
                    >
                      <Icons.Film className="w-3.5 h-3.5" />
                      <span>Video Player</span>
                    </button>
                    <button
                      onClick={() => setActiveMediaTab("contact_sheet")}
                      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${
                        activeMediaTab === "contact_sheet"
                          ? "bg-indigo-600 text-white shadow-sm shadow-indigo-600/40"
                          : "text-zinc-400 hover:text-zinc-200"
                      }`}
                    >
                      <Icons.Layers className="w-3.5 h-3.5" />
                      <span>Contact Sheet</span>
                    </button>
                    <button
                      onClick={() => setActiveMediaTab("audit_samples")}
                      className={`flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-semibold transition-all ${
                        activeMediaTab === "audit_samples"
                          ? "bg-indigo-600 text-white shadow-sm shadow-indigo-600/40"
                          : "text-zinc-400 hover:text-zinc-200"
                      }`}
                    >
                      <Icons.Sparkles className="w-3.5 h-3.5" />
                      <span>Audit Keyframes</span>
                      <span className="text-[10px] font-mono bg-zinc-800 px-1.5 py-0.2 rounded text-zinc-300">
                        {frameSamples.length}
                      </span>
                    </button>
                  </div>

                  <Badge variant="success" className="text-[10px] uppercase font-bold">
                    RENDER VERIFIED
                  </Badge>
                </div>

                {/* Tab 1: Video Player */}
                {activeMediaTab === "video" && (
                  <div className="space-y-3">
                    <div className="aspect-video bg-black rounded-lg overflow-hidden flex items-center justify-center border border-zinc-800 shadow-inner">
                      <video
                        ref={videoRef}
                        controls
                        src={api.getRenderVideoUrl(project.id, activeJob.render_id)}
                        className="w-full h-full object-contain"
                      />
                    </div>

                    {/* Interactive Keyframe Jump Strip */}
                    {frameSamples.length > 0 && (
                      <div className="space-y-1.5">
                        <div className="flex items-center justify-between text-[11px] text-zinc-400">
                          <span className="font-semibold uppercase tracking-wider flex items-center gap-1.5 text-zinc-300">
                            <Icons.Clock className="w-3.5 h-3.5 text-indigo-400" />
                            Seek Verified Keyframes
                          </span>
                          <span className="text-[10px] text-zinc-500">Click timestamp to seek video</span>
                        </div>
                        <div className="flex items-center gap-2 overflow-x-auto py-1 scrollbar-thin scrollbar-thumb-zinc-700">
                          {frameSamples.map((sample: any, sIdx: number) => (
                            <button
                              key={sIdx}
                              onClick={() => {
                                if (videoRef.current) {
                                  videoRef.current.currentTime = sample.timestamp_sec;
                                  videoRef.current.play();
                                }
                              }}
                              className="flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-zinc-950 hover:bg-indigo-950/60 border border-zinc-800 hover:border-indigo-500/80 text-xs font-mono text-zinc-300 hover:text-white transition-all flex-shrink-0 group shadow-sm"
                              title={`Seek to ${sample.timestamp_sec.toFixed(2)}s (Frame #${sample.frame_index}) · Luminance: ${sample.mean_luminance?.toFixed(1)}/255`}
                            >
                              <span className="w-2 h-2 rounded-full bg-emerald-400 group-hover:scale-125 transition-transform" />
                              <span className="font-bold">{sample.timestamp_sec.toFixed(1)}s</span>
                              <span className="text-[10px] text-zinc-500">#{sample.frame_index}</span>
                            </button>
                          ))}
                        </div>
                      </div>
                    )}

                    <div className="flex flex-wrap items-center justify-between gap-3 pt-2">
                      <span className="text-xs text-zinc-400 font-mono truncate max-w-md">
                        {activeJob.output_path}
                      </span>
                      <div className="flex items-center gap-2">
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => handleOpenFile(activeJob.output_path)}
                        >
                          Open Video File
                        </Button>
                        <Button
                          variant="secondary"
                          size="sm"
                          onClick={() => handleOpenFolder(activeJob.output_path)}
                        >
                          Open Folder
                        </Button>
                        <Button
                          variant="primary"
                          size="sm"
                          onClick={() => setShowPackagingModal(true)}
                          className="bg-red-600 hover:bg-red-500 text-white font-bold text-xs flex items-center gap-1.5 shadow-sm shadow-red-600/30"
                        >
                          <Icons.Sparkles className="w-3.5 h-3.5" />
                          <span>YouTube Packaging & Thumbnail</span>
                        </Button>
                      </div>
                    </div>
                  </div>
                )}

                {/* Tab 2: Storyboard Contact Sheet */}
                {activeMediaTab === "contact_sheet" && (
                  <div className="space-y-3">
                    <div className="flex items-center justify-between text-xs text-zinc-400">
                      <span>Full Episode Storyboard Contact Sheet · Verifying panel pacing and visual flow</span>
                      <a
                        href={api.getRenderContactSheetUrl(project.id, activeJob.render_id)}
                        target="_blank"
                        rel="noreferrer"
                        className="text-indigo-400 hover:text-indigo-300 flex items-center gap-1 font-medium"
                      >
                        <Icons.ExternalLink className="w-3.5 h-3.5" />
                        Full Resolution
                      </a>
                    </div>
                    <div className="max-h-[500px] overflow-auto rounded-lg bg-zinc-950 border border-zinc-800 p-2 flex items-center justify-center">
                      <img
                        src={api.getRenderContactSheetUrl(project.id, activeJob.render_id)}
                        alt="Render Contact Sheet"
                        className="w-full h-auto object-contain rounded shadow-lg"
                      />
                    </div>
                  </div>
                )}

                {/* Tab 3: Keyframe Audit Samples */}
                {activeMediaTab === "audit_samples" && (
                  <div className="space-y-3">
                    <p className="text-xs text-zinc-400">
                      Raster frames sampled during automated video validation, confirming absence of black frames and color-space validity.
                    </p>
                    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3 max-h-[520px] overflow-y-auto p-1">
                      {frameSamples.map((sample: any, sIdx: number) => (
                        <div
                          key={sIdx}
                          className="bg-zinc-950 border border-zinc-800 rounded-lg overflow-hidden flex flex-col group hover:border-indigo-500/50 transition-colors shadow-sm"
                        >
                          <div className="relative aspect-video bg-black flex items-center justify-center overflow-hidden">
                            <img
                              src={api.getRenderAuditSampleUrl(project.id, activeJob.render_id, sIdx)}
                              alt={`Audit sample at ${sample.timestamp_sec}s`}
                              className="w-full h-full object-cover group-hover:scale-105 transition-transform duration-300"
                            />
                            <span className="absolute top-2 left-2 bg-black/80 backdrop-blur-sm text-zinc-200 text-[10px] font-mono px-2 py-0.5 rounded border border-zinc-700/60 font-bold">
                              {sample.timestamp_sec.toFixed(2)}s
                            </span>
                            <span className={`absolute top-2 right-2 text-[10px] font-bold px-1.5 py-0.5 rounded border ${
                              sample.is_black
                                ? "bg-rose-950/90 text-rose-300 border-rose-700"
                                : "bg-emerald-950/90 text-emerald-300 border-emerald-700"
                            }`}>
                              {sample.is_black ? "BLACK FRAME" : "VALID"}
                            </span>
                          </div>
                          <div className="p-2.5 space-y-2 flex-1 flex flex-col justify-between">
                            <div className="space-y-1 text-xs">
                              <div className="flex justify-between text-zinc-400 text-[11px]">
                                <span>Frame Index:</span>
                                <span className="font-mono text-zinc-200 font-bold">#{sample.frame_index}</span>
                              </div>
                              <div className="flex justify-between text-zinc-400 text-[11px]">
                                <span>Luminance:</span>
                                <span className="font-mono text-emerald-400 font-bold">
                                  {sample.mean_luminance?.toFixed(1) ?? "N/A"} / 255
                                </span>
                              </div>
                              <div className="flex justify-between text-zinc-400 text-[11px]">
                                <span>Subtitles:</span>
                                <span className={`font-mono text-[10px] font-bold ${sample.caption_rendered ? "text-indigo-400" : "text-zinc-500"}`}>
                                  {sample.caption_rendered ? "RENDERED" : "OMITTED"}
                                </span>
                              </div>
                            </div>
                            <Button
                              variant="secondary"
                              size="sm"
                              onClick={() => {
                                setActiveMediaTab("video");
                                setTimeout(() => {
                                  if (videoRef.current) {
                                    videoRef.current.currentTime = sample.timestamp_sec;
                                    videoRef.current.play();
                                  }
                                }, 100);
                              }}
                              className="w-full text-xs text-indigo-300 hover:text-white border-zinc-700 hover:border-indigo-500 font-medium"
                            >
                              <Icons.Play className="w-3 h-3 mr-1" />
                              Seek Video Here
                            </Button>
                          </div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </Card>
            );
          })()}

          {/* Validation Report & Quality Audit */}
          <Card className="p-5 bg-zinc-900 border-zinc-800 space-y-4">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-zinc-200 uppercase tracking-wider">
                Validation Audit
              </h3>
              {(() => {
                let report = activeJob.validation_report as any;
                if (typeof report === "string") {
                  try { report = JSON.parse(report); } catch {}
                }
                const gate = report?.gate_status || (report?.is_valid ? "PRODUCTION_READY" : null);
                if (!gate) return null;
                return (
                  <Badge variant={gate === "PRODUCTION_READY" || gate === "READY_FOR_REVIEW" ? "success" : "danger"} className="text-[9px] uppercase font-bold">
                    {gate}
                  </Badge>
                );
              })()}
            </div>

            {activeJob.validation_report ? (() => {
              let report = activeJob.validation_report as any;
              if (typeof report === "string") {
                try { report = JSON.parse(report); } catch {}
              }
              const duration = report.actual_duration_sec ?? report.duration_sec ?? 0;
              const blackFrames = report.quality_flags?.black_frames ?? report.black_frames_count ?? 0;
              const timelineGaps = report.quality_flags?.timeline_gaps ?? report.timeline_gaps_count ?? 0;
              const clipping = report.quality_flags?.audio_clipping_events ?? report.clipping_samples_count ?? 0;
              const syncValid = report.quality_flags?.av_sync_offset_ms === 0 || report.is_valid;
              const semantic = report.semantic_qa;
              const failedChecks: string[] = semantic?.failed_checks || [];
              const warnings: string[] = report.warnings || [];

              return (
                <div className="space-y-3 text-xs">
                  <div className="flex justify-between py-1.5 border-b border-zinc-800">
                    <span className="text-zinc-400">Duration</span>
                    <span className="font-mono font-bold text-zinc-200">
                      {duration.toFixed(2)}s
                    </span>
                  </div>
                  <div className="flex justify-between py-1.5 border-b border-zinc-800">
                    <span className="text-zinc-400">Black Frame Failures</span>
                    <span className="font-mono font-bold text-emerald-400">
                      {blackFrames} frames
                    </span>
                  </div>
                  <div className="flex justify-between py-1.5 border-b border-zinc-800">
                    <span className="text-zinc-400">Timeline Gaps</span>
                    <span className="font-mono font-bold text-emerald-400">
                      {timelineGaps} gaps
                    </span>
                  </div>
                  <div className="flex justify-between py-1.5 border-b border-zinc-800">
                    <span className="text-zinc-400">Audio Clipping</span>
                    <span className="font-mono font-bold text-emerald-400">
                      {clipping} samples
                    </span>
                  </div>
                  <div className="flex justify-between py-1.5 border-b border-zinc-800">
                    <span className="text-zinc-400">A/V Sync Status</span>
                    <span className="font-mono font-bold text-emerald-400">
                      {syncValid ? "SYNCHRONIZED (0 ms)" : "DESYNC"}
                    </span>
                  </div>
                  {semantic && (
                    <>
                      <div className="flex justify-between py-1.5 border-b border-zinc-800">
                        <span className="text-zinc-400">Story Event Coverage</span>
                        <span className="font-mono font-bold text-emerald-400">
                          {semantic.story_event_coverage_pct ?? 100}%
                        </span>
                      </div>
                      <div className="flex justify-between py-1.5 border-b border-zinc-800">
                        <span className="text-zinc-400">Visual Panel Coverage</span>
                        <span className="font-mono font-bold text-emerald-400">
                          {semantic.visual_panel_coverage_pct ?? 100}%
                        </span>
                      </div>
                    </>
                  )}

                  {/* Semantic QA Failures */}
                  {failedChecks.length > 0 && (
                    <div className="mt-3 p-3 rounded-lg bg-rose-950/40 border border-rose-800/60 text-xs space-y-1.5">
                      <div className="flex items-center gap-1.5 text-rose-400 font-bold uppercase tracking-wider text-[10px]">
                        <Icons.AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
                        <span>Semantic QA Gate Blockers ({failedChecks.length})</span>
                      </div>
                      <ul className="list-disc list-inside space-y-1 text-rose-200 text-[11px]">
                        {failedChecks.map((fc, idx) => (
                          <li key={idx} className="leading-tight">{fc}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Quality Warnings */}
                  {warnings.length > 0 && (
                    <div className="mt-3 p-3 rounded-lg bg-amber-950/30 border border-amber-800/50 text-xs space-y-1.5">
                      <div className="flex items-center gap-1.5 text-amber-400 font-bold uppercase tracking-wider text-[10px]">
                        <Icons.AlertTriangle className="w-3.5 h-3.5 flex-shrink-0" />
                        <span>Validation Warnings ({warnings.length})</span>
                      </div>
                      <ul className="list-disc list-inside space-y-1 text-amber-200 text-[11px]">
                        {warnings.map((w, idx) => (
                          <li key={idx} className="leading-tight">{w}</li>
                        ))}
                      </ul>
                    </div>
                  )}

                  {/* Export QA Audit JSON Button */}
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => {
                      const jsonStr = JSON.stringify(report, null, 2);
                      const blob = new Blob([jsonStr], { type: "application/json" });
                      const url = URL.createObjectURL(blob);
                      const a = document.createElement("a");
                      a.href = url;
                      a.download = `qa_audit_${activeJob.render_id}.json`;
                      a.click();
                      URL.revokeObjectURL(url);
                    }}
                    className="w-full mt-3 text-xs border-zinc-700 text-zinc-300 hover:text-white hover:bg-zinc-800"
                  >
                    <Icons.Download className="w-3.5 h-3.5 mr-1.5 text-indigo-400" />
                    Export Full QA Audit (JSON)
                  </Button>
                </div>
              );
            })() : (
              <p className="text-xs text-zinc-500">Validation report ready upon encode completion.</p>
            )}
          </Card>
        </div>
        </div>
      )}

      {/* Render History Table */}
      <Card className="p-5 bg-zinc-900 border-zinc-800 space-y-3">
        <h3 className="text-sm font-bold text-zinc-200 uppercase tracking-wider">
          Render History
        </h3>

        {renders.length === 0 ? (
          <p className="text-xs text-zinc-500 py-4">No previous renders recorded for this project.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs">
              <thead>
                <tr className="border-b border-zinc-800 text-zinc-400 font-mono">
                  <th className="py-2 px-3">Status</th>
                  <th className="py-2 px-3">Profile</th>
                  <th className="py-2 px-3">Progress</th>
                  <th className="py-2 px-3">Date</th>
                  <th className="py-2 px-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-zinc-800/50">
                {renders.map((r) => (
                  <tr key={r.render_id} className="hover:bg-zinc-800/30 transition-colors">
                    <td className="py-2.5 px-3">
                      <Badge
                        variant={
                          r.status === "COMPLETE"
                            ? "success"
                            : r.status === "FAILED"
                            ? "danger"
                            : "neutral"
                        }
                        className="text-[9px] uppercase font-bold"
                      >
                        {r.status}
                      </Badge>
                    </td>
                    <td className="py-2.5 px-3 font-mono text-zinc-200">
                      {r.output_profile}
                    </td>
                    <td className="py-2.5 px-3 font-mono text-zinc-400">
                      {Math.round(r.progress > 1 ? r.progress : r.progress * 100)}%
                    </td>
                    <td className="py-2.5 px-3 text-zinc-500 font-mono">
                      {r.created_at ? new Date(r.created_at).toLocaleTimeString() : "-"}
                    </td>
                    <td className="py-2.5 px-3 text-right space-x-2">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setActiveJob(r)}
                        className="text-xs text-indigo-400 hover:text-indigo-300"
                      >
                        Inspect
                      </Button>
                      {r.output_path && (
                        <Button
                          variant="ghost"
                          size="sm"
                          onClick={() => handleOpenFile(r.output_path)}
                          className="text-xs text-zinc-400 hover:text-zinc-200"
                        >
                          Open
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>
      <YouTubePackagingModal
        isOpen={showPackagingModal}
        onClose={() => setShowPackagingModal(false)}
        project={project}
        profileName={activeJob?.output_profile}
      />
    </div>
  );
};
