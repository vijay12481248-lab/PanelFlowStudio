import React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { Film, PencilRuler, Redo2, Undo2, ZoomIn, ZoomOut } from "lucide-react";
import { api } from "@panelflow/api-client";
import type { Page, Panel, Project } from "@panelflow/shared-types";
import { Button, Chip, EmptyState, ErrorState, GlassPanel, Select, Skeleton, Switch, useToast } from "@panelflow/ui-v2";
import { historyShortcut } from "../../../history/shortcuts";
import { useError } from "../../../context/ErrorContext";
import type { Box } from "../kit/canvas/geometry";
import { PageCanvas, type CanvasBox } from "../kit/canvas/PageCanvas";
import { ConfirmDialog } from "../kit/ConfirmDialog";
import { JobProgress } from "../kit/JobProgress";
import { StageToolbar } from "../kit/StageToolbar";
import { refusal } from "../kit/engineReason";
import { stageKeys, usePages } from "../kit/stageData";
import { useFollowedJob } from "../kit/useFollowedJob";
import { AddPanelDialog } from "./AddPanelDialog";
import { PageStrip } from "./PageStrip";
import { PanelInspector } from "./PanelInspector";
import { PanelList } from "./PanelList";
import { panelKeys, usePanels, useProjectHistory } from "./panelsData";
import { canConfirmPanels, historyAvailability, isPanelsConfirmed, pageCounts, panelStatus, panelsOnPage } from "./panelsModel";
import { usePanelEditing } from "./usePanelEditing";

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

