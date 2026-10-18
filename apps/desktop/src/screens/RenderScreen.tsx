import React, { useEffect, useState, useCallback, useRef } from "react";
import { api } from "@panelflow/api-client";
import type { Project, RenderJob, RenderStatus } from "@panelflow/shared-types";
import { Button, Card, Badge, ProgressBar, Icons } from "@panelflow/ui";

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
  const [renders, setRenders] = useState<RenderJob[]>([]);
  const [activeJob, setActiveJob] = useState<RenderJob | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [rendering, setRendering] = useState<boolean>(false);
  const [cancelling, setCancelling] = useState<boolean>(false);

  // Render Settings
  const [selectedProfile, setSelectedProfile] = useState<string>("standard_1080p");
  const [subtitlesEnabled, setSubtitlesEnabled] = useState<boolean>(true);
  const [bgmVolumeDb, setBgmVolumeDb] = useState<number>(-10.0);
  const [dialogueGainDb, setDialogueGainDb] = useState<number>(0.0);

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
    } catch (err) {
      console.error("Failed to load render history:", err);
    } finally {
      setLoading(false);
    }
  }, [project.id]);

  useEffect(() => {
    loadHistory();
  }, [loadHistory]);

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
  }, [rendering, activeJob?.render_id, project.id, onRenderComplete, loadHistory]);

  const handleStartRender = async () => {
    setRendering(true);
    try {
      const job = await api.startRender(project.id, {
        profileName: selectedProfile,
        subtitleEnabled: subtitlesEnabled,
        bgmVolumeDb,
        dialogueGainDb,
        isDraft: selectedProfile === "draft_720p",
      });
      setActiveJob(job);
      await loadHistory();
    } catch (err: any) {
      alert(`Render failed to start: ${err.message}`);
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
      alert(`Cancellation failed: ${err.message}`);
    } finally {
      setCancelling(false);
    }
  };

  const handleOpenFile = async (path: string) => {
    try {
      await api.openPath(path, true);
    } catch (err: any) {
      alert(`Could not open file: ${err.message}`);
    }
  };

  const handleOpenFolder = async (path: string) => {
    try {
      await api.openPath(path, false);
    } catch (err: any) {
      alert(`Could not open folder: ${err.message}`);
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
        <Card className="p-5 bg-zinc-900 border-zinc-800 space-y-4">
          <h2 className="text-sm font-bold text-zinc-100 uppercase tracking-wider">
            Output Configuration
          </h2>

          <div className="grid grid-cols-1 md:grid-cols-4 gap-4">
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
              <label className="text-xs font-semibold text-zinc-400">Subtitles</label>
              <label className="flex items-center gap-2 text-xs text-zinc-200 cursor-pointer pt-2">
                <input
                  type="checkbox"
                  checked={subtitlesEnabled}
                  onChange={(e) => setSubtitlesEnabled(e.target.checked)}
                  className="rounded accent-indigo-500 w-4 h-4"
                />
                Burn Dialogue Subtitles
              </label>
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

      {/* Completed Video Player & Validation Audit */}
      {activeJob && activeJob.status === "COMPLETE" && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
          {/* Video Player */}
          <Card className="lg:col-span-2 p-4 bg-zinc-900 border-zinc-800 space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-bold text-zinc-200">Video Player</h3>
              <Badge variant="success" className="text-[10px] uppercase font-bold">
                RENDER VERIFIED
              </Badge>
            </div>

            <div className="aspect-video bg-black rounded-lg overflow-hidden flex items-center justify-center">
              <video
                controls
                src={api.getRenderVideoUrl(project.id, activeJob.render_id)}
                className="w-full h-full object-contain"
              />
            </div>

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
              </div>
            </div>
          </Card>

          {/* Validation Report & Quality Audit */}
          <Card className="p-5 bg-zinc-900 border-zinc-800 space-y-4">
            <h3 className="text-sm font-bold text-zinc-200 uppercase tracking-wider">
              Validation Audit
            </h3>

            {activeJob.validation_report ? (() => {
              const report = activeJob.validation_report as any;
              const duration = report.duration_sec ?? report.actual_duration_sec ?? 0;
              const blackFrames = report.black_frames_count ?? report.quality_flags?.black_frames ?? 0;
              const timelineGaps = report.timeline_gaps_count ?? report.quality_flags?.timeline_gaps ?? 0;
              const clipping = report.clipping_samples_count ?? report.quality_flags?.audio_clipping_events ?? 0;
              const syncValid = report.sync_valid ?? (report.quality_flags?.av_sync_offset_ms === 0 || report.is_valid);
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
                      {syncValid ? "SYNCHRONIZED" : "DESYNC"}
                    </span>
                  </div>
                </div>
              );
            })() : (
              <p className="text-xs text-zinc-500">Validation report ready upon encode completion.</p>
            )}
          </Card>
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
    </div>
  );
};
