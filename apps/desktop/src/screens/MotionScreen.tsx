import React, { useEffect, useState, useCallback } from "react";
import { api } from "@panelflow/api-client";
import type { Project, MotionTimelineResponse, MotionStylePreset, Shot } from "@panelflow/shared-types";
import { Button, Card, Badge, Icons } from "@panelflow/ui";

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
  const [motionData, setMotionData] = useState<MotionTimelineResponse | null>(null);
  const [loading, setLoading] = useState<boolean>(true);
  const [planning, setPlanning] = useState<boolean>(false);
  const [approving, setApproving] = useState<boolean>(false);
  const [selectedPreset, setSelectedPreset] = useState<MotionStylePreset>("cinematic");

  const loadMotion = useCallback(async () => {
    setLoading(true);
    try {
      const data = await api.getMotionTimeline(project.id);
      setMotionData(data);
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
      alert(`Motion planning failed: ${err.message}`);
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
      alert(`Motion approval failed: ${err.message}`);
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
            <h1 className="text-xl font-bold text-zinc-100 flex items-center gap-2">
              Motion Director & Shot Planning
            </h1>
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
        const shotsList: any[] = (motionData?.timeline as any)?.shots || (Array.isArray(motionData?.timeline) ? motionData.timeline : []) || (motionData as any)?.shots || [];
        if (shotsList.length === 0) {
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
          <div className="space-y-3">
            {shotsList.map((shot: any, idx: number) => {
            const startBox = shot.camera_start || shot.start_rect || { x: 0, y: 0, width: 1, height: 1, center_x: 0.5, center_y: 0.5 };
            const endBox = shot.camera_end || shot.end_rect || { x: 0, y: 0, width: 1, height: 1, center_x: 0.5, center_y: 0.5 };
            const startCx = startBox.center_x ?? ((startBox.x ?? 0) + (startBox.width ?? 1) / 2);
            const startCy = startBox.center_y ?? ((startBox.y ?? 0) + (startBox.height ?? 1) / 2);
            const startW = startBox.width ?? 1;
            const endCx = endBox.center_x ?? ((endBox.x ?? 0) + (endBox.width ?? 1) / 2);
            const endCy = endBox.center_y ?? ((endBox.y ?? 0) + (endBox.height ?? 1) / 2);
            const endW = endBox.width ?? 1;
            const isMoving = Math.abs(startCx - endCx) > 0.01 || Math.abs(startCy - endCy) > 0.01 || Math.abs(startW - endW) > 0.01;
            const motionType = shot.motion_type || shot.camera_motion_type || "STATIC";
            const sourceId = shot.source_asset_id || shot.panel_id || shot.visual_source_id || `Shot ${idx + 1}`;
            const startTime = shot.start_time_sec ?? shot.start_time ?? 0;
            const endTime = shot.end_time_sec ?? shot.end_time ?? 0;
            const duration = shot.duration_sec ?? shot.duration ?? Math.max(0, endTime - startTime);
            const easing = shot.easing || shot.easing_function || "LINEAR";

            return (
              <Card
                key={shot.shot_id || idx}
                className="p-4 bg-zinc-900 border-zinc-800 hover:border-zinc-700 transition-colors"
              >
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
                  {/* Left: Shot Identification & Motion Details */}
                  <div className="space-y-1.5 flex-1 min-w-0">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="text-xs font-bold text-indigo-400 font-mono">
                        Shot #{idx + 1}
                      </span>
                      <Badge
                        variant={isMoving ? "accent" : "neutral"}
                        className="text-[10px] uppercase font-bold"
                      >
                        {motionType}
                      </Badge>
                      <span className="text-xs font-bold text-zinc-100">
                        {sourceId}
                      </span>
                      <span className="text-[11px] font-mono text-zinc-400">
                        {startTime.toFixed(2)}s - {endTime.toFixed(2)}s ({duration.toFixed(2)}s)
                      </span>
                      {shot.transition_in && shot.transition_in !== "CUT" && (
                        <span className="text-[10px] bg-zinc-800 text-zinc-400 px-1.5 py-0.5 rounded font-mono">
                          {shot.transition_in} ({shot.transition_duration_sec || 0.5}s)
                        </span>
                      )}
                    </div>

                    {/* Camera framing trajectories */}
                    <div className="flex items-center gap-4 text-[11px] text-zinc-400 font-mono pt-1">
                      <div>
                        Start Framing:{" "}
                        <span className="text-zinc-300">
                          [{startCx.toFixed(2)}, {startCy.toFixed(2)}] ({Math.round(startW * 100)}% w)
                        </span>
                      </div>
                      <div>→</div>
                      <div>
                        End Framing:{" "}
                        <span className="text-zinc-300">
                          [{endCx.toFixed(2)}, {endCy.toFixed(2)}] ({Math.round(endW * 100)}% w)
                        </span>
                      </div>
                      <div className="text-[10px] text-zinc-500">
                        Easing: {easing}
                      </div>
                    </div>
                  </div>

                  {/* Right: Duration pill */}
                  <div className="text-right flex-shrink-0">
                    <span className="text-xs font-mono font-bold text-zinc-300 bg-zinc-800/80 px-2.5 py-1 rounded">
                      {duration.toFixed(2)}s
                    </span>
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
