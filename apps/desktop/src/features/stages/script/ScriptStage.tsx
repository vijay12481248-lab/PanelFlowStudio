import React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@panelflow/api-client";
import type { Project } from "@panelflow/shared-types";
import { Button, Chip, EmptyState, GlassPanel, Select, Skeleton, Tabs, useToast } from "@panelflow/ui-v2";
import { useError } from "../../../context/ErrorContext";
import { ConfirmDialog } from "../kit/ConfirmDialog";
import { JobProgress } from "../kit/JobProgress";
import { StageToolbar } from "../kit/StageToolbar";
import { refusal } from "../kit/engineReason";
import { isActiveJob, stageKeys, useJob, useProjectJobs } from "../kit/stageData";
import { useNarrative, useStoryCharacters } from "../story/storyData";
import { ScriptMetrics } from "./ScriptMetrics";
import { SpokenList } from "./SpokenList";
import { StoryboardView } from "./StoryboardView";
import { UnsupportedBanner } from "./UnsupportedBanner";
import { scriptKeys, useScript, useScriptValidation, useStoryboard } from "./scriptData";
import { useScriptEditing } from "./useScriptEditing";
import { PROFILES, canApproveScript, isScriptApproved, unsupportedIssues, type SegmentAction } from "./scriptModel";

export interface ScriptStageProps {
  project: Project;
  /** Called with the reloaded project after the script is approved. */
  onApproved: (updated: Project) => void;
  /** Move on to Audio (already approved). */
  onContinue: (project: Project) => void;
  /** Called with the reloaded project after a line is edited. */
  onProjectUpdated: (updated: Project) => void;
}

const GENERATE_ADVICE = "Check the local model in Settings, then try again. The engine log in Diagnostics has the details.";

