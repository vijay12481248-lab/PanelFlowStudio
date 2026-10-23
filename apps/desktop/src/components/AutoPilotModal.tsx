import React, { useCallback, useEffect, useRef, useState } from "react";
import { api } from "@panelflow/api-client";
import type { AutoPilotStatusResponse, Project } from "@panelflow/shared-types";
import { Badge, Button, Card, Icons, ProgressBar } from "@panelflow/ui";

const DEFAULT_STAGES = [
  { id: "pages", name: "1. Page Ingest & Normalization", status: "PENDING", progress: 0, message: "Waiting to start...", duration_sec: 0 },
  { id: "panels", name: "2. Panel Segmentation & Ordering", status: "PENDING", progress: 0, message: "Waiting to start...", duration_sec: 0 },
  { id: "ocr", name: "3. Speech Bubble & Text Extraction", status: "PENDING", progress: 0, message: "Waiting to start...", duration_sec: 0 },
  { id: "story", name: "4. Narrative & Scene Breakdown", status: "PENDING", progress: 0, message: "Waiting to start...", duration_sec: 0 },
  { id: "script", name: "5. Script & Dialogue Adaptation", status: "PENDING", progress: 0, message: "Waiting to start...", duration_sec: 0 },
  { id: "audio", name: "6. Master Audio & Voice Synthesis", status: "PENDING", progress: 0, message: "Waiting to start...", duration_sec: 0 },
  { id: "motion", name: "7. Motion Director Keyframing", status: "PENDING", progress: 0, message: "Waiting to start...", duration_sec: 0 },
  { id: "render", name: "8. Production Video Rendering (MP4)", status: "PENDING", progress: 0, message: "Waiting to start...", duration_sec: 0 },
  { id: "packaging", name: "9. YouTube Packaging & AI Thumbnail", status: "PENDING", progress: 0, message: "Waiting to start...", duration_sec: 0 },
];

export interface AutoPilotModalProps {
  isOpen: boolean;
  onClose: () => void;
  project: Project;
  onOpenPackaging?: () => void;
  onOpenRenderScreen?: () => void;
}

