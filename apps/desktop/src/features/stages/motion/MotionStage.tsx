import React from "react";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@panelflow/api-client";
import type { MotionTimelineResponse, Panel, Project } from "@panelflow/shared-types";
import { Button, Chip, EmptyState, GlassPanel, Select, Skeleton } from "@panelflow/ui-v2";
import { useError } from "../../../context/ErrorContext";
import { useEngine } from "../../../app/providers";
import { ConfirmDialog } from "../kit/ConfirmDialog";
import { StageToolbar } from "../kit/StageToolbar";
import { refusal } from "../kit/engineReason";
import { ShotCard, type PreviewRequest } from "./ShotCard";
import { extractShots, formatClock, matchPanel, shotView, STYLE_PRESETS, VIDEO_ENGINES } from "./motionModel";

export interface MotionStageProps {
  project: Project;
  /** Called with the reloaded project after the motion plan is approved. */
  onApproved: (updated: Project) => void;
  /** Move on to Render (already approved). */
  onContinue: (project: Project) => void;
}

const motionKey = (projectId: string) => ["stages", "motion", projectId] as const;
const panelsKey = (projectId: string) => ["stages", "panels", projectId] as const;

/** Motion: plan the camera moves, look at each shot, approve. Per-shot previews are for looking only and are never saved. */
export const MotionStage: React.FC<MotionStageProps> = ({ project, onApproved, onContinue }) => {
  const queryClient = useQueryClient();
  const { connected } = useEngine();
  const { reportError } = useError();
  // No plan is a normal state: the engine answers with an error, which is shown as "no plan yet".
  const motion = useQuery<MotionTimelineResponse | null>({ queryKey: motionKey(project.id), queryFn: () => api.getMotionTimeline(project.id).catch(() => null), enabled: connected, retry: false });
  const panelsQuery = useQuery<Panel[]>({ queryKey: panelsKey(project.id), queryFn: () => api.listPanels(project.id).catch(() => []), enabled: connected, retry: false });
  const panels = panelsQuery.data ?? [];
  const data = motion.data ?? null;
  const shots = React.useMemo(() => extractShots(data), [data]);
  const hasPlan = shots.length > 0;
  const approved = data?.status === "APPROVED" || project.current_stage === "MOTION_APPROVED";

  const [preset, setPreset] = React.useState<string>("cinematic");
  const [engine, setEngine] = React.useState<string>("fast_h3");
  const [confirmReplace, setConfirmReplace] = React.useState(false);
  const [planning, setPlanning] = React.useState(false);
  const [approving, setApproving] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const busy = React.useRef(false);

  // Start from the style the saved plan used.
  React.useEffect(() => { if (data?.style_preset) setPreset(data.style_preset); }, [data?.style_preset]);

  const plan = async () => {
    if (busy.current) return;
    busy.current = true;
    setPlanning(true);
    setError(null);
    try {
      queryClient.setQueryData(motionKey(project.id), await api.planMotion(project.id, preset));
    } catch (err: any) {
      setError("Couldn't plan the motion. Check that the engine is running, then try again.");
      reportError({ title: "Motion Planning Failed", message: "Failed to generate camera keyframes and motion plan.", severity: "error", source: "pipeline", projectId: project.id, rawDetails: err });
    } finally { busy.current = false; setPlanning(false); }
  };

  const approve = async () => {
    if (busy.current || !hasPlan || approved) return;
    busy.current = true;
    setApproving(true);
    setError(null);
    try {
      await api.approveMotion(project.id);
      const updated = await api.getProject(project.id);
      queryClient.setQueryData<MotionTimelineResponse | null>(motionKey(project.id), (prev) => (prev ? { ...prev, status: "APPROVED" } : prev));
      onApproved(updated);
    } catch (err: any) {
      setError(refusal("Motion can't be approved yet.", err, "Plan the motion again, then try approving."));
      reportError({ title: "Motion Approval Gate Blocked", message: "Motion timeline gate conditions were not satisfied.", severity: "error", source: "pipeline", projectId: project.id, rawDetails: err });
    } finally { busy.current = false; setApproving(false); }
  };

  const preview = async (request: PreviewRequest) => {
    try {
      const res = await api.previewShotVideo(project.id, request.panelId, request.motion, request.prompt, engine, request.intensity, request.fx);
      return res?.video_url ?? null;
    } catch (err: any) {
      reportError({ title: "Shot Video Preview Failed", message: "Could not generate shot video preview.", severity: "warning", source: "pipeline", projectId: project.id, rawDetails: err });
      throw err;
    }
  };

  const statusChip = approved ? <Chip tone="ok">Approved</Chip> : hasPlan ? <Chip tone="accent">Draft</Chip> : <Chip>Not planned</Chip>;

  return (
    <div className="grid grid-cols-1 gap-5">
      <StageToolbar
        title="Plan camera motion"
        description="Plan the camera move for every shot, look through them, then approve the plan."
        status={statusChip}
        actions={
          <>
            {hasPlan && !approved && <Button variant="primary" size="sm" loading={approving} onClick={() => void approve()}>Approve motion</Button>}
            {approved && <Button variant="secondary" size="sm" disabled>Motion approved</Button>}
            {approved && <Button variant="primary" size="sm" onClick={() => onContinue(project)}>Continue to render</Button>}
          </>
        }
      />

      <GlassPanel blur={false} className="flex flex-wrap items-end gap-3 p-4">
        <label className="grid gap-1.5 text-[13px] font-medium text-fg">
          Style
          <Select aria-label="Style" className="h-9 w-64 text-sm" value={preset} disabled={planning} onChange={(e) => setPreset(e.target.value)}>
            {STYLE_PRESETS.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </Select>
        </label>
        <label className="grid gap-1.5 text-[13px] font-medium text-fg">
          Preview engine
          <Select aria-label="Preview engine" className="h-9 w-48 text-sm" value={engine} onChange={(e) => setEngine(e.target.value)}>
            {VIDEO_ENGINES.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
          </Select>
        </label>
        <Button variant="secondary" size="sm" loading={planning} onClick={() => (hasPlan ? setConfirmReplace(true) : void plan())}>{hasPlan ? "Re-plan motion" : "Plan motion"}</Button>
      </GlassPanel>

      {error && <p role="alert" className="text-sm text-bad">{error}</p>}

      {data && hasPlan && (
        <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
          <Stat label="Total length" value={formatClock(data.total_duration)} detail={`${data.total_duration.toFixed(1)}s`} />
          <Stat label="Planned shots" value={`${data.total_shots} shots`} />
          <Stat label="Style" value={data.style_preset} />
          <Stat label="Continuity" value={data.warnings_count ? `${data.warnings_count} notes` : "Clean"} />
        </div>
      )}

      {!motion.data && motion.isLoading ? (
        <Skeleton className="h-64" />
      ) : !hasPlan ? (
        <GlassPanel blur={false}>
          <EmptyState title="No camera plan yet" description="Plan motion to give every shot a camera move that follows the voice track." />
        </GlassPanel>
      ) : (
        <section className="grid grid-cols-1 gap-4" aria-label="Planned shots">
          <p className="text-sm text-fg-dim">{`${shots.length} planned camera moves, aligned to the voice track`}</p>
          {shots.map((raw, index) => {
            const view = shotView(raw, index);
            const panel = matchPanel(raw, index, panels);
            return <ShotCard key={view.key} shot={view} panel={panel} panelImageUrl={panel ? api.getPanelImageUrl(project.id, panel.id) : undefined} onPreview={preview} />;
          })}
        </section>
      )}

      <ConfirmDialog
        open={confirmReplace}
        title="Replace the current plan?"
        description="Planning again writes new camera moves for every shot. The current plan is replaced."
        confirmLabel="Replace plan"
        onConfirm={() => { setConfirmReplace(false); void plan(); }}
        onCancel={() => setConfirmReplace(false)}
      />
    </div>
  );
};

const Stat: React.FC<{ label: string; value: string; detail?: string }> = ({ label, value, detail }) => (
  <GlassPanel blur={false} className="grid gap-1 p-3">
    <p className="text-xs text-fg-faint">{label}</p>
    <p className="font-display text-lg font-semibold text-fg">{value}{detail && <span className="ml-1.5 text-xs font-normal text-fg-dim">{`(${detail})`}</span>}</p>
  </GlassPanel>
);
