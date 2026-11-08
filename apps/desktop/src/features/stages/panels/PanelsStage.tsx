import React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Film, Redo2, Undo2 } from "lucide-react";
import { api } from "@panelflow/api-client";
import type { Page, Panel, Project } from "@panelflow/shared-types";
import { Button, Chip, EmptyState, ErrorState, GlassPanel, Select, Skeleton, useToast } from "@panelflow/ui-v2";
import { historyShortcut } from "../../../history/shortcuts";
import { useError } from "../../../context/ErrorContext";
import { PageCanvas, type CanvasBox } from "../kit/canvas/PageCanvas";
import { ConfirmDialog } from "../kit/ConfirmDialog";
import { JobProgress } from "../kit/JobProgress";
import { StageToolbar } from "../kit/StageToolbar";
import { refusal } from "../kit/engineReason";
import { stageKeys, usePages } from "../kit/stageData";
import { useFollowedJob } from "../kit/useFollowedJob";
import { PageStrip } from "./PageStrip";
import { panelKeys, usePanels, useProjectHistory } from "./panelsData";
import { canConfirmPanels, historyAvailability, isPanelsConfirmed, pageCounts, panelStatus, panelsOnPage } from "./panelsModel";

export interface PanelsStageProps {
  project: Project;
  /** Called with the reloaded project after the panels are confirmed. */
  onConfirmed: (updated: Project) => void;
  /** Move on to OCR (already confirmed). */
  onContinue: (project: Project) => void;
  onOpenStoryEditor: (project: Project) => void;
}

const DETECT_ADVICE = "Check the engine log in Diagnostics, then try again.";
const FALLBACK_SIZE = { w: 1920, h: 2400 };

/** Fit the canvas to the width of its container. Before it can be measured (and in tests) a fixed fraction is used. */
function useFitZoom(imageWidth: number) {
  const ref = React.useRef<HTMLDivElement | null>(null);
  const [width, setWidth] = React.useState(0);
  React.useEffect(() => {
    const el = ref.current;
    if (!el || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => setWidth(el.clientWidth));
    observer.observe(el);
    setWidth(el.clientWidth);
    return () => observer.disconnect();
  }, []);
  return { ref, zoom: width > 0 ? Math.max(5, Math.floor((width / imageWidth) * 100)) : 40 };
}