export const AutoPilotModal: React.FC<AutoPilotModalProps> = ({
  isOpen,
  onClose,
  project,
  onOpenPackaging,
  onOpenRenderScreen,
}) => {
  const [statusData, setStatusData] = useState<AutoPilotStatusResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [running, setRunning] = useState<boolean>(false);
  const [cancelling, setCancelling] = useState<boolean>(false);

  // Configuration options
  const [targetProfile, setTargetProfile] = useState<string>("standard_1080p");
  const [skipExisting, setSkipExisting] = useState<boolean>(true);
  const [enableThumbnails, setEnableThumbnails] = useState<boolean>(true);

  const pollIntervalRef = useRef<any>(null);
  const logsEndRef = useRef<HTMLDivElement>(null);

  const pollStatus = useCallback(async () => {
    try {
      const res = await api.getAutoPilotStatus(project.id);
      setStatusData(res);
      setRunning(res.status === "RUNNING");
      if (res.status === "COMPLETED" || res.status === "FAILED" || res.status === "CANCELLED") {
        if (pollIntervalRef.current) {
          clearInterval(pollIntervalRef.current);
          pollIntervalRef.current = null;
        }
      }
    } catch (err) {
      console.warn("Poll autopilot status error:", err);
    } finally {
      setLoading(false);
    }
  }, [project.id]);

  useEffect(() => {
    if (!isOpen) {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
      return;
    }

    pollStatus();
    pollIntervalRef.current = setInterval(pollStatus, 1000);

    return () => {
      if (pollIntervalRef.current) {
        clearInterval(pollIntervalRef.current);
        pollIntervalRef.current = null;
      }
    };
  }, [isOpen, pollStatus]);

  // Auto-scroll logs
  useEffect(() => {
    if (logsEndRef.current) {
      logsEndRef.current.scrollIntoView({ behavior: "smooth" });
    }
  }, [statusData?.logs]);

  if (!isOpen) return null;

  const handleStartRun = async () => {
    setLoading(true);
    try {
      const res = await api.startAutoPilot(project.id, {
        target_profile: targetProfile,
        skip_existing_stages: skipExisting,
        enable_thumbnails: enableThumbnails,
      });
      setStatusData(res);
      setRunning(true);
      if (!pollIntervalRef.current) {
        pollIntervalRef.current = setInterval(pollStatus, 1000);
      }
    } catch (err: any) {
      console.error("Failed to start Auto-Pilot:", err);
    } finally {
      setLoading(false);
    }
  };

  const handleCancelRun = async () => {
    setCancelling(true);
    try {
      await api.cancelAutoPilot(project.id);
      await pollStatus();
    } catch (err) {
      console.warn("Cancel Auto-Pilot error:", err);
    } finally {
      setCancelling(false);
      setRunning(false);
    }
  };

  const isCompleted = statusData?.status === "COMPLETED";
  const isFailed = statusData?.status === "FAILED";
  const progressPercent = Math.round((statusData?.overall_progress ?? 0) * 100);

  return (
    <div
      className="fixed inset-0 z-50 bg-black/85 backdrop-blur-md flex items-center justify-center p-4 animate-in fade-in duration-200"
      role="dialog"
      aria-modal="true"
      aria-label="PanelFlow Auto-Pilot Orchestrator"
    >
      <div className="bg-zinc-950 border border-zinc-800 rounded-2xl w-full max-w-5xl max-h-[92vh] flex flex-col shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b border-zinc-800/80 bg-zinc-900/60 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 via-purple-600 to-pink-600 flex items-center justify-center text-white shadow-lg shadow-indigo-600/30">
              <Icons.Zap className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-zinc-100 flex items-center gap-2">
                1-Click End-to-End Pipeline Auto-Pilot
                <Badge variant="accent" className="text-[10px]">AUTONOMOUS</Badge>
              </h2>
              <p className="text-xs text-zinc-400">
                Executes all 9 stages from raw pages to certified MP4 video & ComfyUI thumbnail for <span className="text-zinc-200 font-medium">{project.title}</span>
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg flex items-center justify-center text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 transition-colors"
            aria-label="Close dialog"
          >
            <Icons.X className="w-4 h-4" />
          </button>
        </div>

        {/* Configuration Bar */}
        <div className="px-6 py-3 border-b border-zinc-800/80 bg-zinc-900/40 flex flex-wrap items-center justify-between gap-4 text-xs">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <span className="text-zinc-400 font-medium">Output Profile:</span>
              <select
                value={targetProfile}
                onChange={(e) => setTargetProfile(e.target.value)}
                disabled={running}
                className="bg-zinc-950 border border-zinc-700 rounded-md px-2.5 py-1 text-xs text-zinc-200"
              >
                <option value="standard_1080p">1080p Landscape (16:9)</option>
                <option value="vertical_shorts">1080p Vertical Shorts (9:16)</option>
                <option value="square_feed">Square Feed (1:1)</option>
              </select>
            </div>

            <label className="flex items-center gap-1.5 text-zinc-300 cursor-pointer">
              <input
                type="checkbox"
                checked={skipExisting}
                onChange={(e) => setSkipExisting(e.target.checked)}
                disabled={running}
                className="rounded border-zinc-700 bg-zinc-900 text-indigo-500 focus:ring-0"
              />
              <span>Smart Skip (Preserve existing verified stages)</span>
            </label>

            <label className="flex items-center gap-1.5 text-zinc-300 cursor-pointer">
              <input
                type="checkbox"
                checked={enableThumbnails}
                onChange={(e) => setEnableThumbnails(e.target.checked)}
                disabled={running}
                className="rounded border-zinc-700 bg-zinc-900 text-indigo-500 focus:ring-0"
              />
              <span>Generate ComfyUI Thumbnail & YouTube Packaging</span>
            </label>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-[11px] text-zinc-400 font-mono">
              Status: <span className="font-bold text-zinc-200">{statusData?.status || "READY"}</span>
            </span>
          </div>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Progress Overview */}
          <div className="bg-zinc-900/60 p-4 rounded-xl border border-zinc-800 space-y-2">
            <div className="flex justify-between items-center text-xs">
              <span className="font-bold text-zinc-200 flex items-center gap-2">
                <Icons.Activity className="w-4 h-4 text-indigo-400" />
                Pipeline Orchestration Progress
              </span>
              <span className="font-mono text-indigo-400 font-bold text-sm">{progressPercent}%</span>
            </div>
            <ProgressBar progress={statusData?.overall_progress ?? 0} />
            <div className="flex justify-between text-[11px] text-zinc-400 font-mono">
              <span>Current: {statusData?.current_stage_id ? statusData.current_stage_id.toUpperCase() : "Ready to launch"}</span>
              <span>9 Stages Synchronized</span>
            </div>
          </div>

          {/* Success Banner */}
          {isCompleted && (
            <div className="p-4 bg-gradient-to-r from-emerald-950/40 via-zinc-900 to-indigo-950/40 border border-emerald-600/60 rounded-xl space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-full bg-emerald-500/20 text-emerald-400 flex items-center justify-center">
                    <Icons.CheckCircle className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-zinc-100">End-to-End Pipeline Execution Successful!</h3>
                    <p className="text-xs text-zinc-400">
                      Production video rendered, A/V validated, and YouTube packaging generated.
                    </p>
                  </div>
                </div>
                <Badge variant="success">PRODUCTION READY</Badge>
              </div>

              {statusData?.result?.output_mp4_path && (
                <div className="p-2.5 bg-zinc-950 border border-zinc-800 rounded-lg text-xs font-mono text-zinc-300 truncate">
                  Output: {statusData.result.output_mp4_path}
                </div>
              )}

              <div className="flex flex-wrap items-center gap-2 pt-1">
                {onOpenPackaging && (
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={onOpenPackaging}
                    className="bg-indigo-600 hover:bg-indigo-500 text-white font-bold text-xs flex items-center gap-1.5"
                  >
                    <Icons.Sparkles className="w-3.5 h-3.5" />
                    <span>View YouTube Packaging & AI Thumbnail</span>
                  </Button>
                )}
                {onOpenRenderScreen && (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={onOpenRenderScreen}
                    className="text-xs flex items-center gap-1.5 border-zinc-700"
                  >
                    <Icons.Film className="w-3.5 h-3.5" />
                    <span>Open Video Player & Media Samples</span>
                  </Button>
                )}
              </div>
            </div>
          )}

          {/* Error Banner */}
          {isFailed && (
            <div className="p-4 bg-rose-950/40 border border-rose-800 rounded-xl flex items-start gap-3">
              <Icons.XCircle className="w-5 h-5 text-rose-400 shrink-0 mt-0.5" />
              <div className="space-y-1 text-xs">
                <h4 className="font-bold text-rose-300">Pipeline Failed</h4>
                <p className="text-rose-200 font-mono text-[11px]">{statusData?.error}</p>
              </div>
            </div>
          )}

          {/* Main Grid: Stages Checklist (Left) & Console Logs (Right) */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* 9 Stages Checklist (6 cols) */}
            <div className="lg:col-span-6 space-y-2">
              <h3 className="text-xs font-bold text-zinc-200 uppercase tracking-wider mb-2 flex items-center gap-1.5">
                <Icons.Layers className="w-4 h-4 text-indigo-400" />
                Pipeline Stages Execution
              </h3>

              <div className="space-y-2">
                {(statusData?.stages || DEFAULT_STAGES).map((stage) => {
                  const isDone = stage.status === "COMPLETED" || stage.status === "SKIPPED";
                  const isCurrent = stage.status === "RUNNING";
                  const isStageFailed = stage.status === "FAILED";

                  return (
                    <div
                      key={stage.id}
                      className={`p-3 rounded-xl border transition-all ${
                        isCurrent
                          ? "border-indigo-500 bg-indigo-950/20 shadow-md shadow-indigo-600/10"
                          : isDone
                          ? "border-zinc-800/80 bg-zinc-900/40"
                          : isStageFailed
                          ? "border-rose-800 bg-rose-950/20"
                          : "border-zinc-800/50 bg-zinc-950/40 opacity-70"
                      }`}
                    >
                      <div className="flex items-center justify-between text-xs mb-1">
                        <div className="flex items-center gap-2">
                          {isDone ? (
                            <Icons.CheckCircle className="w-4 h-4 text-emerald-400" />
                          ) : isCurrent ? (
                            <Icons.Refresh className="w-4 h-4 text-indigo-400 animate-spin" />
                          ) : isStageFailed ? (
                            <Icons.XCircle className="w-4 h-4 text-rose-400" />
                          ) : (
                            <Icons.Clock className="w-4 h-4 text-zinc-600" />
                          )}
                          <span className={`font-semibold ${isCurrent ? "text-white" : isDone ? "text-zinc-200" : "text-zinc-400"}`}>
                            {stage.name}
                          </span>
                        </div>

                        <div className="flex items-center gap-2">
                          {stage.duration_sec > 0 && (
                            <span className="text-[10px] font-mono text-zinc-500">
                              {stage.duration_sec.toFixed(1)}s
                            </span>
                          )}
                          <span
                            className={`text-[10px] font-mono font-bold uppercase px-1.5 py-0.5 rounded ${
                              isDone
                                ? "bg-emerald-950/80 text-emerald-400 border border-emerald-800/60"
                                : isCurrent
                                ? "bg-indigo-950/80 text-indigo-300 border border-indigo-700/60 animate-pulse"
                                : isStageFailed
                                ? "bg-rose-950 text-rose-400"
                                : "text-zinc-600"
                            }`}
                          >
                            {stage.status}
                          </span>
                        </div>
                      </div>

                      {stage.message && (
                        <p className="text-[11px] text-zinc-400 pl-6 truncate">
                          {stage.message}
                        </p>
                      )}
                    </div>
                  );
                })}
              </div>
            </div>

            {/* Live Terminal / Console Logs (6 cols) */}
            <div className="lg:col-span-6 space-y-2 flex flex-col">
              <div className="flex items-center justify-between text-xs">
                <span className="font-bold text-zinc-200 uppercase tracking-wider flex items-center gap-1.5">
                  <Icons.Cpu className="w-4 h-4 text-indigo-400" />
                  Live Orchestration Console
                </span>
                <span className="text-[10px] font-mono text-zinc-500">
                  {statusData?.logs.length ?? 0} events
                </span>
              </div>

              <div className="flex-1 min-h-[380px] max-h-[460px] bg-black border border-zinc-800 rounded-xl p-3 overflow-y-auto font-mono text-[11px] space-y-1 text-zinc-300 shadow-inner">
                {statusData?.logs && statusData.logs.length > 0 ? (
                  statusData.logs.map((logLine, lIdx) => (
                    <div key={lIdx} className="leading-tight break-all">
                      {logLine.includes("FAILED") || logLine.includes("error") ? (
                        <span className="text-rose-400">{logLine}</span>
                      ) : logLine.includes("completed") || logLine.includes("certified") || logLine.includes("Successful") ? (
                        <span className="text-emerald-400 font-semibold">{logLine}</span>
                      ) : logLine.includes("Starting") || logLine.includes("Stage:") ? (
                        <span className="text-indigo-300">{logLine}</span>
                      ) : (
                        <span className="text-zinc-400">{logLine}</span>
                      )}
                    </div>
                  ))
                ) : (
                  <div className="h-full flex items-center justify-center text-zinc-600">
                    Console idle. Click "Start Auto-Pilot Run" to begin.
                  </div>
                )}
                <div ref={logsEndRef} />
              </div>
            </div>
          </div>
        </div>

        {/* Modal Footer */}
        <div className="px-6 py-4 border-t border-zinc-800/80 bg-zinc-900/60 flex items-center justify-between">
          <div className="text-xs text-zinc-400">
            {running
              ? "Auto-Pilot is executing in the background — you can safely keep this open or close it."
              : isCompleted
              ? "All stages finished. Your motion comic video and thumbnail are ready!"
              : "Ready to automate all 9 pipeline stages."}
          </div>

          <div className="flex items-center gap-2">
            <Button variant="secondary" size="sm" onClick={onClose} className="text-xs">
              {isCompleted ? "Done" : "Close"}
            </Button>

            {running ? (
              <Button
                variant="secondary"
                size="sm"
                onClick={handleCancelRun}
                disabled={cancelling}
                className="text-xs text-rose-400 hover:text-rose-300 border-rose-900/60"
              >
                {cancelling ? "Stopping..." : "Stop Auto-Pilot"}
              </Button>
            ) : (
              <Button
                variant="primary"
                size="sm"
                onClick={handleStartRun}
                disabled={loading}
                className="bg-indigo-600 hover:bg-indigo-500 text-white font-bold px-5 text-xs shadow-md shadow-indigo-600/30 flex items-center gap-1.5"
              >
                <Icons.Zap className="w-4 h-4" />
                <span>{isCompleted ? "Re-Run Auto-Pilot" : "Start Auto-Pilot Run"}</span>
              </Button>
            )}
          </div>
        </div>
      </div>
    </div>
  );
};
