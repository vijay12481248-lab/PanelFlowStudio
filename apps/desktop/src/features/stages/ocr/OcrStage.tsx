import React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Film, Redo2, Undo2 } from "lucide-react";
import { api } from "@panelflow/api-client";
import type { Project } from "@panelflow/shared-types";
import { Button, Chip, ErrorState, GlassPanel, Select, Skeleton, useToast } from "@panelflow/ui-v2";
import { historyShortcut } from "../../../history/shortcuts";
import { useError } from "../../../context/ErrorContext";
import { JobProgress } from "../kit/JobProgress";
import { StageToolbar } from "../kit/StageToolbar";
import { browserDownload } from "../kit/download";
import { refusal } from "../kit/engineReason";
import { isTyping } from "../kit/typing";
import { useFollowedJob } from "../kit/useFollowedJob";
import { useHistoryMoves } from "../kit/useHistoryMoves";
import { panelKeys, usePanels } from "../panels/panelsData";
import { GateBanner } from "./GateBanner";
import { ocrKeys, useOcrEngines, useTextRegions } from "./ocrData";
import { canConfirmOCR, confirmPatch, engineProblem, needsReview, pickEngine } from "./ocrModel";

export interface OcrStageProps {
  project: Project;
  /** Called with the reloaded project after the text is approved. */
  onApproved: (updated: Project) => void;
  onContinue: (project: Project) => void;
  onOpenStoryEditor: (project: Project) => void;
  /** Saves text as a file. Replaced in tests. */
  download?: (filename: string, content: string) => void;
}

const OCR_APPROVED = new Set(["OCR_CONFIRMED", "STORY_ANALYZED", "STORY_CONFIRMED", "SCRIPT_GENERATED", "SCRIPT_APPROVED", "AUDIO_GENERATED", "AUDIO_APPROVED", "MOTION_PLANNED", "MOTION_APPROVED", "RENDERED"]);