/** Panels: detect panels on every page, fix them on the page, and confirm. Undo and redo are the engine's. */
export const PanelsStage: React.FC<PanelsStageProps> = ({ project, onConfirmed, onContinue, onOpenStoryEditor }) => {
  const queryClient = useQueryClient();
  const toast = useToast();
  const { reportError } = useError();

  const pagesQuery = usePages(project.id);
  const pages = React.useMemo(() => [...(pagesQuery.data ?? [])].sort((a, b) => a.sequence - b.sequence), [pagesQuery.data]);
  const panelsQuery = usePanels(project.id);
  const panels = panelsQuery.data ?? [];
  const counts = React.useMemo(() => pageCounts(panels, pages), [panels, pages]);
  const confirmed = isPanelsConfirmed(project.current_stage);
  const gate = canConfirmPanels(panels);

  const [pageIndex, setPageIndex] = React.useState(0);
  const [selectedId, setSelectedId] = React.useState<string | null>(null);
  const [direction, setDirection] = React.useState<"ltr" | "rtl">("ltr");
  const [cacheBuster, setCacheBuster] = React.useState(() => Date.now());
  const [loaded, setLoaded] = React.useState<{ pageId: string; w: number; h: number } | null>(null);
  const [error, setError] = React.useState<string | null>(null);
  const [notice, setNotice] = React.useState<string | null>(null);
  const [confirmDetect, setConfirmDetect] = React.useState(false);
  const [confirming, setConfirming] = React.useState(false);
  const [detectingPage, setDetectingPage] = React.useState(false);
  const busy = React.useRef(false);
  const history = useProjectHistory(project.id);
  const historyBusy = React.useRef(false);
  const [historyWorking, setHistoryWorking] = React.useState(false);
  const availability = historyAvailability(history.history, historyWorking);

  const activePage: Page | undefined = pages[Math.min(pageIndex, Math.max(0, pages.length - 1))];
  const pagePanels = activePage ? panelsOnPage(panels, activePage.id) : [];
  const size = activePage && loaded?.pageId === activePage.id ? { w: loaded.w, h: loaded.h } : activePage?.width && activePage?.height ? { w: activePage.width, h: activePage.height } : FALLBACK_SIZE;
  const fit = useFitZoom(size.w);

  const reloadPanels = () => queryClient.invalidateQueries({ queryKey: panelKeys.list(project.id) });

  // Detection and normalisation are jobs: follow one that was started here or was already running when the stage opened.
  const followed = useFollowedJob({
    projectId: project.id,
    types: ["PANEL_DETECTION", "NORMALIZATION"],
    onDone: (job) => {
      const detecting = job.job_type === "PANEL_DETECTION";
      if (job.status === "SUCCEEDED") {
        void reloadPanels();
        void queryClient.invalidateQueries({ queryKey: stageKeys.pages(project.id) });
        setCacheBuster(Date.now());
        toast.show(detecting ? "Panels detected." : "Pages normalized.");
      } else if (job.status === "CANCELLED") {
        setNotice(detecting ? "Detection cancelled." : "Normalization cancelled.");
      } else {
        setError(refusal(detecting ? "Couldn't detect the panels." : "Couldn't normalize the pages.", new Error(job.error ?? ""), DETECT_ADVICE));
        reportError({ title: detecting ? "Panel Detection Failed" : "Page Normalization Failed", message: job.error || job.message || "The job failed.", severity: "error", source: "pipeline", projectId: project.id, jobType: job.job_type, rawDetails: job });
      }
    },
  });

  const startJob = async (start: () => Promise<{ job_id: string }>, failure: string, title: string, jobType: string) => {
    if (busy.current || followed.active) return;
    busy.current = true;
    setError(null);
    setNotice(null);
    try { followed.follow((await start()).job_id); }
    catch (err: any) {
      setError(`${failure} Check that the engine is running, then try again.`);
      reportError({ title, message: failure, severity: "error", source: "pipeline", projectId: project.id, jobType, rawDetails: err });
    } finally { busy.current = false; }
  };
  const detect = () => startJob(() => api.detectPanels(project.id, direction, 0.02), "Couldn't start the detection.", "Panel Detection Failed", "PANEL_DETECTION");
  const normalize = () => startJob(() => api.normalizeProject(project.id, 1920), "Couldn't start the normalization.", "Page Normalization Failed", "NORMALIZATION");

  const detectThisPage = async () => {
    if (!activePage || busy.current || followed.active) return;
    busy.current = true;
    setDetectingPage(true);
    setError(null);
    try {
      const found = await api.detectPagePanels(project.id, activePage.id, direction);
      queryClient.setQueryData<Panel[]>(panelKeys.list(project.id), (all) => [...(all ?? []).filter((p) => p.page_id !== activePage.id), ...found]);
      setCacheBuster(Date.now());
      history.refresh();
    } catch (err: any) {
      setError("Couldn't detect the panels on this page. Check that the engine is running, then try again.");
      reportError({ title: "Panel Detection Failed", message: "Error running automatic panel extraction.", severity: "error", source: "pipeline", projectId: project.id, jobType: "PANEL_DETECTION", rawDetails: err });
    } finally { busy.current = false; setDetectingPage(false); }
  };

  const confirm = async () => {
    if (busy.current || !gate.ok) return;
    busy.current = true;
    setConfirming(true);
    setError(null);
    try {
      await api.confirmPanels(project.id);
      onConfirmed(await api.getProject(project.id));
    } catch (err: any) {
      setError(refusal("Panels can't be confirmed yet.", err, "Fix the panels, then try again."));
      reportError({ title: "Panel Confirmation Failed", message: "Could not confirm detected panels.", severity: "error", source: "pipeline", projectId: project.id, rawDetails: err });
    } finally { busy.current = false; setConfirming(false); }
  };

  const moveHistory = async (direction: "undo" | "redo") => {
    if (historyBusy.current) return;
    const known = api.getCachedProjectHistory(project.id);
    if (known && !(direction === "undo" ? known.canUndo : known.canRedo)) { history.setHistory(known); return; }
    historyBusy.current = true;
    setHistoryWorking(true);
    setError(null);
    try {
      const reply = direction === "undo" ? await api.undo(project.id) : await api.redo(project.id);
      history.setHistory(reply.history ?? api.getCachedProjectHistory(project.id));
      await reloadPanels();
      setCacheBuster(Date.now());
    } catch (err: any) {
      history.refresh();
      setError(`Couldn't ${direction} that. Reload the page if this keeps happening.`);
      reportError({ title: direction === "undo" ? "Undo Failed" : "Redo Failed", message: `Could not ${direction} project state.`, severity: "warning", source: "pipeline", projectId: project.id, rawDetails: err });
    } finally { historyBusy.current = false; setHistoryWorking(false); }
  };

  // Keyboard: Ctrl+Z / Ctrl+Y for history, Left and Right for pages. Text fields and dialogs keep their own keys.
  React.useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const target = event.target as HTMLElement | null;
      if (event.defaultPrevented || ["INPUT", "TEXTAREA", "SELECT"].includes(target?.tagName ?? "") || target?.isContentEditable || target?.closest?.("[role=dialog]")) return;
      const action = historyShortcut(event);
      if (action) { event.preventDefault(); void moveHistory(action); return; }
      if (event.key === "ArrowLeft" && !event.shiftKey) { setPageIndex((i) => Math.max(0, i - 1)); setSelectedId(null); }
      else if (event.key === "ArrowRight" && !event.shiftKey) { setPageIndex((i) => Math.min(pages.length - 1, i + 1)); setSelectedId(null); }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [pages.length]); // eslint-disable-line react-hooks/exhaustive-deps

  const canvasBoxes: CanvasBox[] = pagePanels.map((p) => ({
    id: p.id, box: { x: p.x, y: p.y, w: p.width, h: p.height }, label: `Panel ${p.page_sequence}`, tone: panelStatus(p.status).tone === "neutral" ? "neutral" : (panelStatus(p.status).tone as CanvasBox["tone"]), locked: p.status === "IGNORED",
  }));
  const statusChip = confirmed ? <Chip tone="ok">Confirmed</Chip> : panels.length > 0 ? <Chip tone="accent">Needs confirming</Chip> : <Chip>No panels</Chip>;

  if (pagesQuery.isError || panelsQuery.isError) return <ErrorState title="Couldn't load the panels" description="Check that the engine is running, then try again." onRetry={() => { void pagesQuery.refetch(); void panelsQuery.refetch(); }} />;

  return (
    <div className="grid grid-cols-1 gap-5">
      <StageToolbar
        title="Review panels"
        description="Detect the panels on every page, fix any that are wrong, then confirm."
        status={statusChip}
        actions={
          <>
            <Button variant="ghost" size="sm" icon={<Undo2 size={14} />} title="Undo (Ctrl+Z)" disabled={!availability.canUndo} onClick={() => void moveHistory("undo")}>Undo</Button>
            <Button variant="ghost" size="sm" icon={<Redo2 size={14} />} title="Redo (Ctrl+Y)" disabled={!availability.canRedo} onClick={() => void moveHistory("redo")}>Redo</Button>
            <Button variant="secondary" size="sm" disabled={panels.length === 0} icon={<Film size={14} />} onClick={() => onOpenStoryEditor(project)}>Open story editor</Button>
            {confirmed && <Button variant="secondary" size="sm" onClick={() => onContinue(project)}>Continue to OCR</Button>}
            <Button variant="primary" size="sm" loading={confirming} disabled={!gate.ok} onClick={() => void confirm()}>Confirm panels</Button>
          </>
        }
      />

      <GlassPanel blur={false} className="flex flex-wrap items-end gap-3 p-4">
        <label className="grid gap-1.5 text-[13px] font-medium text-fg">
          Reading direction
          <Select aria-label="Reading direction" className="h-9 w-56 text-sm" value={direction} onChange={(e) => setDirection(e.target.value as "ltr" | "rtl")}>
            <option value="ltr">Left to right</option>
            <option value="rtl">Right to left (manga)</option>
          </Select>
        </label>
        <Button variant="secondary" size="sm" disabled={followed.active} title="Standardize the resolution and colour space without changing the originals" onClick={() => void normalize()}>Normalize pages</Button>
        <Button variant="secondary" size="sm" disabled={followed.active} title="Pages with manual edits, approved panels or panels linked to video scenes are preserved" onClick={() => (panels.length > 0 ? setConfirmDetect(true) : void detect())}>Detect panels</Button>
        <Button variant="secondary" size="sm" loading={detectingPage} disabled={followed.active || !activePage} onClick={() => void detectThisPage()}>Detect this page</Button>
      </GlassPanel>

      {!gate.ok && panels.length > 0 && <p className="text-sm text-warn">{gate.reason}</p>}
      {!gate.ok && panels.length === 0 && pages.length > 0 && <p className="text-sm text-warn">{gate.reason}</p>}
      {availability.blocked && <p className="text-sm text-warn">{availability.blocked}</p>}
      {error && <p role="alert" className="text-sm text-bad">{error}</p>}
      {notice && <p role="status" className="text-sm text-fg-dim">{notice}</p>}
      {followed.active && (
        <GlassPanel blur={false} className="grid grid-cols-1 gap-2 p-4" role="status">
          <JobProgress job={followed.job} idleLabel="Starting." />
          {followed.lost && <p className="flex flex-wrap items-center gap-3 text-sm text-warn">Lost contact with the engine. The job may still be running.<Button size="sm" variant="secondary" onClick={followed.check}>Check again</Button></p>}
        </GlassPanel>
      )}

      {pagesQuery.isLoading || panelsQuery.isLoading ? (
        <Skeleton className="h-72" />
      ) : pages.length === 0 ? (
        <GlassPanel blur={false}><EmptyState title="No pages yet" description="Go back to Acquire and download the pages first." /></GlassPanel>
      ) : (
        <>
          <PageStrip pages={pages} perPage={counts.perPage} selectedIndex={pageIndex} onSelect={(i) => { setPageIndex(i); setSelectedId(null); }} />
          {pagePanels.length === 0 && <p className="text-sm text-fg-dim">No panels on this page. Use Detect this page, or draw one.</p>}
          <div ref={fit.ref} className="min-w-0">
            {activePage && (
              <PageCanvas
                key={activePage.id}
                className="h-[70vh]"
                image={{ src: `${api.getNormalizedPageImageUrl(project.id, activePage.id)}?t=${cacheBuster}`, width: size.w, height: size.h, alt: `Page ${activePage.sequence}` }}
                boxes={canvasBoxes}
                selectedId={selectedId}
                zoom={fit.zoom}
                editable={false}
                onSelect={(id) => setSelectedId(id)}
                onImageSize={(w, h) => setLoaded({ pageId: activePage.id, w, h })}
              />
            )}
          </div>
        </>
      )}

      <ConfirmDialog
        open={confirmDetect}
        title="Detect again?"
        description="Detection runs on every page. Pages with manual edits, approved panels or panels linked to video scenes are preserved."
        confirmLabel="Detect panels"
        onConfirm={() => { setConfirmDetect(false); void detect(); }}
        onCancel={() => setConfirmDetect(false)}
      />
    </div>
  );
};
