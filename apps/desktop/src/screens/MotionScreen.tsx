import React, { useEffect, useState, useCallback } from "react";
import { api } from "@panelflow/api-client";
import type { Project, MotionTimelineResponse, MotionStylePreset, Shot, Panel } from "@panelflow/shared-types";
import { Button, Card, Badge, Icons, SvgCameraFramingVisualizer } from "@panelflow/ui";
import { useError } from "../context/ErrorContext";

export interface MotionScreenProps {
  project: Project;
  onBack: () => void;
  onMotionApproved: (updatedProject: Project) => void;
  onProceedToRender: (proj: Project) => void;
}

export const MotionScreen: React.FC<MotionScreenProps> = ({
  project,
  onBack,
  onMotionApproved,
  onProceedToRender,
}) => {
  const { reportError, inspectError } = useError();
  const [motionData, setMotionData] = useState<MotionTimelineResponse | null>(null);
  const [panels, setPanels] = useState<Panel[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [planning, setPlanning] = useState<boolean>(false);
  const [approving, setApproving] = useState<boolean>(false);
  const [selectedPreset, setSelectedPreset] = useState<MotionStylePreset>("cinematic");
  const [videoEngine, setVideoEngine] = useState<"ken_burns" | "fast_h3">("fast_h3");
  const [shotMotions, setShotMotions] = useState<Record<string, string>>({});
  const [shotPrompts, setShotPrompts] = useState<Record<string, string>>({});
  const [previewingShot, setPreviewingShot] = useState<string | null>(null);
  const [shotVideoUrls, setShotVideoUrls] = useState<Record<string, string>>({});
  const [shotIntensities, setShotIntensities] = useState<Record<string, string>>({});
  const [shotFxs, setShotFxs] = useState<Record<string, string>>({});

  const QUICK_VFX_TAGS = [
    "💨 Wind in hair",
    "🫁 Breathing motion",
    "✨ Glowing aura",
    "🌧️ Rain droplets",
    "💥 Action speed lines",
    "🎬 24fps cinema",
    "🔍 Bokeh depth",
  ];

  const handleAddTag = (shotKey: string, tag: string) => {
    const cleanTag = tag.replace(/^[^\w\s]+/, "").trim();
    const cur = shotPrompts[shotKey] || "";
    const next = cur ? `${cur}, ${cleanTag}` : cleanTag;
    setShotPrompts((prev) => ({ ...prev, [shotKey]: next }));
  };

  const handlePreviewShot = async (shotKey: string, panelId?: string) => {
    if (!panelId) return;
    setPreviewingShot(shotKey);
    try {
      const motion = shotMotions[shotKey] || "push_in";
      const prompt = shotPrompts[shotKey] || "";
      const intensity = shotIntensities[shotKey] || "balanced";
      const fx = shotFxs[shotKey] || "none";
      const res = await (api as any).previewShotVideo(project.id, panelId, motion, prompt, videoEngine, intensity, fx);
      if (res?.video_url) {
        setShotVideoUrls((prev) => ({ ...prev, [shotKey]: res.video_url }));
      }
    } catch (err: any) {
      reportError({
        title: "Shot Video Preview Failed",
        message: err.message || "Could not generate shot video preview.",
        severity: "warning",
        source: "pipeline",
        projectId: project.id,
        rawDetails: err,
      });
    } finally {
      setPreviewingShot(null);
    }
  };

  const loadMotion = useCallback(async () => {
    setLoading(true);
    try {
      const [data, panelsList] = await Promise.all([
        api.getMotionTimeline(project.id).catch(() => null),
        api.listPanels(project.id).catch(() => []),
      ]);
      setMotionData(data);
      setPanels(panelsList);
      if (data?.style_preset) {
        setSelectedPreset(data.style_preset as MotionStylePreset);
      }
    } catch {
      setMotionData(null);
    } finally {
      setLoading(false);
    }
  }, [project.id]);

  useEffect(() => {
    loadMotion();
  }, [loadMotion]);

  const handlePlanMotion = async () => {
    setPlanning(true);
    try {
      const result = await api.planMotion(project.id, selectedPreset);
      setMotionData(result);
    } catch (err: any) {
      reportError({
        title: "Motion Planning Failed",
        message: err.message || "Failed to generate camera keyframes and motion plan.",
        severity: "error",
        source: "pipeline",
        projectId: project.id,
        rawDetails: err,
      });
    } finally {
      setPlanning(false);
    }
  };

  const handleApproveMotion = async () => {
    setApproving(true);
    try {
      await api.approveMotion(project.id);
      const updated = await api.getProject(project.id);
      setMotionData((prev) => (prev ? { ...prev, status: "APPROVED" } : null));
      onMotionApproved(updated);
    } catch (err: any) {
      reportError({
        title: "Motion Approval Gate Blocked",
        message: err.message || "Motion timeline gate conditions were not satisfied.",
        severity: "error",
        source: "pipeline",
        projectId: project.id,
        rawDetails: err,
      });
    } finally {
      setApproving(false);
    }
  };

  const formatDuration = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = Math.round(seconds % 60);
    return `${mins}:${secs < 10 ? "0" : ""}${secs}`;
  };

  const isApproved = motionData?.status === "APPROVED" || project.current_stage === "MOTION_APPROVED";

  return (
    <div className="space-y-6">
      {/* Header Bar */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-zinc-800 pb-5">
        <div className="space-y-1">
          <div className="flex items-center gap-3">
            <Button variant="ghost" size="sm" onClick={onBack}>
              <Icons.ArrowLeft className="w-4 h-4 mr-1" /> Back
            </Button>
            <h2 className="text-xl font-bold text-zinc-100 flex items-center gap-2">
              Motion Director & Shot Planning
            </h2>
            <Badge variant={isApproved ? "success" : "neutral"} className="uppercase font-mono">
              {motionData?.status || "NOT_PLANNED"}
            </Badge>
          </div>
          <p className="text-xs text-zinc-400">
            Automated shot composition, camera framing trajectories, and speech-synchronized pacing.
          </p>
        </div>

        {/* Action Controls */}
        <div className="flex flex-wrap items-center gap-2">
          {/* Video Engine Toggle */}
          <div className="flex items-center bg-zinc-900 border border-zinc-700 rounded-lg p-0.5 text-xs font-mono">
            <button
              type="button"
              onClick={() => setVideoEngine("ken_burns")}
              className={`px-2.5 py-1 rounded transition-colors ${
                videoEngine === "ken_burns"
                  ? "bg-zinc-700 text-white font-bold"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              Ken Burns 2D
            </button>
            <button
              type="button"
              onClick={() => setVideoEngine("fast_h3")}
              className={`px-2.5 py-1 rounded transition-colors flex items-center gap-1 ${
                videoEngine === "fast_h3"
                  ? "bg-indigo-600 text-white font-bold"
                  : "text-zinc-400 hover:text-zinc-200"
              }`}
            >
              Fast H3 Motion
            </button>
          </div>

          {/* Style Preset Selector */}
          <select
            value={selectedPreset}
            onChange={(e) => setSelectedPreset(e.target.value as MotionStylePreset)}
            disabled={planning}
            className="bg-zinc-900 border border-zinc-700 text-xs text-zinc-200 rounded-lg px-3 py-1.5 focus:outline-none focus:border-indigo-500 font-mono"
          >
            <option value="cinematic">Cinematic (Balanced)</option>
            <option value="action_dynamic">Action Dynamic (Fast Pans)</option>
            <option value="slow_burn">Slow Burn (Deliberate)</option>
            <option value="minimal">Minimal (Static Holds)</option>
            <option value="webtoon_scroll">Webtoon Scroll</option>
          </select>

          <Button
            variant="secondary"
            size="sm"
            onClick={handlePlanMotion}
            disabled={planning}
          >
            <Icons.Rotate className={`w-3.5 h-3.5 mr-1.5 ${planning ? "animate-spin" : ""}`} />
            {motionData ? "Re-Plan Motion" : "Plan Shots"}
          </Button>

          {motionData && (
            <Button
              variant="primary"
              size="sm"
              onClick={handleApproveMotion}
              disabled={approving || isApproved}
              className="bg-emerald-600 hover:bg-emerald-500 text-white"
            >
              <Icons.Check className="w-3.5 h-3.5 mr-1.5" />
              {isApproved ? "Motion Approved" : "Approve Motion"}
            </Button>
          )}

          {isApproved && (
            <Button
              variant="primary"
              size="sm"
              onClick={() => onProceedToRender(project)}
              className="bg-indigo-600 hover:bg-indigo-500 text-white"
            >
              Proceed to Render <Icons.ArrowRight className="w-3.5 h-3.5 ml-1.5" />
            </Button>
          )}
        </div>
      </div>

      {/* Metrics Cards */}
      {motionData && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <Card className="p-4 bg-zinc-900 border-zinc-800 space-y-1">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
              Total Duration
            </span>
            <div className="text-xl font-bold font-mono text-indigo-400">
              {formatDuration(motionData.total_duration)}
              <span className="text-xs text-zinc-400 ml-1.5 font-normal">
                ({motionData.total_duration.toFixed(1)}s)
              </span>
            </div>
          </Card>

          <Card className="p-4 bg-zinc-900 border-zinc-800 space-y-1">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
              Planned Shots
            </span>
            <div className="text-xl font-bold font-mono text-zinc-100">
              {motionData.total_shots} shots
            </div>
          </Card>

          <Card className="p-4 bg-zinc-900 border-zinc-800 space-y-1">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
              Style Preset
            </span>
            <div className="text-sm font-bold font-mono text-emerald-400 mt-1 uppercase">
              {motionData.style_preset}
            </div>
          </Card>

          <Card className="p-4 bg-zinc-900 border-zinc-800 space-y-1">
            <span className="text-[11px] font-semibold uppercase tracking-wider text-zinc-500">
              Continuity Checks
            </span>
            <div className="text-sm font-bold font-mono text-zinc-200 mt-1">
              {motionData.warnings_count ? `${motionData.warnings_count} notes` : "Zero Gaps (Clean)"}
            </div>
          </Card>
        </div>
      )}

      {/* Shots List */}
      {loading ? (
        <Card className="p-12 text-center bg-zinc-900 border-zinc-800 space-y-4">
          <Icons.Rotate className="w-8 h-8 text-zinc-600 animate-spin mx-auto" />
          <p className="text-xs text-zinc-400">Loading Visual Timeline...</p>
        </Card>
      ) : (() => {
        const timelineObj: any = motionData?.timeline || {};
        const scenesList: any[] = timelineObj.scenes || [];
        const rawShots: any[] = scenesList.length > 0
          ? scenesList.flatMap((s: any) =>
              (s.shots || []).map((shot: any) => ({
                ...shot,
                sceneTitle: s.title || `Scene ${s.sequence}`,
                sceneSeq: s.sequence,
              }))
            )
          : (timelineObj.shots || (Array.isArray(timelineObj) ? timelineObj : []) || (motionData as any)?.shots || []);

        if (rawShots.length === 0) {
          return (
            <Card className="p-12 text-center bg-zinc-900 border-zinc-800 space-y-4">
              <Icons.Layers className="w-10 h-10 text-zinc-600 mx-auto" />
              <div className="space-y-1">
                <h3 className="font-bold text-zinc-200">No Visual Timeline Planned Yet</h3>
                <p className="text-xs text-zinc-400 max-w-md mx-auto">
                  Click "Plan Shots" above to generate camera framing and motion curves aligned to the Master Audio Timeline.
                </p>
              </div>
              <Button variant="primary" onClick={handlePlanMotion} disabled={planning}>
                Plan Shots
              </Button>
            </Card>
          );
        }

        return (
          <div className="space-y-4">
            <div className="flex items-center justify-between text-xs text-zinc-400 pb-1">
              <span>{rawShots.length} Planned Camera Moves Aligned to Master Audio</span>
              <span className="text-[11px] font-mono text-indigo-400">Interactive Visual Trajectories</span>
            </div>

            {rawShots.map((shot: any, idx: number) => {
              const startCam = shot.camera_start || shot.start_rect || { center_x: 0.5, center_y: 0.5, zoom: 1.0 };
              const endCam = shot.camera_end || shot.end_rect || { center_x: 0.5, center_y: 0.5, zoom: 1.0 };
              const duration = shot.duration_sec ?? shot.duration ?? Math.max(0, (shot.end_time ?? 0) - (shot.start_time ?? 0));
              const motionType = shot.motion_type || shot.camera_motion_type || "CINEMATIC";
              const easing = shot.easing || shot.easing_function || "SMOOTHSTEP";
              const caption = shot.caption_cues && shot.caption_cues[0] ? shot.caption_cues[0] : null;

              // Resolve matched panel image
              const provPanels: string[] = shot.provenance?.panel_ids || [];
              let matchedPanel = panels.find((p: any) =>
                provPanels.includes(p.id) ||
                shot.source_panel_id === p.id ||
                shot.panel_id === p.id
              );

              if (!matchedPanel && shot.source_panel_id) {
                const match = String(shot.source_panel_id).match(/panel_(\d+)/i);
                if (match) {
                  const seq = parseInt(match[1], 10);
                  matchedPanel = panels.find((p: any) => p.sequence === seq);
                }
              }

              if (!matchedPanel && panels.length > 0) {
                matchedPanel = panels[idx % panels.length];
              }

              const panelImageUrl = matchedPanel ? api.getPanelImageUrl(project.id, matchedPanel.id) : undefined;

              return (
                <Card
                  key={shot.shot_id || idx}
                  className="p-4 bg-zinc-900 border-zinc-800 hover:border-zinc-700 transition-all shadow-sm"
                >
                  <div className="flex flex-col lg:flex-row lg:items-center gap-4">
                    {/* Left: Interactive Visual Camera Framing Preview */}
                    <SvgCameraFramingVisualizer
                      imageUrl={panelImageUrl}
                      startCamera={startCam}
                      endCamera={endCam}
                      motionType={motionType}
                      durationSec={duration}
                      easing={easing}
                    />

                    {/* Center: Shot Metadata, Captions, and Pacing */}
                    <div className="space-y-2 flex-1 min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-xs font-bold text-indigo-400 font-mono">
                          Shot #{idx + 1}
                        </span>
                        {shot.sceneTitle && (
                          <span className="text-[10px] uppercase font-bold bg-zinc-800 text-zinc-300 px-2 py-0.5 rounded border border-zinc-700/60">
                            {shot.sceneTitle}
                          </span>
                        )}
                        <Badge
                          variant="accent"
                          className="text-[10px] uppercase font-bold"
                        >
                          {motionType}
                        </Badge>
                        <span className="text-[11px] font-mono text-zinc-400">
                          {(shot.start_time ?? 0).toFixed(2)}s - {(shot.end_time ?? 0).toFixed(2)}s ({duration.toFixed(2)}s)
                        </span>
                        {shot.transition_in && (
                          <span className="text-[10px] bg-zinc-850 text-zinc-400 px-2 py-0.5 rounded font-mono border border-zinc-800">
                            {typeof shot.transition_in === "string" ? shot.transition_in : shot.transition_in.transition_type}
                            {typeof shot.transition_in === "object" && shot.transition_in.duration_sec ? ` (${shot.transition_in.duration_sec}s)` : ""}
                          </span>
                        )}
                      </div>

                      {/* Dialogue / Caption Line Preview */}
                      {caption && (
                        <div className="p-2.5 rounded bg-zinc-950 border border-zinc-800/80 text-xs">
                          <span className="font-bold text-indigo-300 mr-2 uppercase text-[10px] tracking-wider">
                            {caption.speaker || "SPEAKER"}:
                          </span>
                          <span className="text-zinc-200 italic leading-relaxed">
                            "{caption.text}"
                          </span>
                        </div>
                      )}

                      {/* Camera Framing Details */}
                      <div className="flex items-center gap-3 text-[11px] text-zinc-400 font-mono">
                        <span>
                          Start: {startCam.zoom ? `${startCam.zoom.toFixed(2)}x Zoom` : "1.00x"}
                        </span>
                        <span>→</span>
                        <span className="text-zinc-200">
                          End: {endCam.zoom ? `${endCam.zoom.toFixed(2)}x Zoom` : "1.00x"}
                        </span>
                        <span className="text-zinc-500">· Easing: {easing}</span>
                      </div>

                      {/* Fast H3 Motion Controls & VFX Prompt */}
                      <div className="pt-2 border-t border-zinc-800/60 space-y-2">
                        <div className="flex flex-wrap items-center gap-2">
                          {/* Camera Motion */}
                          <select
                            value={shotMotions[shot.shot_id || idx] || "push_in"}
                            onChange={(e) => setShotMotions({ ...shotMotions, [shot.shot_id || idx]: e.target.value })}
                            className="bg-zinc-950 border border-zinc-800 text-[11px] text-zinc-300 rounded px-2 py-1 font-mono focus:outline-none focus:border-indigo-500"
                          >
                            <option value="push_in">Camera: Push In</option>
                            <option value="pull_out">Camera: Pull Out</option>
                            <option value="pan_left">Camera: Pan Left</option>
                            <option value="pan_right">Camera: Pan Right</option>
                            <option value="tilt_up">Camera: Tilt Up</option>
                            <option value="orbit">Camera: Orbit</option>
                            <option value="static">Camera: Static Hold</option>
                          </select>

                          {/* Motion Intensity */}
                          <select
                            value={shotIntensities[shot.shot_id || idx] || "balanced"}
                            onChange={(e) => setShotIntensities({ ...shotIntensities, [shot.shot_id || idx]: e.target.value })}
                            className="bg-zinc-950 border border-zinc-800 text-[11px] text-zinc-300 rounded px-2 py-1 font-mono focus:outline-none focus:border-indigo-500"
                          >
                            <option value="subtle">Intensity: Subtle (0.5x)</option>
                            <option value="balanced">Intensity: Balanced (1.0x)</option>
                            <option value="action">Intensity: Dynamic Action (1.8x)</option>
                          </select>

                          {/* Motion Graphics FX Overlay */}
                          <select
                            value={shotFxs[shot.shot_id || idx] || "none"}
                            onChange={(e) => setShotFxs({ ...shotFxs, [shot.shot_id || idx]: e.target.value })}
                            className="bg-zinc-950 border border-zinc-800 text-[11px] text-zinc-300 rounded px-2 py-1 font-mono focus:outline-none focus:border-indigo-500"
                          >
                            <option value="none">FX: Clean (None)</option>
                            <option value="letterbox">FX: Cinematic 2.39:1 Scope</option>
                            <option value="vignette">FX: Vignette & Tone</option>
                            <option value="film_grain">FX: 35mm Film Grain</option>
                            <option value="action_shake">FX: Action Camera Shake</option>
                            <option value="warm_cinema">FX: Warm Cinema Grade</option>
                          </select>

                          {/* FL2V Continuity Tag */}
                          <span className="text-[10px] font-mono px-2 py-0.5 rounded bg-zinc-800/80 text-zinc-400 border border-zinc-700/60 ml-auto">
                            FL2V: Panel #{matchedPanel?.sequence ?? (idx + 1)}
                          </span>
                        </div>

                        {/* Quick Tag Pills */}
                        <div className="flex flex-wrap items-center gap-1.5 pt-0.5">
                          <span className="text-[10px] uppercase font-bold text-zinc-500 font-mono">Quick VFX:</span>
                          {QUICK_VFX_TAGS.map((tag) => (
                            <button
                              key={tag}
                              type="button"
                              onClick={() => handleAddTag(shot.shot_id || String(idx), tag)}
                              className="text-[10px] font-mono px-2 py-0.5 rounded-full bg-zinc-800 hover:bg-zinc-700 text-zinc-300 hover:text-white transition-colors border border-zinc-700/50"
                            >
                              {tag}
                            </button>
                          ))}
                        </div>

                        {/* Prompt Input & Generate Preview Button */}
                        <div className="flex flex-col sm:flex-row items-stretch sm:items-center gap-2">
                          <input
                            type="text"
                            placeholder="Motion prompt / VFX details (e.g. glowing aura, wind blowing hair, sharp focus)"
                            value={shotPrompts[shot.shot_id || idx] || ""}
                            onChange={(e) => setShotPrompts({ ...shotPrompts, [shot.shot_id || idx]: e.target.value })}
                            className="bg-zinc-950 border border-zinc-800 text-[11px] text-zinc-300 rounded px-2.5 py-1.5 flex-1 font-mono placeholder:text-zinc-600 focus:outline-none focus:border-indigo-500"
                          />

                          <Button
                            variant="secondary"
                            size="sm"
                            onClick={() => handlePreviewShot(shot.shot_id || String(idx), matchedPanel?.id)}
                            disabled={previewingShot === (shot.shot_id || String(idx)) || !matchedPanel}
                            className="text-[11px] px-3 py-1.5 bg-indigo-600/20 hover:bg-indigo-600/30 text-indigo-200 border border-indigo-500/30"
                          >
                            <Icons.Play className={`w-3 h-3 mr-1.5 ${previewingShot === (shot.shot_id || String(idx)) ? "animate-pulse" : ""}`} />
                            {previewingShot === (shot.shot_id || String(idx)) ? "Generating Video..." : "Preview Shot"}
                          </Button>
                        </div>
                      </div>

                      {/* Shot Preview Video if Generated */}
                      {shotVideoUrls[shot.shot_id || String(idx)] && (
                        <div className="mt-2 rounded overflow-hidden border border-zinc-800 bg-black">
                          <video
                            src={shotVideoUrls[shot.shot_id || String(idx)]}
                            controls
                            autoPlay
                            loop
                            className="w-full max-h-48 object-contain"
                          />
                        </div>
                      )}
                    </div>

                    {/* Right: Duration pill & Panel Reference */}
                    <div className="flex flex-col sm:flex-row lg:flex-col items-end justify-between gap-3 flex-shrink-0">
                      <span className="text-xs font-mono font-bold text-zinc-200 bg-zinc-800/90 px-3 py-1 rounded border border-zinc-700">
                        {duration.toFixed(2)}s
                      </span>
                      {matchedPanel && (
                        <span className="text-[10px] font-mono text-zinc-500">
                          Panel #{matchedPanel.sequence}
                        </span>
                      )}
                    </div>
                  </div>
                </Card>
              );
            })}
          </div>
        );
      })()}
    </div>
  );
};