/** OCR: find the text in every panel, read it, fix it, and approve it. Undo and redo are the engine's. */
export const OcrStage: React.FC<OcrStageProps> = ({ project, onApproved, onContinue, onOpenStoryEditor, download = browserDownload }) => {
  const queryClient = useQueryClient();
  const toast = useToast();
  const { reportError } = useError();

  const regionsQuery = useTextRegions(project.id);
  const regions = regionsQuery.data ?? [];
  const panelsQuery = usePanels(project.id);
  const enginesQuery = useOcrEngines();
  const engines = enginesQuery.data ?? [];

  const [chosenEngine, setChosenEngine] = React.useState<string | null>(null);
  const engineId = chosenEngine ?? pickEngine(engines);
  const problem = enginesQuery.data ? engineProblem(engines) : null;
  const approved = OCR_APPROVED.has(project.current_stage);

  const [error, setError] = React.useState<string | null>(null);
  const [notice, setNotice] = React.useState<string | null>(null);
  const [working, setWorking] = React.useState<null | "detect" | "confirm" | "approve" | "export">(null);
  const [progress, setProgress] = React.useState<string | null>(null);
  const busy = React.useRef(false);
  const reloadRegions = () => queryClient.invalidateQueries({ queryKey: ocrKeys.regions(project.id) });

  const followed = useFollowedJob({
    projectId: project.id,
    types: ["OCR_EXTRACTION"],
    onDone: (job) => {
      if (job.status === "SUCCEEDED") { void reloadRegions(); toast.show("Text read."); }
      else if (job.status === "CANCELLED") setNotice("Reading the text was cancelled.");
      else {
        setError(refusal("Couldn't read the text.", new Error(job.error ?? ""), "Check the engine log in Diagnostics, then try again."));
        reportError({ title: "OCR Extraction Failed", message: job.error || job.message || "The job failed.", severity: "error", source: "pipeline", projectId: project.id, jobType: job.job_type, rawDetails: job as unknown as Record<string, any> });
      }
    },
  });

  const history = useHistoryMoves(project.id, {
    onMoved: async () => { await Promise.all([reloadRegions(), queryClient.invalidateQueries({ queryKey: panelKeys.list(project.id) })]); },
    onFailed: (which, err) => {
      setError(`Couldn't ${which} that. Reload the page if this keeps happening.`);
      reportError({ title: which === "undo" ? "Undo Failed" : "Redo Failed", message: `Could not ${which} project state.`, severity: "warning", source: "pipeline", projectId: project.id, rawDetails: err as Record<string, any> });
    },
  });

  /** One action at a time. A failure becomes a sentence; `task` returns a notice to show when it worked. */
  const run = async (kind: NonNullable<typeof working>, failure: string, task: () => Promise<string | void>) => {
    if (busy.current || followed.active) return;
    busy.current = true;
    setWorking(kind);
    setError(null);
    setNotice(null);
    try { const done = await task(); if (done) setNotice(done); }
    catch (err) { setError(refusal(failure, err)); }
    finally { busy.current = false; setWorking(null); setProgress(null); }
  };

  const detect = () => run("detect", "Couldn't detect the text regions.", async () => { await api.detectTextRegions(project.id); await reloadRegions(); });
  const read = async () => {
    if (!engineId || busy.current || followed.active) return;
    busy.current = true;
    setError(null);
    setNotice(null);
    try { followed.follow((await api.extractOCR(project.id, engineId, "en")).job_id); }
    catch (err) { setError(refusal("Couldn't start reading the text.", err)); }
    finally { busy.current = false; }
  };
  const confirmAll = () => run("confirm", "Couldn't confirm the regions.", async () => {
    const pending = needsReview(regions);
    const ready = pending.map((r) => ({ r, patch: confirmPatch(r) })).filter((x): x is { r: typeof pending[number]; patch: NonNullable<ReturnType<typeof confirmPatch>> } => x.patch !== null);
    const left = pending.length - ready.length;
    let done = 0;
    try {
      for (const { r, patch } of ready) {
        setProgress(`Confirming ${done + 1} of ${ready.length}`);
        await api.updateTextRegion(project.id, r.id, patch);
        done++;
      }
    } catch (err) {
      await reloadRegions();
      throw new Error(`${done} confirmed, then it stopped. ${refusal("", err, "Try again.").trim()}`);
    }
    await reloadRegions();
    return `${done} confirmed${left > 0 ? `, ${left} left because they have no text` : ""}.`;
  });
  const gate = canConfirmOCR({ regions, running: followed.active });
  const approve = () => {
    if (!gate.ok) return;
    return run("approve", "Text can't be approved yet.", async () => {
      await api.confirmOCR(project.id);
      onApproved(await api.getProject(project.id));
    });
  };
  const exportContract = () => run("export", "Couldn't export the contract.", async () => {
    const contract = await api.getCanonicalExportContract(project.id);
    download(`ocr_contract_${project.id}.json`, JSON.stringify(contract, null, 2));
  });

  const keys = React.useRef<(e: KeyboardEvent) => void>(() => {});
  keys.current = (event) => {
    if (event.defaultPrevented || isTyping(event.target as HTMLElement | null)) return;
    const action = historyShortcut(event);
    if (action) { event.preventDefault(); void history.move(action); }
  };
  React.useEffect(() => {
    const onKey = (event: KeyboardEvent) => keys.current(event);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (regionsQuery.isError || panelsQuery.isError) return <ErrorState title="Couldn't load the text" description="Check that the engine is running, then try again." onRetry={() => { void regionsQuery.refetch(); void panelsQuery.refetch(); }} />;

  const statusChip = approved ? <Chip tone="ok">Approved</Chip> : regions.length > 0 ? <Chip tone="accent">Needs approving</Chip> : <Chip>No text yet</Chip>;
  const availability = history.availability;

  return (
    <div className="grid grid-cols-1 gap-5">
      <StageToolbar
        title="Review the text"
        description="Detect the text in each panel, read it, correct it, then approve it."
        status={statusChip}
        actions={
          <>
            <Button variant="ghost" size="sm" icon={<Undo2 size={14} />} title="Undo (Ctrl+Z)" disabled={!availability.canUndo} onClick={() => void history.move("undo")}>Undo</Button>
            <Button variant="ghost" size="sm" icon={<Redo2 size={14} />} title="Redo (Ctrl+Y)" disabled={!availability.canRedo} onClick={() => void history.move("redo")}>Redo</Button>
            <Button variant="secondary" size="sm" disabled={working === "export"} loading={working === "export"} onClick={() => void exportContract()}>Export contract</Button>
            <Button variant="secondary" size="sm" icon={<Film size={14} />} onClick={() => onOpenStoryEditor(project)}>Open story editor</Button>
            {approved && <Button variant="secondary" size="sm" onClick={() => onContinue(project)}>Continue to story</Button>}
            <Button variant="primary" size="sm" loading={working === "approve"} disabled={!gate.ok || working !== null} onClick={() => void approve()}>Approve text</Button>
          </>
        }
      />

      <GlassPanel blur={false} className="flex flex-wrap items-end gap-3 p-4">
        <label className="grid gap-1.5 text-[13px] font-medium text-fg">
          OCR engine
          <Select aria-label="OCR engine" className="h-9 w-64 text-sm" value={engineId ?? ""} onChange={(e) => setChosenEngine(e.target.value)}>
            {engineId === null && <option value="">No engine available</option>}
            {engines.map((e) => <option key={e.engine_id} value={e.engine_id} disabled={!e.is_available}>{e.is_available ? e.display_name : `${e.display_name} (Not installed)`}</option>)}
          </Select>
        </label>
        <Button variant="secondary" size="sm" loading={working === "detect"} disabled={working !== null || followed.active} onClick={() => void detect()}>Detect text regions</Button>
        <Button variant="secondary" size="sm" disabled={!engineId || working !== null || followed.active} title="Read the text of every region with the chosen engine" onClick={() => void read()}>Read text</Button>
        <Button variant="secondary" size="sm" loading={working === "confirm"} disabled={working !== null || followed.active || needsReview(regions).length === 0} title="Confirm the regions that already have text. Regions without text are left for you." onClick={() => void confirmAll()}>Confirm all with text</Button>
      </GlassPanel>

      {problem && <p className="text-sm text-warn">{problem}</p>}
      {!gate.ok && regions.length > 0 && <p className="text-sm text-warn">{gate.reason}</p>}
      {availability.blocked && <p className="text-sm text-warn">{availability.blocked}</p>}
      {error && <p role="alert" className="text-sm text-bad">{error}</p>}
      {notice && <p role="status" className="text-sm text-fg-dim">{notice}</p>}
      {progress && <p role="status" className="text-sm text-fg-dim">{progress}</p>}
      {followed.active && (
        <GlassPanel blur={false} className="grid grid-cols-1 gap-2 p-4" role="status">
          <JobProgress job={followed.job} idleLabel="Starting." />
          {followed.lost && <p className="flex flex-wrap items-center gap-3 text-sm text-warn">Lost contact with the engine. The job may still be running.<Button size="sm" variant="secondary" onClick={followed.check}>Check again</Button></p>}
        </GlassPanel>
      )}

      {regionsQuery.isLoading || panelsQuery.isLoading ? (
        <Skeleton className="h-72" />
      ) : regions.length === 0 ? (
        <p className="text-sm text-fg-dim">No text regions yet. Detect text regions to find the text in the panels.</p>
      ) : (
        <GateBanner regions={regions} onJump={() => {}} />
      )}
    </div>
  );
};
