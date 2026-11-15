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
import { AnalysisActivity } from "./AnalysisActivity";
import { CharactersTab } from "./CharactersTab";
import { ContinuityTab } from "./ContinuityTab";
import { ScenesTab } from "./ScenesTab";
import { UtterancesTab } from "./UtterancesTab";
import { storyKeys, useNarrative, usePanelsLite, useStoryCharacters, useStoryProviders } from "./storyData";
import { blockingWarnings, canApproveStory, isStoryApproved, normalizeScenes, providerChoices, sceneBlocks } from "./storyModel";

export interface StoryStageProps {
  project: Project;
  /** Called with the reloaded project after the story is approved. */
  onApproved: (updated: Project) => void;
  /** Move on to Script (already approved). */
  onContinue: (project: Project) => void;
}

const ANALYSIS_ADVICE = "Check the model in Settings, then try again. The engine log in Diagnostics has the details.";

/** Story: run the analysis, check characters, scenes, utterances and continuity, approve the narrative. */
export const StoryStage: React.FC<StoryStageProps> = ({ project, onApproved, onContinue }) => {
  const queryClient = useQueryClient();
  const toast = useToast();
  const { reportError } = useError();

  const narrativeQuery = useNarrative(project.id);
  const narrative = narrativeQuery.data ?? null;
  const providers = useStoryProviders();
  const choices = React.useMemo(() => providerChoices(providers.data ?? [], project.settings), [providers.data, project.settings]);
  const [chosen, setChosen] = React.useState<string | null>(null);
  const providerId = chosen && choices.options.some((o) => o.id === chosen) ? chosen : choices.defaultId;
  const panels = usePanelsLite(project.id).data ?? [];
  const characters = useStoryCharacters(project.id, narrativeQuery.isLoading ? undefined : narrative);
  const blocks = React.useMemo(() => sceneBlocks(narrative, normalizeScenes(narrative?.scenes)), [narrative]);
  const blocking = blockingWarnings(narrative);
  const approved = isStoryApproved(project.current_stage);

  const [tab, setTab] = React.useState("characters");
  const [confirmReplace, setConfirmReplace] = React.useState(false);
  const [error, setError] = React.useState<string | null>(null);
  const [notice, setNotice] = React.useState<string | null>(null);
  const [starting, setStarting] = React.useState(false);
  const [approving, setApproving] = React.useState(false);
  const [cancelling, setCancelling] = React.useState(false);
  const busy = React.useRef(false);
  const cancelBusy = React.useRef(false); // synchronous: state alone lets a fast double click cancel twice

  // Follow an analysis job: one started here, or one already running when the stage opened.
  const [jobId, setJobId] = React.useState<string | undefined>();
  const handled = React.useRef(new Set<string>());
  const jobsQuery = useProjectJobs(project.id);
  const latestJob = jobsQuery.data?.find((j) => j.job_type === "STORY_ANALYSIS");
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
      void queryClient.invalidateQueries({ queryKey: storyKeys.narrative(project.id) });
      toast.show("Story analysis finished.");
    } else if (finished.status === "CANCELLED") {
      setNotice("Analysis cancelled.");
    } else {
      setError(refusal("Couldn't analyse the story.", new Error(finished.error ?? ""), ANALYSIS_ADVICE));
      reportError({ title: "Story Understanding Failed", message: finished.error || finished.message || "Story analysis failed.", severity: "error", source: "job", jobId, projectId: project.id, jobType: "STORY_ANALYSIS", rawDetails: finished });
    }
  }, [jobId, job.data?.status]); // eslint-disable-line react-hooks/exhaustive-deps
  const analyzing = starting || jobId !== undefined;
  const gate = canApproveStory({ narrative, analyzing });

  const run = async () => {
    if (busy.current || analyzing || !providerId) return;
    busy.current = true;
    setStarting(true);
    setError(null);
    setNotice(null);
    try {
      setJobId((await api.analyzeStory(project.id, providerId)).job_id);
    } catch (err: any) {
      setError("Couldn't start the story analysis. Check that the engine is running, then try again.");
      reportError({ title: "Failed to Start Story Analysis", message: "Failed to trigger story analysis.", severity: "error", source: "engine", projectId: project.id, jobType: "STORY_ANALYSIS", rawDetails: err });
    } finally { busy.current = false; setStarting(false); }
  };

  const cancel = async () => {
    if (!jobId || cancelBusy.current) return;
    cancelBusy.current = true;
    setCancelling(true);
    try {
      await api.cancelJob(jobId);
      await job.refetch();
    } catch {
      setError("Couldn't cancel the analysis. Try again in a moment.");
    } finally { cancelBusy.current = false; setCancelling(false); }
  };

  const approve = async () => {
    if (busy.current || !gate.ok || approved) return;
    busy.current = true;
    setApproving(true);
    setError(null);
    try {
      await api.confirmStory(project.id);
      onApproved(await api.getProject(project.id));
    } catch (err: any) {
      setError(refusal("Story can't be approved yet.", err, "Fix the continuity errors, then try again."));
      reportError({ title: "Story Approval Gate Blocked", message: "Strict story narrative gate verification failed.", severity: "error", source: "pipeline", projectId: project.id, rawDetails: err });
    } finally { busy.current = false; setApproving(false); }
  };

  const reload = () => queryClient.invalidateQueries({ queryKey: storyKeys.narrative(project.id) });
  const statusChip = approved ? <Chip tone="ok">Approved</Chip> : narrative ? <Chip tone="accent">Draft</Chip> : <Chip>Not analysed</Chip>;
  const noModel = !providers.isLoading && !providerId;

  const tabs = [
    { value: "characters", label: `Characters (${characters.length})` },
    { value: "scenes", label: `Scenes and beats (${blocks.length})` },
    { value: "utterances", label: `Utterances (${narrative?.utterances?.length ?? 0})` },
    { value: "continuity", label: `Continuity (${narrative?.continuity_warnings?.length ?? 0})` },
  ];

  return (
    <div className="grid grid-cols-1 gap-5">
      <StageToolbar
        title="Review the story"
        description="Check the characters, scenes, dialogue and continuity the analysis found, then approve the story."
        status={statusChip}
        actions={
          <>
            <Button variant="secondary" size="sm" loading={analyzing} disabled={!providerId} onClick={() => (narrative ? setConfirmReplace(true) : void run())}>{narrative ? "Re-analyze story" : "Run story analysis"}</Button>
            {narrative && !approved && <Button variant="primary" size="sm" loading={approving} disabled={!gate.ok} onClick={() => void approve()}>Approve story</Button>}
            {approved && <Button variant="secondary" size="sm" disabled>Story approved</Button>}
            {approved && <Button variant="primary" size="sm" onClick={() => onContinue(project)}>Continue to script</Button>}
          </>
        }
      />

      <GlassPanel blur={false} className="flex flex-wrap items-end gap-3 p-4">
        <label className="grid gap-1.5 text-[13px] font-medium text-fg">
          Model
          <Select aria-label="Model" className="h-9 w-80 text-sm" value={providerId ?? ""} disabled={analyzing || choices.options.length === 0} onChange={(e) => setChosen(e.target.value)}>
            {!providerId && <option value="">No model selected</option>}
            {choices.options.map((o) => <option key={o.id} value={o.id}>{o.label}</option>)}
          </Select>
        </label>
        {providers.isError && <p className="text-sm text-warn">Couldn't load the model list. Check that the engine is running.</p>}
        {noModel && !providers.isError && <p className="text-sm text-warn">No healthy local model is available. Start the local model server, or choose a model in Settings, then reload this page.</p>}
      </GlassPanel>

      {narrative && !approved && !gate.ok && <p className="text-sm text-warn">{gate.reason}</p>}
      {error && <p role="alert" className="text-sm text-bad">{error}</p>}
      {notice && <p role="status" className="text-sm text-fg-dim">{notice}</p>}

      {analyzing && (
        <GlassPanel blur={false} className="grid grid-cols-1 gap-3 p-4">
          <JobProgress job={job.data} idleLabel="Starting the story analysis." />
          {job.isError && (
            <p className="flex flex-wrap items-center gap-3 text-sm text-warn">
              Lost contact with the engine. The analysis may still be running.
              <Button size="sm" variant="secondary" onClick={() => void job.refetch()}>Check again</Button>
            </p>
          )}
          <AnalysisActivity job={job.data ?? null} />
          {jobId && <div><Button variant="ghost" size="sm" loading={cancelling} onClick={() => void cancel()}>Cancel analysis</Button></div>}
        </GlassPanel>
      )}

      {blocking.length > 0 && (
        <p role="alert" className="rounded-ctl border border-bad/40 bg-bad/10 p-3 text-sm text-bad">{`${blocking.length} continuity error${blocking.length === 1 ? "" : "s"} must be resolved before the story can be approved.`}</p>
      )}

      {narrativeQuery.isLoading ? (
        <Skeleton className="h-64" />
      ) : !narrative ? (
        <GlassPanel blur={false}><EmptyState title="No story analysis yet" description="Run the story analysis to find the characters, scenes and dialogue in this chapter." /></GlassPanel>
      ) : (
        <Tabs value={tab} onValueChange={setTab} tabs={tabs}>
          {tab === "characters" && <CharactersTab projectId={project.id} characters={characters} utterances={narrative.utterances ?? []} panels={panels} onChanged={reload} />}
          {tab === "scenes" && <ScenesTab blocks={blocks} panels={panels} />}
          {tab === "utterances" && <UtterancesTab projectId={project.id} utterances={narrative.utterances ?? []} characters={characters} panels={panels} onChanged={reload} />}
          {tab === "continuity" && <ContinuityTab warnings={narrative.continuity_warnings ?? []} />}
        </Tabs>
      )}

      <ConfirmDialog
        open={confirmReplace}
        title="Replace the current analysis?"
        description="Analysing again writes a new story from the panels and replaces the current characters, scenes and dialogue, including your edits."
        confirmLabel="Re-analyze story"
        onConfirm={() => { setConfirmReplace(false); void run(); }}
        onCancel={() => setConfirmReplace(false)}
      />
    </div>
  );
};
