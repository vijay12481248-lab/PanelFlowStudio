import React from "react";
import { useSearchParams } from "react-router";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api } from "@panelflow/api-client";
import type { SceneProposal, SceneRun } from "@panelflow/api-client";
import { Button, EmptyState, ErrorState, GlassPanel, PageHeader, Select, Skeleton } from "@panelflow/ui-v2";
import { useEngine } from "../../app/providers";
import { AiReviewPanel } from "./AiReviewPanel";
import { OwnerPanel } from "./OwnerPanel";
import { sceneKeys } from "./sceneQueries";
import { analysisOverdue, ANGLES, itemRows, STATES } from "./sceneView";

const PROJECT_TITLE = "Scene Director";
const TERMINAL = new Set(["SUCCEEDED", "FAILED", "CANCELLED"]);

/** Brief -> plan (editable) -> picture, then the review of the picture: the AI judges' view next to the owner's verdict. */
const CreatePanel: React.FC<{ pollMs: number; onDone: (runId: string) => void }> = ({ pollMs, onDone }) => {
  const [brief, setBrief] = React.useState("");
  const [proposal, setProposal] = React.useState<{ plan: SceneProposal["plan"]; summary: string } | null>(null);
  const [busy, setBusy] = React.useState<"plan" | "correct" | "draw" | null>(null);
  const [jobId, setJobId] = React.useState<string | null>(null);
  const [error, setError] = React.useState<string | null>(null);

  const job = useQuery({
    queryKey: ["scene-job", jobId],
    queryFn: () => api.getJob(jobId as string),
    enabled: Boolean(jobId),
    refetchInterval: (q) => (q.state.data && TERMINAL.has(q.state.data.status) ? false : pollMs),
    retry: false,
  });
  React.useEffect(() => {
    const j = job.data;
    if (!j || !TERMINAL.has(j.status)) return;
    setJobId(null);
    setBusy(null);
    if (j.status === "SUCCEEDED" && j.output?.run_id) onDone(String(j.output.run_id));
    else setError(j.status === "SUCCEEDED" ? "The picture was made but could not be saved for review." : (j.error ?? `The job ${j.status.toLowerCase()}.`));
  }, [job.data, onDone]);

  const guard = async (kind: "plan" | "correct" | "draw", fn: () => Promise<void>) => {
    setBusy(kind);
    setError(null);
    try {
      await fn();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Something went wrong");
      setBusy(null);
      return;
    }
    if (kind !== "draw") setBusy(null);
  };

  const plan = proposal?.plan;
  const states = STATES[plan?.scene_type as string] ?? [];
  const correct = (path: string, value: string) =>
    guard("correct", async () => { if (plan) setProposal(await api.sceneCorrect(plan, { [path]: value })); });

  const draw = () => guard("draw", async () => {
    if (!plan) return;
    const projects = await api.listProjects();
    const project = projects.find((p) => p.title === PROJECT_TITLE)
      ?? (await api.createProject({ title: PROJECT_TITLE, source_type: "CHRONOFLOW_AI", rights_status: "USER_OWNED" } as unknown as Parameters<typeof api.createProject>[0]));
    const started = await api.sceneGenerate(project.id, plan);
    setJobId(started.job_id);
  });

  return (
    <GlassPanel className="grid gap-3 p-4" aria-label="Make a picture">
      <h2 className="font-display text-base font-semibold text-fg">Make a picture</h2>
      <span className="text-sm text-fg-dim">Describe the picture in a sentence. The system plans it and asks only what it needs.</span>
      <textarea
        aria-label="Describe the picture" rows={2} maxLength={1000} value={brief} onChange={(e) => setBrief(e.currentTarget.value)}
        placeholder="e.g. the hero fights the villain"
        className="w-full rounded-ctl border border-edge bg-glass px-3 py-2 text-sm text-fg placeholder:text-fg-faint"
      />
      <div>
        <Button disabled={!brief.trim() || busy !== null} loading={busy === "plan"} onClick={() => void guard("plan", async () => { setProposal(await api.sceneProposal(brief.trim())); })}>Plan it</Button>
      </div>
      {proposal && plan && (
        <div className="grid gap-3">
          <p className="text-sm text-fg">{proposal.summary}</p>
          <div className="flex flex-wrap gap-3">
            <label className="grid gap-1 text-xs text-fg-dim">
              Camera angle
              <Select aria-label="Camera angle" value={plan.camera?.angle} disabled={busy !== null} onChange={(e) => void correct("camera.angle", e.currentTarget.value)}>
                {ANGLES.map((a) => <option key={a.value} value={a.value}>{a.label}</option>)}
              </Select>
            </label>
            {(plan.actors ?? []).map((a: { id: string; action_state: string }) => (
              <label key={a.id} className="grid gap-1 text-xs text-fg-dim">
                {a.id}
                <Select aria-label={`${a.id} action`} value={a.action_state} disabled={busy !== null} onChange={(e) => void correct(`actors.${a.id}.action_state`, e.currentTarget.value)}>
                  {states.map((s) => <option key={s} value={s}>{s}</option>)}
                </Select>
              </label>
            ))}
          </div>
          <div>
            <Button disabled={busy !== null} loading={busy === "draw"} onClick={() => void draw()}>Draw it</Button>
            {busy === "draw" && <span className="ml-3 text-sm text-fg-dim">Drawing, checking and asking the two judges: about two minutes.</span>}
          </div>
        </div>
      )}
      {error && <p className="text-sm text-bad" role="alert">{error}</p>}
    </GlassPanel>
  );
};

