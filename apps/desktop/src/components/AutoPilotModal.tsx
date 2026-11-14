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
  /** Jump to the screen of a pipeline stage id (pages, panels, ocr, story, script, audio, motion, render, packaging). */
  onOpenStage?: (stageId: string) => void;
}

export const AutoPilotModal: React.FC<AutoPilotModalProps> = ({
  isOpen,
  onClose,
  project,
  onOpenPackaging,
  onOpenRenderScreen,
  onOpenStage,
}) => {
  const [statusData, setStatusData] = useState<AutoPilotStatusResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [running, setRunning] = useState<boolean>(false);
  const [cancelling, setCancelling] = useState<boolean>(false);
  const [copiedDiagnostics, setCopiedDiagnostics] = useState<boolean>(false);

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

  // The dialog must be dismissable from the keyboard. Closing never cancels a running pipeline.
  useEffect(() => {
    if (!isOpen) return;
    const onKey = (event: KeyboardEvent) => { if (event.key === "Escape") onClose(); };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [isOpen, onClose]);

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
      <div className="bg-ink border border-edge rounded-2xl w-full max-w-5xl max-h-[92vh] flex flex-col shadow-2xl overflow-hidden">
        {/* Header */}
        <div className="px-6 py-4 border-b border-edge/80 bg-navy/60 flex items-center justify-between">
          <div className="flex items-center gap-3">
            <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-accent via-accent to-accent flex items-center justify-center text-white shadow-lg shadow-accent/30">
              <Icons.Zap className="w-5 h-5" />
            </div>
            <div>
              <h2 className="text-base font-bold text-fg flex items-center gap-2">
                1-Click End-to-End Pipeline Auto-Pilot
                <Badge variant="accent" className="text-[10px]">AUTONOMOUS</Badge>
              </h2>
              <p className="text-xs text-fg-dim">
                Executes all 9 stages from raw pages to certified MP4 video & ComfyUI thumbnail for <span className="text-fg font-medium">{project.title}</span>
              </p>
            </div>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg flex items-center justify-center text-fg-dim hover:text-fg hover:bg-flat transition-colors"
            aria-label="Close dialog"
          >
            <Icons.X className="w-4 h-4" />
          </button>
        </div>

        {/* Configuration Bar */}
        <div className="px-6 py-3 border-b border-edge/80 bg-navy/40 flex flex-wrap items-center justify-between gap-4 text-xs">
          <div className="flex items-center gap-4">
            <div className="flex items-center gap-2">
              <span className="text-fg-dim font-medium">Output Profile:</span>
              <select
                value={targetProfile}
                onChange={(e) => setTargetProfile(e.target.value)}
                disabled={running}
                className="bg-ink border border-edge rounded-md px-2.5 py-1 text-xs text-fg"
              >
                <option value="standard_1080p">1080p Landscape (16:9)</option>
                <option value="vertical_shorts">1080p Vertical Shorts (9:16)</option>
                <option value="square_feed">Square Feed (1:1)</option>
              </select>
            </div>

            <label className="flex items-center gap-1.5 text-fg-dim cursor-pointer">
              <input
                type="checkbox"
                checked={skipExisting}
                onChange={(e) => setSkipExisting(e.target.checked)}
                disabled={running}
                className="rounded border-edge bg-navy text-accent focus:ring-0"
              />
              <span>Smart Skip (Preserve existing verified stages)</span>
            </label>

            <label className="flex items-center gap-1.5 text-fg-dim cursor-pointer">
              <input
                type="checkbox"
                checked={enableThumbnails}
                onChange={(e) => setEnableThumbnails(e.target.checked)}
                disabled={running}
                className="rounded border-edge bg-navy text-accent focus:ring-0"
              />
              <span>Generate ComfyUI Thumbnail & YouTube Packaging</span>
            </label>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-[11px] text-fg-dim font-mono">
              Status: <span className="font-bold text-fg">{statusData?.status || "READY"}</span>
            </span>
          </div>
        </div>

        {/* Content Body */}
        <div className="flex-1 overflow-y-auto p-6 space-y-6">
          {/* Progress Overview */}
          <div className="bg-navy/60 p-4 rounded-xl border border-edge space-y-2">
            <div className="flex justify-between items-center text-xs">
              <span className="font-bold text-fg flex items-center gap-2">
                <Icons.Activity className="w-4 h-4 text-info" />
                Pipeline Orchestration Progress
              </span>
              <span className="font-mono text-info font-bold text-sm">{progressPercent}%</span>
            </div>
            <ProgressBar progress={statusData?.overall_progress ?? 0} />
            <div className="flex justify-between text-[11px] text-fg-dim font-mono">
              <span>Current: {statusData?.current_stage_id ? statusData.current_stage_id.toUpperCase() : "Ready to launch"}</span>
              <span>9 Stages Synchronized</span>
            </div>
          </div>

          {/* Success Banner */}
          {isCompleted && (
            <div className="p-4 bg-gradient-to-r from-ok/40 via-navy to-accent/40 border border-ok/60 rounded-xl space-y-3">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-2.5">
                  <div className="w-8 h-8 rounded-full bg-ok/20 text-ok flex items-center justify-center">
                    <Icons.CheckCircle className="w-5 h-5" />
                  </div>
                  <div>
                    <h3 className="text-sm font-bold text-fg">End-to-End Pipeline Execution Successful!</h3>
                    <p className="text-xs text-fg-dim">
                      Production video rendered, A/V validated, and YouTube packaging generated.
                    </p>
                  </div>
                </div>
                <Badge variant="success">PRODUCTION READY</Badge>
              </div>

              {statusData?.result?.output_mp4_path && (
                <div className="p-2.5 bg-ink border border-edge rounded-lg text-xs font-mono text-fg-dim truncate">
                  Output: {statusData.result.output_mp4_path}
                </div>
              )}

              <div className="flex flex-wrap items-center gap-2 pt-1">
                {onOpenPackaging && (
                  <Button
                    variant="primary"
                    size="sm"
                    onClick={onOpenPackaging}
                    className="bg-accent hover:bg-accent text-white font-bold text-xs flex items-center gap-1.5"
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
                    className="text-xs flex items-center gap-1.5 border-edge"
                  >
                    <Icons.Film className="w-3.5 h-3.5" />
                    <span>Open Video Player & Media Samples</span>
                  </Button>
                )}
              </div>
            </div>
          )}

          {/* Error Banner with Diagnostics & Actionable Troubleshooting */}
          {isFailed && (
            <div className="p-4 bg-bad/40 border border-bad/40 rounded-xl space-y-3">
              <div className="flex items-start justify-between gap-3">
                <div className="flex items-start gap-3">
                  <Icons.XCircle className="w-5 h-5 text-bad shrink-0 mt-0.5" />
                  <div className="space-y-1">
                    <div className="flex items-center gap-2">
                      <h4 className="font-bold text-bad text-sm">Pipeline Stopped</h4>
                      {statusData?.error_details?.category && (
                        <span className="text-[10px] font-mono font-bold uppercase px-2 py-0.5 rounded bg-bad/60 text-bad border border-bad/50">
                          {statusData.error_details.category}
                        </span>
                      )}
                      {statusData?.error_details?.stage_id && (
                        <span className="text-[10px] font-mono text-fg-dim">
                          Stage: {statusData.error_details.stage_id.toUpperCase()}
                        </span>
                      )}
                    </div>
                    <p className="text-bad font-mono text-xs break-words">
                      {statusData?.error || statusData?.error_details?.message}
                    </p>
                  </div>
                </div>
              </div>

              {/* Troubleshooting Guidance */}
              {statusData?.error_details?.troubleshooting && statusData.error_details.troubleshooting.length > 0 && (
                <div className="p-3 bg-ink/80 border border-edge/80 rounded-lg space-y-2">
                  <span className="text-[11px] font-bold text-fg-dim flex items-center gap-1.5 uppercase tracking-wider">
                    <Icons.AlertTriangle className="w-3.5 h-3.5 text-warn" />
                    Recommended Troubleshooting Actions
                  </span>
                  <ul className="space-y-1.5 pl-1">
                    {statusData.error_details.troubleshooting.map((tip, idx) => (
                      <li key={idx} className="text-xs text-fg-dim flex items-start gap-2">
                        <span className="text-warn font-bold shrink-0 mt-0.5">•</span>
                        <span>{tip}</span>
                      </li>
                    ))}
                  </ul>
                </div>
              )}

              {/* Action Buttons: Resume & Copy Diagnostics */}
              <div className="flex items-center gap-2 pt-1">
                <Button
                  variant="primary"
                  size="sm"
                  onClick={() => {
                    setSkipExisting(true);
                    handleStartRun();
                  }}
                  disabled={running || loading}
                  className="bg-accent hover:bg-accent text-white font-bold text-xs flex items-center gap-1.5"
                >
                  <Icons.Rotate className="w-3.5 h-3.5" />
                  <span>Resume Pipeline (Skip Finished)</span>
                </Button>
                {onOpenStage && statusData?.error_details?.stage_id && (
                  <Button
                    variant="secondary"
                    size="sm"
                    onClick={() => onOpenStage(statusData.error_details!.stage_id!)}
                    className="text-xs flex items-center gap-1.5 border-bad text-bad"
                  >
                    <span>Go to {statusData.error_details.stage_id.toUpperCase()} stage</span>
                  </Button>
                )}
                <Button
                  variant="secondary"
                  size="sm"
                  onClick={() => {
                    const text = [
                      `PanelFlow Pipeline Error Diagnostic`,
                      `Project: ${project.title} (${project.id})`,
                      `Stage: ${statusData?.error_details?.stage_id || statusData?.current_stage_id || "Unknown"}`,
                      `Category: ${statusData?.error_details?.category || "ERROR"}`,
                      `Message: ${statusData?.error || statusData?.error_details?.message}`,
                      `Troubleshooting:`,
                      ...(statusData?.error_details?.troubleshooting || []).map((t) => ` - ${t}`),
                    ].join("\n");
                    navigator.clipboard.writeText(text);
                    setCopiedDiagnostics(true);
                    setTimeout(() => setCopiedDiagnostics(false), 2500);
                  }}
                  className="text-xs flex items-center gap-1.5 border-edge"
                >
                  <Icons.CheckCircle className={`w-3.5 h-3.5 ${copiedDiagnostics ? "text-ok" : "text-fg-dim"}`} />
                  <span>{copiedDiagnostics ? "Copied Diagnostics!" : "Copy Diagnostics"}</span>
                </Button>
              </div>
            </div>
          )}

          {/* Main Grid: Stages Checklist (Left) & Console Logs (Right) */}
          <div className="grid grid-cols-1 lg:grid-cols-12 gap-6">
            {/* 9 Stages Checklist (6 cols) */}
            <div className="lg:col-span-6 space-y-2">
              <h3 className="text-xs font-bold text-fg uppercase tracking-wider mb-2 flex items-center gap-1.5">
                <Icons.Layers className="w-4 h-4 text-info" />
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
                          ? "border-accent bg-accent/20 shadow-md shadow-accent/10"
                          : isDone
                          ? "border-edge/80 bg-navy/40"
                          : isStageFailed
                          ? "border-bad/40 bg-bad/20"
                          : "border-edge/50 bg-ink/40 opacity-70"
                      }`}
                    >
                      <div className="flex items-center justify-between text-xs mb-1">
                        <div className="flex items-center gap-2">
                          {isDone ? (
                            <Icons.CheckCircle className="w-4 h-4 text-ok" />
                          ) : isCurrent ? (
                            <Icons.Refresh className="w-4 h-4 text-info animate-spin" />
                          ) : isStageFailed ? (
                            <Icons.XCircle className="w-4 h-4 text-bad" />
                          ) : (
                            <Icons.Clock className="w-4 h-4 text-fg-faint" />
                          )}
                          <span className={`font-semibold ${isCurrent ? "text-white" : isDone ? "text-fg" : "text-fg-dim"}`}>
                            {stage.name}
                          </span>
                        </div>

                        <div className="flex items-center gap-2">
                          {stage.duration_sec > 0 && (
                            <span className="text-[10px] font-mono text-fg-faint">
                              {stage.duration_sec.toFixed(1)}s
                            </span>
                          )}
                          <span
                            className={`text-[10px] font-mono font-bold uppercase px-1.5 py-0.5 rounded ${
                              isDone
                                ? "bg-ok/80 text-ok border border-ok/60"
                                : isCurrent
                                ? "bg-accent/80 text-info border border-accent/60 animate-pulse"
                                : isStageFailed
                                ? "bg-bad/20 text-bad"
                                : "text-fg-faint"
                            }`}
                          >
                            {stage.status}
                          </span>
                        </div>
                      </div>

                      {stage.message && (
                        <p className="text-[11px] text-fg-dim pl-6 truncate">
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
                <span className="font-bold text-fg uppercase tracking-wider flex items-center gap-1.5">
                  <Icons.Cpu className="w-4 h-4 text-info" />
                  Live Orchestration Console
                </span>
                <span className="text-[10px] font-mono text-fg-faint">
                  {statusData?.logs.length ?? 0} events
                </span>
              </div>

              <div className="flex-1 min-h-[380px] max-h-[460px] bg-black border border-edge rounded-xl p-3 overflow-y-auto font-mono text-[11px] space-y-1 text-fg-dim shadow-inner">
                {statusData?.logs && statusData.logs.length > 0 ? (
                  statusData.logs.map((logLine, lIdx) => (
                    <div key={lIdx} className="leading-tight break-all">
                      {logLine.includes("FAILED") || logLine.includes("error") ? (
                        <span className="text-bad">{logLine}</span>
                      ) : logLine.includes("completed") || logLine.includes("certified") || logLine.includes("Successful") ? (
                        <span className="text-ok font-semibold">{logLine}</span>
                      ) : logLine.includes("Starting") || logLine.includes("Stage:") ? (
                        <span className="text-info">{logLine}</span>
                      ) : (
                        <span className="text-fg-dim">{logLine}</span>
                      )}
                    </div>
                  ))
                ) : (
                  <div className="h-full flex items-center justify-center text-fg-faint">
                    Console idle. Click "Start Auto-Pilot Run" to begin.
                  </div>
                )}
                <div ref={logsEndRef} />
              </div>
            </div>
          </div>
        </div>

        {/* Modal Footer */}
        <div className="px-6 py-4 border-t border-edge/80 bg-navy/60 flex items-center justify-between">
          <div className="text-xs text-fg-dim">
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
                className="text-xs text-bad hover:text-bad border-bad/60"
              >
                {cancelling ? "Stopping..." : "Stop Auto-Pilot"}
              </Button>
            ) : (
              <Button
                variant="primary"
                size="sm"
                onClick={handleStartRun}
                disabled={loading}
                className="bg-accent hover:bg-accent text-white font-bold px-5 text-xs shadow-md shadow-accent/30 flex items-center gap-1.5"
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