/** Script: adapt the story into spoken lines, check them against the source, fix what is unsupported, approve. */
export const ScriptStage: React.FC<ScriptStageProps> = ({ project, onApproved, onContinue, onProjectUpdated }) => {
  const queryClient = useQueryClient();
  const toast = useToast();
  const { reportError } = useError();

  const scriptQuery = useScript(project.id);
  const script = scriptQuery.data ?? null;
  const storyboardQuery = useStoryboard(project.id);
  // A storyboard belongs to a script. One without a script (a lost record) is not shown: it could not be edited or checked.
  const storyboard = script && storyboardQuery.data && storyboardQuery.data.segments.length > 0 ? storyboardQuery.data : null;
  const narrative = useNarrative(project.id);
  const characters = useStoryCharacters(project.id, narrative.isLoading ? undefined : narrative.data ?? null);
  const validation = useScriptValidation(project.id, script?.script_id);
  const issues = unsupportedIssues(validation.report);
  const editing = useScriptEditing({ project, script, validation, onProjectUpdated });
  const approved = isScriptApproved(project.current_stage, script?.status);

  const [profile, setProfile] = React.useState<string | null>(null);
  const profileValue = profile ?? script?.adaptation_profile ?? (project.settings?.visual_storytelling ? "DRAMATIC_NARRATION" : "FAITHFUL");
  const [view, setView] = React.useState<"storyboard" | "spoken" | null>(null);
  const [unsupportedOnly, setUnsupportedOnly] = React.useState(false);
  const [confirmReplace, setConfirmReplace] = React.useState(false);
  const [editingId, setEditingId] = React.useState<string | null>(null);
  const [pendingAction, setPendingAction] = React.useState<{ segmentId: string; action: SegmentAction } | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [starting, setStarting] = React.useState(false);
  const [approving, setApproving] = React.useState(false);
  const busy = React.useRef(false);

  // Follow a generation job: one started here, or one already running when the stage opened.
  const [jobId, setJobId] = React.useState<string | undefined>();
  const handled = React.useRef(new Set<string>());
  const jobsQuery = useProjectJobs(project.id);
  const latestJob = jobsQuery.data?.find((j) => j.job_type === "SCRIPT_GENERATION");
  React.useEffect(() => {
    if (!jobId && latestJob && isActiveJob(latestJob) && !handled.current.has(latestJob.job_id)) setJobId(latestJob.job_id);
  }, [jobId, latestJob?.job_id, latestJob?.status]); // eslint-disable-line react-hooks/exhaustive-deps
  const job = useJob(jobId);
  React.useEffect(() => {
    const finished = job.data;
    if (!jobId || !finished || isActiveJob(finished)) return;
    handled.current.add(jobId);
    setJobId(undefined);
    void queryClient.invalidateQueries({ queryKey: stageKeys.jobs(project.id) });
    if (finished.status === "SUCCEEDED") {
      void (async () => {
        const before = script?.script_id;
        await Promise.all([
          queryClient.invalidateQueries({ queryKey: scriptKeys.script(project.id) }),
          queryClient.invalidateQueries({ queryKey: scriptKeys.storyboard(project.id) }),
        ]);
        const fresh = queryClient.getQueryData<{ script_id: string } | null>(scriptKeys.script(project.id));
        // A new script id is validated automatically; the same id (a record rewritten in place) must be asked again.
        if (fresh && fresh.script_id === before && validation.hasSeen(before)) void validation.revalidate();
        toast.show("Script generated.");
      })();
    } else if (finished.status === "CANCELLED") {
      setError("Script generation was cancelled.");
    } else {
      setError(refusal("Couldn't generate the script.", new Error(finished.error ?? ""), GENERATE_ADVICE));
      reportError({ title: "Script Adaptation Failed", message: finished.error || finished.message || "Script generation failed.", severity: "error", source: "pipeline", projectId: project.id, jobType: "SCRIPT_GENERATION", rawDetails: finished });
    }
  }, [jobId, job.data?.status]); // eslint-disable-line react-hooks/exhaustive-deps
  const generating = starting || jobId !== undefined;
  const gate = canApproveScript({ script, report: validation.report, busy: generating || editing.busy });

  const generate = async () => {
    if (busy.current || generating) return;
    busy.current = true;
    setStarting(true);
    setError(null);
    try {
      setJobId((await api.generateScriptJob(project.id, profileValue)).job_id);
    } catch (err: any) {
      setError(refusal("Couldn't generate the script.", err, GENERATE_ADVICE));
      reportError({ title: "Script Adaptation Failed", message: "Failed to adapt and generate video script.", severity: "error", source: "pipeline", projectId: project.id, jobType: "SCRIPT_GENERATION", rawDetails: err });
    } finally { busy.current = false; setStarting(false); }
  };

  const approve = async () => {
    if (busy.current || !script || !gate.ok || approved) return;
    busy.current = true;
    setApproving(true);
    setError(null);
    try {
      await api.approveScript(project.id, script.script_id);
      onApproved(await api.getProject(project.id));
    } catch (err: any) {
      setError(refusal("Script can't be approved yet.", err, "Fix the flagged lines, then try again."));
      reportError({ title: "Approval Gate Blocked", message: "Strict script approval conditions were not satisfied.", severity: "error", source: "pipeline", projectId: project.id, rawDetails: { scriptId: script.script_id, error: err } });
      void validation.run(); // show which lines are flagged
    } finally { busy.current = false; setApproving(false); }
  };

  const onAction = (segmentId: string, action: SegmentAction) => (action.confirm ? setPendingAction({ segmentId, action }) : void editing.actionOn(segmentId, action.id));

  const statusChip = approved ? <Chip tone="ok">Approved</Chip> : script ? <Chip tone="accent">{script.status === "VALIDATED" ? "Validated" : "Draft"}</Chip> : <Chip>Not generated</Chip>;
  const activeView = view ?? (storyboard ? "storyboard" : "spoken");

  return (
    <div className="grid grid-cols-1 gap-5">
      <StageToolbar
        title="Review the script"
        description="Turn the story into spoken lines, check each one against the source, fix what is unsupported, then approve."
        status={statusChip}
        actions={
          <>
            <Button variant="secondary" size="sm" loading={generating} onClick={() => (script ? setConfirmReplace(true) : void generate())}>{script ? "Re-adapt script" : "Generate script"}</Button>
            {script && <Button variant="secondary" size="sm" loading={validation.state === "running"} onClick={() => void validation.run()}>Validate faithfulness</Button>}
            {script && !approved && <Button variant="primary" size="sm" loading={approving} disabled={!gate.ok} onClick={() => void approve()}>Approve script</Button>}
            {approved && <Button variant="secondary" size="sm" disabled>Script approved</Button>}
            {approved && <Button variant="primary" size="sm" onClick={() => onContinue(project)}>Continue to audio</Button>}
          </>
        }
      />

      <GlassPanel blur={false} className="flex flex-wrap items-end gap-3 p-4">
        <label className="grid gap-1.5 text-[13px] font-medium text-fg">
          Adaptation profile
          <Select aria-label="Adaptation profile" className="h-9 w-64 text-sm" value={profileValue} disabled={generating} onChange={(e) => setProfile(e.target.value)}>
            {PROFILES.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
          </Select>
        </label>
      </GlassPanel>

      {script && !approved && !gate.ok && <p className="text-sm text-warn">{gate.reason}</p>}
      {(error ?? editing.error) && <p role="alert" className="text-sm text-bad">{error ?? editing.error}</p>}
      {script && validation.state === "failed" && <p className="text-sm text-warn">Validation unavailable. Check that the engine is running, then press Validate faithfulness.</p>}
      {generating && <GlassPanel blur={false} className="p-4" role="status"><JobProgress job={job.data} idleLabel="Starting the script adaptation." /></GlassPanel>}

      {script && <ScriptMetrics script={script} report={validation.report} />}
      {script && issues.length > 0 && (
        <UnsupportedBanner
          issues={issues}
          segments={script.segments}
          characters={characters}
          approved={approved}
          filterOn={unsupportedOnly}
          onToggleFilter={() => setUnsupportedOnly((on) => !on)}
          onEdit={(segmentId) => { setEditingId(segmentId); setTimeout(() => document.getElementById(`seg-${segmentId}`)?.scrollIntoView?.({ behavior: "smooth", block: "center" }), 0); }}
        />
      )}

      {scriptQuery.isLoading ? (
        <Skeleton className="h-64" />
      ) : !script ? (
        <GlassPanel blur={false}><EmptyState title="No script yet" description="Generate a script to adapt the approved story into spoken lines and build the storyboard." /></GlassPanel>
      ) : storyboard ? (
        <Tabs value={activeView} onValueChange={(v) => setView(v as "storyboard" | "spoken")} tabs={[{ value: "storyboard", label: "Storyboard" }, { value: "spoken", label: "Spoken script" }]}>
          {activeView === "storyboard"
            ? <StoryboardView projectId={project.id} segments={storyboard.segments} totalSeconds={storyboard.total_duration_sec ?? script.estimated_duration} report={validation.report} unsupportedOnly={unsupportedOnly} editingId={editingId} onEdit={setEditingId} busy={editing.busy} realigning={editing.realigning} onSaveBeat={editing.saveBeat} onMotion={(id, panels) => void editing.setMotion(id, panels)} onRealign={() => void editing.realign()} />
            : <SpokenList projectId={project.id} segments={script.segments} characters={characters} report={validation.report} unsupportedOnly={unsupportedOnly} editingId={editingId} onEdit={setEditingId} busy={editing.busy} onAction={onAction} onSave={editing.saveLine} />}
        </Tabs>
      ) : (
        <SpokenList projectId={project.id} segments={script.segments} characters={characters} report={validation.report} unsupportedOnly={unsupportedOnly} editingId={editingId} onEdit={setEditingId} busy={editing.busy} onAction={onAction} onSave={editing.saveLine} />
      )}

      <ConfirmDialog
        open={pendingAction !== null}
        title={pendingAction?.action.confirm ?? "Change this line?"}
        description="The change is saved to the script and the storyboard straight away."
        confirmLabel={pendingAction?.action.label ?? "Confirm"}
        danger={pendingAction?.action.danger}
        onConfirm={() => { const pending = pendingAction; setPendingAction(null); if (pending) void editing.actionOn(pending.segmentId, pending.action.id); }}
        onCancel={() => setPendingAction(null)}
      />
      <ConfirmDialog
        open={confirmReplace}
        title="Replace the current script?"
        description="Adapting again writes a new script and replaces the current lines, including your edits."
        confirmLabel="Re-adapt script"
        onConfirm={() => { setConfirmReplace(false); void generate(); }}
        onCancel={() => setConfirmReplace(false)}
      />
    </div>
  );
};