const isTyping = (target: HTMLElement | null) => ["INPUT", "TEXTAREA", "SELECT"].includes(target?.tagName ?? "") || Boolean(target?.isContentEditable) || Boolean(target?.closest?.("[role=dialog]"));

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
  const [mergeIds, setMergeIds] = React.useState<string[]>([]);
  const [draft, setDraft] = React.useState<Record<string, Box>>({});
  const [drawMode, setDrawMode] = React.useState(false);
  const [showBoxes, setShowBoxes] = React.useState(true);
  const [zoomMode, setZoomMode] = React.useState<"fit" | number>("fit");
  const [addOpen, setAddOpen] = React.useState(false);
  const [pendingDelete, setPendingDelete] = React.useState<Panel | null>(null);
  const [direction, setDirection] = React.useState<"ltr" | "rtl">("ltr");
  const [cacheBuster, setCacheBuster] = React.useState(() => Date.now()); // the page image: changes after detection, normalization or undo
  const [cropBuster, setCropBuster] = React.useState(() => Date.now()); // panel crops: change after every edit
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
  const selected = panels.find((p) => p.id === selectedId) ?? null;
  const size = activePage && loaded?.pageId === activePage.id ? { w: loaded.w, h: loaded.h } : activePage?.width && activePage?.height ? { w: activePage.width, h: activePage.height } : FALLBACK_SIZE;
  const fit = useFitZoom(size.w);
  const zoom = zoomMode === "fit" ? fit.zoom : zoomMode;

  const editing = usePanelEditing({ project, pages, onChanged: () => { history.refresh(); setCropBuster(Date.now()); } });
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
        setCropBuster(Date.now());
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
      setCropBuster(Date.now());
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

  const moveHistory = async (which: "undo" | "redo") => {
    if (historyBusy.current) return;
    const known = api.getCachedProjectHistory(project.id);
    if (known && !(which === "undo" ? known.canUndo : known.canRedo)) { history.setHistory(known); return; }
    historyBusy.current = true;
    setHistoryWorking(true);
    setError(null);
    try {
      const reply = which === "undo" ? await api.undo(project.id) : await api.redo(project.id);
      history.setHistory(reply.history ?? api.getCachedProjectHistory(project.id));
      await reloadPanels();
      setCacheBuster(Date.now());
      setCropBuster(Date.now());
    } catch (err: any) {
      history.refresh();
      setError(`Couldn't ${which} that. Reload the page if this keeps happening.`);
      reportError({ title: which === "undo" ? "Undo Failed" : "Redo Failed", message: `Could not ${which} project state.`, severity: "warning", source: "pipeline", projectId: project.id, rawDetails: err });
    } finally { historyBusy.current = false; setHistoryWorking(false); }
  };

  const select = (id: string | null, additive = false) => {
    if (additive && id) setMergeIds((ids) => (ids.includes(id) ? ids.filter((x) => x !== id) : [...ids, id]));
    else setSelectedId(id);
  };
  const cycle = (delta: 1 | -1) => {
    if (pagePanels.length === 0) return;
    const at = pagePanels.findIndex((p) => p.id === selectedId);
    setSelectedId(pagePanels[at < 0 ? (delta > 0 ? 0 : pagePanels.length - 1) : (at + delta + pagePanels.length) % pagePanels.length].id);
  };

  // Keyboard. Tab is left alone so the page can be walked with the keyboard. Text fields and dialogs keep their own keys.
  const keys = React.useRef<(e: KeyboardEvent) => void>(() => {});
  keys.current = (event) => {
    const target = event.target as HTMLElement | null;
    if (event.defaultPrevented || isTyping(target)) return;
    const action = historyShortcut(event);
    if (action) { event.preventDefault(); void moveHistory(action); return; }
    const onCanvas = Boolean(target?.closest?.("[data-canvas-overlay]"));
    if (event.key === "ArrowLeft" && !event.shiftKey && !onCanvas) { setPageIndex((i) => Math.max(0, i - 1)); setSelectedId(null); setMergeIds([]); }
    else if (event.key === "ArrowRight" && !event.shiftKey && !onCanvas) { setPageIndex((i) => Math.min(pages.length - 1, i + 1)); setSelectedId(null); setMergeIds([]); }
    else if (event.key === "[") { event.preventDefault(); cycle(-1); }
    else if (event.key === "]") { event.preventDefault(); cycle(1); }
    else if ((event.key === "Delete" || event.key === "Backspace") && selected) { event.preventDefault(); setPendingDelete(selected); }
    else if (event.key === "Escape") { setDrawMode(false); setSelectedId(null); setMergeIds([]); }
  };
  React.useEffect(() => {
    const onKey = (event: KeyboardEvent) => keys.current(event);
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  const commitMove = async (id: string, box: Box) => {
    const panel = panels.find((p) => p.id === id);
    if (panel) await editing.move(panel, box);
    setDraft((d) => { const next = { ...d }; delete next[id]; return next; }); // saved, or put back
  };
  const addBox = async (pageId: string, box: Box) => {
    const created = await editing.add(pageId, box);
    if (created) setSelectedId(created.id);
    return Boolean(created);
  };
  const reorderPage = (index: number, delta: -1 | 1) => {
    if (!activePage) return;
    const ids = pagePanels.map((p) => p.id);
    const [moved] = ids.splice(index, 1);
    ids.splice(index + delta, 0, moved);
    void editing.reorder(activePage.id, ids);
  };
  const doMerge = async () => {
    const merged = await editing.merge(mergeIds);
    if (merged) { setMergeIds([]); setSelectedId(merged.id); }
  };
  const doDelete = async () => {
    const panel = pendingDelete;
    setPendingDelete(null);
    if (panel && (await editing.remove(panel))) {
      setSelectedId((id) => (id === panel.id ? null : id));
      setMergeIds((ids) => ids.filter((x) => x !== panel.id));
    }
  };

  const canvasBoxes: CanvasBox[] = pagePanels.map((p) => {
    const tone = mergeIds.includes(p.id) ? "warn" : (panelStatus(p.status).tone as CanvasBox["tone"]);
    return { id: p.id, box: draft[p.id] ?? { x: p.x, y: p.y, w: p.width, h: p.height }, label: `Panel ${p.page_sequence}`, tone, locked: p.status === "IGNORED" };
  });
  const statusChip = confirmed ? <Chip tone="ok">Confirmed</Chip> : panels.length > 0 ? <Chip tone="accent">Needs confirming</Chip> : <Chip>No panels</Chip>;
  const failure = error ?? editing.error;

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

      {!gate.ok && pages.length > 0 && <p className="text-sm text-warn">{gate.reason}</p>}
      {availability.blocked && <p className="text-sm text-warn">{availability.blocked}</p>}
      {failure && <p role="alert" className="text-sm text-bad">{failure}</p>}
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
          <PageStrip pages={pages} perPage={counts.perPage} selectedIndex={pageIndex} onSelect={(i) => { setPageIndex(i); setSelectedId(null); setMergeIds([]); }} />
          {pagePanels.length === 0 && <p className="text-sm text-fg-dim">No panels on this page. Use Detect this page, or draw one.</p>}
          <div className="grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1fr)_340px]">
            <div className="grid min-w-0 content-start gap-3">
              <div className="flex flex-wrap items-center gap-2">
                <Button size="sm" variant="ghost" icon={<ZoomOut size={14} />} onClick={() => setZoomMode(Math.max(5, Math.round(zoom * 0.8)))}>Zoom out</Button>
                <Button size="sm" variant="ghost" onClick={() => setZoomMode("fit")}>Fit width</Button>
                <Button size="sm" variant="ghost" icon={<ZoomIn size={14} />} onClick={() => setZoomMode(Math.min(400, Math.round(zoom * 1.25)))}>Zoom in</Button>
                <span className="font-data text-xs text-fg-faint">{`${zoom}%`}</span>
                <Button size="sm" variant={drawMode ? "primary" : "secondary"} aria-pressed={drawMode} icon={<PencilRuler size={14} />} onClick={() => setDrawMode((on) => !on)}>Draw panel</Button>
                <Button size="sm" variant="secondary" onClick={() => setAddOpen(true)}>Add by numbers</Button>
                <Switch checked={showBoxes} onCheckedChange={setShowBoxes} label="Show boxes" />
              </div>
              <div ref={fit.ref} className="min-w-0">
                {activePage && (
                  <PageCanvas
                    key={activePage.id}
                    className="h-[70vh]"
                    image={{ src: `${api.getNormalizedPageImageUrl(project.id, activePage.id)}?t=${cacheBuster}`, width: size.w, height: size.h, alt: `Page ${activePage.sequence}` }}
                    boxes={canvasBoxes}
                    selectedId={selectedId}
                    zoom={zoom}
                    showBoxes={showBoxes}
                    drawMode={drawMode}
                    onSelect={select}
                    onChange={(id, box) => setDraft((d) => ({ ...d, [id]: box }))}
                    onCommit={(id, box) => void commitMove(id, box)}
                    onDraw={(box) => { setDrawMode(false); void addBox(activePage.id, box); }}
                    onImageSize={(w, h) => setLoaded({ pageId: activePage.id, w, h })}
                  />
                )}
              </div>
            </div>
            <div className="grid min-w-0 content-start gap-4">
              {selected && (
                <PanelInspector
                  projectId={project.id}
                  panel={selected}
                  image={size}
                  busy={editing.busy}
                  cropBuster={cropBuster}
                  onApplyBox={(box) => void editing.move(selected, box)}
                  onSplit={(type) => void editing.split(selected, type)}
                  onFullPage={() => void editing.markFullPage(selected, size)}
                  onDelete={() => setPendingDelete(selected)}
                />
              )}
              <PanelList panels={pagePanels} selectedId={selectedId} mergeIds={mergeIds} busy={editing.busy} onSelect={(id) => setSelectedId(id)} onToggleMerge={(id) => select(id, true)} onMove={reorderPage} onMerge={() => void doMerge()} />
            </div>
          </div>
        </>
      )}

      <AddPanelDialog open={addOpen} image={size} onClose={() => setAddOpen(false)} onAdd={(box) => (activePage ? addBox(activePage.id, box) : Promise.resolve(false))} />
      <ConfirmDialog
        open={pendingDelete !== null}
        title={pendingDelete ? `Delete panel ${pendingDelete.page_sequence}?` : "Delete panel?"}
        description="The panel is removed from this page. You can undo it with Undo."
        confirmLabel="Delete panel"
        danger
        onConfirm={() => void doDelete()}
        onCancel={() => setPendingDelete(null)}
      />
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