/** One picture with the AI review and the owner's verdict; remounted per run so the owner's choices never leak from one picture to the next. */
const RunView: React.FC<{ run: SceneRun; onSaved: (run: SceneRun) => void; onDismissed: () => void }> = ({ run, onSaved, onDismissed }) => {
  const [choices, setChoices] = React.useState<Record<string, string>>(run.feedback?.item_verdicts ?? {});
  const onChoose = (key: string, value: string) =>
    setChoices((c) => {
      const next = { ...c };
      if (next[key] === value) delete next[key];
      else next[key] = value;
      return next;
    });
  const usable = Boolean(run.analysis) && !run.analysis?.error && itemRows(run.analysis?.crosscheck as never).length > 0;
  return (
    <div className="grid gap-5">
      <GlassPanel className="grid gap-2 p-3">
        <img src={api.sceneRunImageUrl(run.id)} alt="Generated picture" className="max-h-[32rem] w-full rounded-ctl object-contain" />
        <p className="px-1 text-xs text-fg-dim">{run.brief}</p>
      </GlassPanel>
      <AiReviewPanel run={run} choices={choices} onChoose={onChoose} overdue={analysisOverdue(run)} />
      <OwnerPanel run={run} choices={choices} usable={usable} onSaved={onSaved} onDismissed={onDismissed} />
    </div>
  );
};

export const ScenePage: React.FC<{ pollMs?: number }> = ({ pollMs = 3000 }) => {
  const engine = useEngine();
  const client = useQueryClient();
  const [params, setParams] = useSearchParams();
  const runId = params.get("run");

  const queue = useQuery({ queryKey: sceneKeys.runs, queryFn: () => api.listSceneRuns({ unreviewed: true, limit: 20 }), enabled: engine.connected, refetchInterval: 8000, retry: false });
  const run = useQuery({
    queryKey: sceneKeys.run(runId ?? ""),
    queryFn: () => api.getSceneRun(runId as string),
    enabled: Boolean(runId) && engine.connected,
    refetchInterval: (q) => (q.state.data && !q.state.data.analysis && !analysisOverdue(q.state.data) ? pollMs : false), // the judges are still working: keep looking, but not forever
    retry: false,
  });

  const open = (id: string | null) => setParams(id ? { run: id } : {}, { replace: false });
  const refresh = () => { void client.invalidateQueries({ queryKey: sceneKeys.runs }); void client.invalidateQueries({ queryKey: sceneKeys.unreviewed }); };
  const afterSaved = (saved: SceneRun) => {
    client.setQueryData(sceneKeys.run(saved.id), saved);
    refresh();
  };
  const waiting = (queue.data?.items ?? []).filter((r) => r.id !== runId);

  return (
    <div className="mx-auto grid w-full max-w-6xl gap-5 p-6 md:p-8">
      <PageHeader title="Scene Director" meta={<span>Make a picture, see what the two AI judges think, then give your verdict</span>} />
      <div className="grid gap-5 lg:grid-cols-[1fr_16rem]">
        <div className="grid min-w-0 gap-5">
          <CreatePanel pollMs={pollMs} onDone={(id) => { refresh(); open(id); }} />
          {runId && run.isLoading && <Skeleton className="h-64 w-full" />}
          {runId && run.isError && <ErrorState title="This picture could not be loaded" description="It may have been removed." onBack={() => open(null)} />}
          {run.data && (
            <RunView key={run.data.id} run={run.data} onSaved={afterSaved} onDismissed={() => { refresh(); const next = waiting[0]?.id ?? null; open(next); }} />
          )}
          {!runId && waiting.length === 0 && !queue.isLoading && (
            <EmptyState title="Nothing is waiting for your review." description="New pictures show up here, and as a banner on every screen, as soon as they are made." />
          )}
        </div>
        <aside className="grid content-start gap-2" aria-label="Waiting for review">
          <h2 className="font-display text-sm font-semibold text-fg">Waiting for your review ({queue.data?.total_unreviewed ?? 0})</h2>
          {waiting.map((r) => (
            <button key={r.id} type="button" onClick={() => open(r.id)} className="rounded-ctl border border-warn/50 bg-warn/10 px-3 py-2 text-left text-xs text-fg hover:bg-warn/20">
              <span className="line-clamp-2">{r.brief}</span>
            </button>
          ))}
        </aside>
      </div>
    </div>
  );
};
