import React, { useEffect, useRef, useState } from "react";
import { SnapshotHistory } from "@panelflow/history";
import { historyShortcut } from "../../history/shortcuts";
import { api } from "@panelflow/api-client";
import { Icons } from "@panelflow/ui";
import type { Page, Panel } from "@panelflow/shared-types";
import { boundsOf, clamp, panelSelector, splitSelector, transformSelector, validPolygon } from "./selectorGeometry";
import type { Bounds, Handle, Point, Selector } from "./selectorGeometry";

interface Props {
  projectId: string; page: Page | null; panels: Panel[]; selectedPanelId: string | null;
  pages?: Page[]; onSelectPage?: (pageId: string) => void;
  initialView?: SetupView;
  onSelectPanel: (panel: Panel) => void; onPanelSaved: (panel: Panel) => void;
  onPanelsChanged?: (panels: Panel[]) => void; onAddPanel: (page: Page, panel: Panel) => void;
  drafts?: React.MutableRefObject<Record<string, SetupDraft>>;
  /** Called BEFORE any permanent panel modification (split/delete/save). 
   * The source component pushes a combined snapshot (scenes + panels via updateEditorState at the parent) for undo support. */
  onBeforeSave?: () => void | Promise<void>;
  /** Called immediately after API returns with new panels for undo restoration. Passes (newPanels, oldPanelIds). */
  onAfterPanelChange?: (newPanels: Panel[], oldPanelIds: string[]) => void;
  /** Called before LIVE selector mutations (Split / Delete-selector) — captures undo snapshot immediately before local state changes. */
  onPreMutation?: () => void;
}
type SetupView = "pages" | "panels" | "both";
type SetupZoom = string;
export type SetupDraft = { selectors: Selector[]; activeId: string; tool: "select" | "rect" | "polygon" | "pen"; points: Point[] };
const control = "pf-setup-control";

export function SourceSetupCanvas(props: Props) {
  const [view, setView] = useState<SetupView>(props.initialView || "pages");
  const [stripOpen, setStripOpen] = useState(false);
  const [zoom, setZoom] = useState<SetupZoom>("fit");
  const [liveZoom, setLiveZoom] = useState(100);

  const [splitRatio, setSplitRatio] = useState(50);
  const [detecting, setDetecting] = useState(false);
  const [editorBusy, setEditorBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [hasUnsaved, setHasUnsaved] = useState(false);
  const alive = useRef(true);
  const pageScope = useRef(props.page?.id);
  pageScope.current = props.page?.id;
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useEffect(() => { setNotice(""); }, [props.page?.id]);
  const sourcePages = [...(props.pages || (props.page ? [props.page] : []))].sort((a, b) => a.sequence - b.sequence);
  const pageIndex = sourcePages.findIndex(page => page.id === props.page?.id);
  const pagePanels = props.panels.filter(p => p.page_id === props.page?.id).sort((a, b) => a.page_sequence - b.page_sequence);
  const selected = pagePanels.find(p => p.id === props.selectedPanelId) || pagePanels[0];
  const busy = detecting || editorBusy;
  const detect = async () => {
    if (!props.page || busy) return;
    if (hasUnsaved && !window.confirm("Auto Detect may replace this page's panels. Continue with unsaved selectors?")) return;
    const requestedPage = props.page.id;
    setDetecting(true); setNotice("");
    try {
      await props.onBeforeSave?.();
      await api.detectPagePanels(props.projectId, props.page.id);
      const all = await api.listPanels(props.projectId);
      if (alive.current) {
        props.onPanelsChanged?.(all);
        const current = all.filter(p => p.page_id === requestedPage).sort((a, b) => a.page_sequence - b.page_sequence);
        if (pageScope.current === requestedPage) {
          if (current[0]) props.onSelectPanel(current[0]);
          const retained = pagePanels.length > 0 && current.length === pagePanels.length && current.every(p => pagePanels.some(old => old.id === p.id));
          setNotice(retained ? "Panel detection complete. Existing edited or linked panels were retained." : `Panel detection complete: ${current.length} panels.`);
        }
      }
    } catch (error) { if (alive.current) setNotice(error instanceof Error ? error.message : "Auto Detect failed. Please retry."); }
    finally { if (alive.current) setDetecting(false); }
  };
  const editingPanel = selected || (props.page ? { id: `new-page-${props.page.id}`, page_id: props.page.id, x: 0, y: 0,
    width: props.page.width || 1200, height: props.page.height || 1800, crop_filename: "", page_sequence: 1 } as Panel : null);
  return <section aria-label="Source page setup" className="pf-setup-editor flex flex-col flex-1 min-h-0 min-w-0 text-zinc-200 overflow-hidden">
    <div className="pf-setup-commandbar">
      <div role="tablist" aria-label="Setup view" className="flex gap-1">
        {(["pages", "panels", "both"] as const).map(tab => <button key={tab} type="button" role="tab" id={`setup-tab-${tab}`} aria-controls="setup-view-content"
          aria-selected={view === tab} tabIndex={view === tab ? 0 : -1} disabled={busy} onClick={() => setView(tab)}
          onKeyDown={event => {
            if (busy || !["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
            event.preventDefault(); const tabs = ["pages", "panels", "both"] as const;
            const index = event.key === "Home" ? 0 : event.key === "End" ? 2 : (tabs.indexOf(tab) + (event.key === "ArrowLeft" ? 2 : 1)) % 3;
            setView(tabs[index]); document.getElementById(`setup-tab-${tabs[index]}`)?.focus();
          }} className={`${control} ${view === tab ? "bg-indigo-600/30 border-indigo-400 text-indigo-200" : "text-zinc-400"}`}>{tab === "pages" ? "Pages" : tab === "panels" ? "Panels" : "Both"}</button>)}
      </div>
      <div>
        <select aria-label="Setup panel selection" className={control} disabled={busy || !pagePanels.length} value={selected?.id || ""}
          onChange={event => { const match = pagePanels.find(p => p.id === event.target.value); if (match) props.onSelectPanel(match); }}>
          {!pagePanels.length && <option value="">No panels</option>}
          {pagePanels.map(p => <option key={p.id} value={p.id}>Panel {p.page_sequence}</option>)}
        </select>
        <button type="button" className={control} aria-expanded={stripOpen} aria-controls="setup-panelstrip" onClick={() => setStripOpen(open => !open)}>{stripOpen ? "Hide panels" : "Show panels"}</button>
      </div>
      <div className="pf-setup-zoom" role="group" aria-label="Setup zoom controls">
        <button type="button" className={control} aria-label="Zoom out setup" disabled={busy || liveZoom <= 10} onClick={() => setZoom(String(clamp((Number(zoom) || liveZoom) - 25, 10, 400)))}>−</button>
        <select aria-label="Setup zoom" value={zoom} disabled={busy} onChange={event => setZoom(event.target.value)}>
          <option value="fit">Fit page</option><option value="width">Fit width</option>
          {[25, 50, 75, 100, 150, 200, 300, 400].map(value => <option key={value} value={value}>{value}%</option>)}
          {Number(zoom) > 0 && ![25, 50, 75, 100, 150, 200, 300, 400].includes(Number(zoom)) && <option value={zoom}>{zoom}%</option>}
        </select>
        <button type="button" className={control} aria-label="Zoom in setup" disabled={busy || liveZoom >= 400} onClick={() => setZoom(String(clamp((Number(zoom) || liveZoom) + 25, 10, 400)))}>+</button>
      </div>
      <div className="flex flex-wrap items-center gap-2 text-xs">
        <button type="button" className={control} aria-label="Previous setup page" disabled={busy || pageIndex <= 0 || !props.onSelectPage}
          onClick={() => props.onSelectPage?.(sourcePages[pageIndex - 1].id)}>←</button>
        <span aria-live="polite" aria-label="Setup page position">Page {pageIndex >= 0 ? pageIndex + 1 : 0} / {sourcePages.length}</span>
        <button type="button" className={control} aria-label="Next setup page" disabled={busy || pageIndex < 0 || pageIndex >= sourcePages.length - 1 || !props.onSelectPage}
          onClick={() => props.onSelectPage?.(sourcePages[pageIndex + 1].id)}>→</button>
        <button type="button" className={control} title="Detect panels on the current page; edited, confirmed or linked panels are preserved." disabled={busy || !props.page} onClick={() => void detect()}>{detecting ? "Detecting…" : "Auto Detect"}</button>
      </div>
    </div>
    {notice && <p role="status" className="px-3 py-1 text-xs text-amber-200 shrink-0">{notice}</p>}
    <div id="setup-panelstrip" hidden={!stripOpen} aria-label="Detected panel crops" className="pf-setup-panelstrip flex gap-2 overflow-x-auto px-2 py-1 shrink-0 border-b border-zinc-800">
      {pagePanels.map(panel => <button key={panel.id} type="button" aria-label={`Edit panel ${panel.page_sequence}`} aria-pressed={selected?.id === panel.id}
        disabled={busy} onClick={() => props.onSelectPanel(panel)} className={`shrink-0 flex items-center gap-2 rounded-md border p-1 text-xs ${selected?.id === panel.id ? "border-indigo-400 bg-indigo-950" : "border-zinc-700"}`}>
        <img src={`${api.getPanelImageUrl(props.projectId, panel.id)}?v=${encodeURIComponent(panel.crop_filename || "detected")}`} alt={`Detected panel ${panel.page_sequence}`} className="w-8 h-10 object-contain bg-black" /><span>Panel {panel.page_sequence}</span>
      </button>)}
      {!pagePanels.length && <p className="text-xs text-zinc-400">No detected panels on this page. Use Auto Detect or draw a selector.</p>}
    </div>
    {editingPanel && props.page ? <SelectorEditor key={`${editingPanel.id}:${editingPanel.crop_filename}:${editingPanel.width}:${editingPanel.height}`} {...props}
      page={props.page} panel={editingPanel} view={view} onViewChange={setView} pagePanels={pagePanels}
      zoom={zoom} onScaleChange={setLiveZoom}
      splitRatio={splitRatio} onSplitRatioChange={setSplitRatio} onBusyChange={setEditorBusy} onDirtyChange={setHasUnsaved} detectionBusy={detecting} /> :
      <div className="flex-1 flex items-center justify-center p-8 text-sm text-zinc-400">No source pages available.</div>}
  </section>;
}

function SelectorEditor({ projectId, page, panel, panels, onPanelSaved, onPanelsChanged, onAddPanel, drafts, view, onViewChange, pagePanels, splitRatio, onSplitRatioChange, onBusyChange, onDirtyChange, detectionBusy, onSelectPanel, zoom, onScaleChange, onBeforeSave, onAfterPanelChange, onPreMutation }: Props & {
  page: Page; panel: Panel; view: SetupView; onViewChange: (view: SetupView) => void; pagePanels: Panel[];
  splitRatio: number; onSplitRatioChange: (ratio: number) => void; onBusyChange: (busy: boolean) => void; onDirtyChange: (dirty: boolean) => void; detectionBusy: boolean;
  zoom: SetupZoom; onScaleChange: (scale: number) => void;
}) {
  const isNew = !panel.crop_filename && panel.id === `new-page-${page.id}`;
  const initial = panelSelector(panel);
  const initialSelectors = isNew ? [] : [initial];
  const draftKey = `${projectId}:${panel.id}:${panel.crop_filename}`;
  const cached = drafts?.current[draftKey];
  const [selectors, setSelectors] = useState<Selector[]>(() => cached?.selectors || initialSelectors);
  const [activeId, setActiveId] = useState(cached?.activeId || initial.id);
  const [tool, setTool] = useState<SetupDraft["tool"]>(cached?.tool || "select");
  const [points, setPoints] = useState<Point[]>(cached?.points || []);
  useEffect(() => {
    if (drafts) drafts.current[draftKey] = { selectors, activeId, tool, points };
  }, [drafts, draftKey, selectors, activeId, tool, points]);
  const [saving, setSaving] = useState(false);
  const busy = saving || detectionBusy;
  useEffect(() => { onBusyChange(saving); return () => onBusyChange(false); }, [saving, onBusyChange]);

  const [message, setMessage] = useState("");
  const [confirmDelete, setConfirmDelete] = useState(false);
  const [parts, setParts] = useState(2);
  const [history] = useState(() => new SnapshotHistory<Selector[]>({ clone: structuredClone }));
  const svg = useRef<SVGSVGElement>(null);
  const pageSvg = useRef<SVGSVGElement>(null);
  const pageScroll = useRef<HTMLDivElement>(null);
  const panelScroll = useRef<HTMLDivElement>(null);
  const [surfaceSizes, setSurfaceSizes] = useState({ page: { width: 800, height: 600 }, panel: { width: 800, height: 600 } });
  const splitHost = useRef<HTMLDivElement>(null);
  const splitPointer = useRef<number | null>(null);
  const pageBounds = { x: 0, y: 0, width: page.width || 1200, height: page.height || 1800 };
  const editingBounds = pageBounds;
  const [scales, setScales] = useState({ page: 1, panel: 1 });
  const lockedViewport = useRef<Bounds | null>(null);
  const expandedPanel = boundsOf([{ x: panel.x, y: panel.y }, { x: panel.x + panel.width, y: panel.y + panel.height },
    ...selectors.flatMap(s => [{ x: s.x, y: s.y }, { x: s.x + s.width, y: s.y + s.height }])]);
  const panelViewport = lockedViewport.current || expandedPanel;
  useEffect(() => {
    const measure = () => {
      const size = (element: HTMLDivElement | null) => {
        if (!element || element.clientWidth <= 0 || element.clientHeight <= 0) return null;
        const css = window.getComputedStyle(element);
        return { width: Math.max(1, element.clientWidth - parseFloat(css.paddingLeft || "0") - parseFloat(css.paddingRight || "0")),
          height: Math.max(1, element.clientHeight - parseFloat(css.paddingTop || "0") - parseFloat(css.paddingBottom || "0")) };
      };
      const pageSize = size(pageScroll.current), panelSize = size(panelScroll.current);
      setSurfaceSizes(previous => {
        const next = { page: pageSize || previous.page, panel: panelSize || previous.panel };
        return JSON.stringify(next) === JSON.stringify(previous) ? previous : next;
      });
      const panelRect = svg.current?.getBoundingClientRect(), pageRect = pageSvg.current?.getBoundingClientRect();
      setScales({ panel: panelRect && panelRect.width > 0 && panelRect.height > 0 ? Math.min(panelRect.width / panelViewport.width, panelRect.height / panelViewport.height) : 1,
        page: pageRect && pageRect.width > 0 && pageRect.height > 0 ? Math.min(pageRect.width / pageBounds.width, pageRect.height / pageBounds.height) : 1 });
    };
    measure();
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(measure);
    if (svg.current) observer?.observe(svg.current);
    if (pageSvg.current) observer?.observe(pageSvg.current);
    if (pageScroll.current) observer?.observe(pageScroll.current);
    if (panelScroll.current) observer?.observe(panelScroll.current);
    window.addEventListener("resize", measure);
    return () => { observer?.disconnect(); window.removeEventListener("resize", measure); };
  }, [panelViewport.width, panelViewport.height, pageBounds.width, pageBounds.height, view, zoom]);
  useEffect(() => { onScaleChange(Math.round((view === "pages" ? scales.page : scales.panel) * 100)); }, [view, scales.page, scales.panel, onScaleChange]);
  useEffect(() => { pageSvg.current?.querySelector('[data-selected-panel="true"]')?.scrollIntoView?.({ block: "nearest", inline: "nearest" }); }, [panel.id, view]);
  const serial = useRef(0);
  const drag = useRef<{ pointer: number; start: Point; selector?: Selector; handle?: Handle; vertex?: number; before: Selector[]; drawing?: "rect" | "pen" } | null>(null);
  const active = selectors.find(s => s.id === activeId);
  const dirty = JSON.stringify(selectors) !== JSON.stringify(initialSelectors);
  useEffect(() => { onDirtyChange(dirty || points.length > 0); return () => onDirtyChange(false); }, [dirty, points.length, onDirtyChange]);
  const remember = (next: Selector[]) => { history.record(selectors, next); setSelectors(next); setMessage(""); };
  const restoreDraft = (direction: "undo" | "redo") => {
    if (busy || drag.current) return;
    const restored = history[direction]();
    if (!restored) return;
    setSelectors(restored); setPoints([]); setMessage("");
    if (!restored.some(s => s.id === activeId)) setActiveId(restored[0]?.id || "");
  };
  const replace = (next: Selector) => setSelectors(previous => previous.map(s => s.id === next.id ? next : s));
  const newId = () => `${panel.id}-selector-${Date.now()}-${++serial.current}`;
  const point = (event: React.MouseEvent): Point => {
    const element = event.currentTarget as SVGElement;
    const source = (element.tagName.toLowerCase() === "svg" ? element : element.ownerSVGElement) as SVGSVGElement;
    const [x, y, width, height] = source.getAttribute("viewBox")!.split(" ").map(Number);
    const rect = source.getBoundingClientRect();
    const scale = Math.min(rect.width / width, rect.height / height) || 1;
    return { x: Math.round(clamp(x + (event.clientX - rect.left - (rect.width - width * scale) / 2) / scale, editingBounds.x, editingBounds.x + editingBounds.width)),
      y: Math.round(clamp(y + (event.clientY - rect.top - (rect.height - height * scale) / 2) / scale, editingBounds.y, editingBounds.y + editingBounds.height)) };
  };
  const capture = (event: React.PointerEvent) => {
    const element = event.currentTarget as SVGElement;
    const source = (element.tagName.toLowerCase() === "svg" ? element : element.ownerSVGElement) as SVGSVGElement;
    source.setPointerCapture?.(event.pointerId);
  };
  const beginHandle = (event: React.PointerEvent, selector: Selector, handle: Handle, vertex?: number) => {
    if (busy || event.button !== 0 || tool !== "select") return;
    event.stopPropagation(); event.preventDefault(); setActiveId(selector.id);
    lockedViewport.current = panelViewport;
    drag.current = { pointer: event.pointerId, start: point(event), selector, handle, vertex, before: selectors };
    capture(event);
  };
  const finishPolygon = () => {
    const clean = points.filter((p, i) => i === 0 || Math.hypot(p.x - points[i - 1].x, p.y - points[i - 1].y) > .5);
    if (clean.length > 3 && Math.hypot(clean[0].x - clean[clean.length - 1].x, clean[0].y - clean[clean.length - 1].y) < 1) clean.pop();
    if (!validPolygon(clean)) { setMessage("Draw at least three vertices without crossing edges. Adjust or clear the unfinished shape."); return; }
    const bounds = boundsOf(clean);
    if (bounds.width < 4 || bounds.height < 4) { setMessage("Selectors must be at least 4 × 4 pixels."); return; }
    const selector: Selector = { ...bounds, id: newId(), kind: tool === "pen" ? "pen" : "polygon", points: clean };
    remember([...selectors, selector]); setActiveId(selector.id); setPoints([]); setTool("select");
  };
  const pointerDown = (event: React.PointerEvent<SVGSVGElement>) => {
    if (busy || event.button !== 0) return;
    const start = point(event);
    if (tool === "polygon") { setPoints(previous => previous.length < 512 ? [...previous, start] : previous); return; }
    if (tool === "rect" || tool === "pen") {
      lockedViewport.current = panelViewport;
      drag.current = { pointer: event.pointerId, start, before: selectors, drawing: tool };
      capture(event);
      if (tool === "pen") setPoints([start]);
      else {
        const selector: Selector = { id: newId(), kind: "rect", x: start.x, y: start.y, width: 0, height: 0 };
        drag.current.selector = selector; setSelectors([...selectors, selector]); setActiveId(selector.id);
      }
    }
  };
  const pointerMove = (event: React.PointerEvent<SVGSVGElement>) => {
    const gesture = drag.current;
    if (!gesture || gesture.pointer !== event.pointerId || busy) return;
    const current = point(event);
    if (gesture.drawing === "pen") {
      setPoints(previous => previous.length < 512 && Math.hypot(current.x - previous[previous.length - 1].x, current.y - previous[previous.length - 1].y) >= Math.max(1, Math.min(panel.width, panel.height) / 150) ? [...previous, current] : previous);
    } else if (gesture.drawing === "rect" && gesture.selector) replace({ ...gesture.selector, ...boundsOf([gesture.start, current]) });
    else if (gesture.selector && gesture.vertex !== undefined && gesture.selector.points) {
      const next = gesture.selector.points.map((p, i) => i === gesture.vertex ? current : p);
      replace({ ...gesture.selector, ...boundsOf(next), points: next });
    } else if (gesture.selector && gesture.handle) replace(transformSelector(gesture.selector, gesture.handle, current.x - gesture.start.x, current.y - gesture.start.y, editingBounds));
  };
  const pointerUp = (event: React.PointerEvent<SVGSVGElement>, cancel = false) => {
    const gesture = drag.current;
    if (!gesture || gesture.pointer !== event.pointerId) return;
    drag.current = null;
    lockedViewport.current = null;
    if (event.currentTarget.hasPointerCapture?.(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId);
    if (cancel) { setSelectors(gesture.before); setActiveId(gesture.selector?.id && gesture.before.some(s => s.id === gesture.selector?.id) ? gesture.selector.id : gesture.before[0]?.id || ""); setPoints([]); return; }
    if (gesture.drawing === "pen") { setMessage("Use Finish shape to close and validate the stroke."); return; }
    const completed = selectors.filter(s => s.width >= 4 && s.height >= 4);
    history.record(gesture.before, completed);
    setSelectors(completed);
    if (!selectors.some(s => s.id === activeId && s.width >= 4 && s.height >= 4)) setActiveId(gesture.before[0]?.id || "");
    if (gesture.drawing) setTool("select");
  };
  const save = async () => {
    if (busy) return;
    if (points.length || !selectors.length || selectors.length > 64) { setMessage("Finish or clear the unfinished shape; save between 1 and 64 selectors."); return; }
    const payload = selectors.map(s => {
      const x = Math.floor(s.x), y = Math.floor(s.y);
      return { x, y, width: Math.ceil(s.x + s.width) - x, height: Math.ceil(s.y + s.height) - y,
        points: s.points?.map(p => [Math.round(p.x), Math.round(p.y)] as [number, number]) };
    });
    if (payload.some(s => s.width < 4 || s.height < 4 || (s.points && !validPolygon(s.points.map(([x, y]) => ({ x, y })))))) {
      setMessage("Each selector must have usable bounds and a non-crossing shape."); return;
    }
    setSaving(true); setMessage("");
    try {
      // Pre-action: capture snapshot of panels+scenes BEFORE api calls (true undo baseline)
      await onBeforeSave?.();
      const needsPageBounds = view !== "panels" || payload.some(s => s.x < panel.x || s.y < panel.y || s.x + s.width > panel.x + panel.width || s.y + s.height > panel.y + panel.height);
      const all = isNew ? await api.addPageSelections(projectId, page.id, payload) : !needsPageBounds
        ? await api.savePanelSelections(projectId, panel.id, payload) : await api.savePanelSelections(projectId, panel.id, payload, true);
      const first = all.find(p => p.id === panel.id) || all.find(p => p.page_id === page.id);
      if (drafts) delete drafts.current[draftKey];
      if (first) onPanelSaved(first);
      onPanelsChanged?.(all); setMessage("Selectors saved as panels.");
    } catch (error) { setMessage(error instanceof Error ? error.message : "Could not save selectors. Please retry."); }
    finally { setSaving(false); }
  };
  const deletePanel = async () => {
    setSaving(true); setMessage("");
    try {
      // Pre-action: capture snapshot BEFORE panel is deleted (true undo baseline)
      await onBeforeSave?.();
      await api.deletePanel(projectId, panel.id);
      if (drafts) delete drafts.current[draftKey];
      const counts = new Map<string, number>();
      const remaining = panels.filter(p => p.id !== panel.id).sort((a, b) => a.sequence - b.sequence).map((p, i) => {
        const pageSequence = (counts.get(p.page_id) || 0) + 1; counts.set(p.page_id, pageSequence);
        return { ...p, sequence: i + 1, page_sequence: pageSequence };
      });
      onPanelsChanged?.(remaining);
    }
    catch (error) { setMessage(error instanceof Error ? error.message : "Could not delete panel."); }
    finally { setSaving(false); setConfirmDelete(false); }
  };
  const handles: [Handle, number, number][] = active ? [
    ["nw", active.x, active.y], ["n", active.x + active.width / 2, active.y], ["ne", active.x + active.width, active.y],
    ["e", active.x + active.width, active.y + active.height / 2], ["se", active.x + active.width, active.y + active.height],
    ["s", active.x + active.width / 2, active.y + active.height], ["sw", active.x, active.y + active.height],
    ["w", active.x, active.y + active.height / 2], ["center", active.x + active.width / 2, active.y + active.height / 2],
  ] : [];
  const renderSurface = (surface: "page" | "panel") => {
    const isPage = surface === "page", bounds = isPage ? pageBounds : panelViewport;
    const radius = 5 / (isPage ? scales.page : scales.panel);
    const clipId = `panel-clip-${panel.id}-${surface}`;
    const openPanelAt = (event: React.MouseEvent<SVGSVGElement>) => {
      if (!isPage || busy || tool !== "select") return;
      const location = point(event);
      const contains = (box: Bounds) => location.x >= box.x && location.x <= box.x + box.width && location.y >= box.y && location.y <= box.y + box.height;
      if (selectors.some(contains)) { onViewChange("panels"); return; }
      const match = pagePanels.find(contains);
      if (match) { onSelectPanel(match); onViewChange("panels"); }
    };
    return <svg ref={isPage ? pageSvg : svg} viewBox={`${bounds.x} ${bounds.y} ${bounds.width} ${bounds.height}`} preserveAspectRatio="xMidYMid meet"
        aria-label={isPage ? "Page selector editor" : "Panel selector editor"}
        className="block w-full h-full overflow-visible" style={{ touchAction: tool === "select" ? "pan-y" : "none", cursor: tool === "select" ? "default" : "crosshair" }}
        onPointerDown={pointerDown} onPointerMove={pointerMove} onPointerUp={e => pointerUp(e)} onPointerCancel={e => pointerUp(e, true)}
        onDoubleClick={openPanelAt} onClick={event => { if (event.detail >= 2) openPanelAt(event); }}>
        <defs><clipPath id={clipId}><rect x={bounds.x} y={bounds.y} width={bounds.width} height={bounds.height} /></clipPath></defs>
        <image href={api.getPageImageUrl(projectId, page.id)} x={0} y={0} width={page.width || 1200} height={page.height || 1800}
          clipPath={`url(#${clipId})`} pointerEvents="none" />
        {isPage && pagePanels.filter(p => p.id !== panel.id).map(p => <g key={p.id} role="button" tabIndex={busy ? -1 : 0}
          aria-label={`Page panel ${p.page_sequence}`} aria-pressed={false}
          onClick={event => { if (!busy && tool === "select") { event.stopPropagation(); onSelectPanel(p); if (event.detail >= 2) onViewChange("panels"); } }}
          onDoubleClick={event => { if (!busy && tool === "select") { event.stopPropagation(); onSelectPanel(p); onViewChange("panels"); } }}
          onKeyDown={event => { if (!busy && event.key === "Enter") { event.preventDefault(); onSelectPanel(p); } }}>
          <rect x={p.x} y={p.y} width={p.width} height={p.height} fill="rgba(34,211,238,.06)" stroke="#22d3ee" strokeWidth={2} vectorEffect="non-scaling-stroke" className="cursor-pointer" />
          <text x={p.x + radius} y={p.y + radius * 3} fontSize={radius * 2.5} fill="white" stroke="black" paintOrder="stroke" pointerEvents="none">P{p.page_sequence}</text>
        </g>)}
        {selectors.map((s, index) => <g key={s.id} onPointerDown={e => beginHandle(e, s, "center")} data-selected-panel={isPage ? "true" : undefined}
          role={isPage ? "button" : undefined} tabIndex={isPage && !busy ? 0 : undefined} aria-label={isPage ? `Page panel ${panel.page_sequence}${index ? ` selector ${index + 1}` : ""}` : undefined}
          aria-pressed={isPage ? true : undefined} onDoubleClick={event => { if (isPage && tool === "select" && !busy) { event.stopPropagation(); onViewChange("panels"); } }}
          onClick={event => { if (isPage && tool === "select" && !busy && event.detail >= 2) onViewChange("panels"); }}
          onKeyDown={event => { if (isPage && event.key === "Enter" && !busy) { event.preventDefault(); onViewChange("panels"); } }}>
          {s.points ? <polygon points={s.points.map(p => `${p.x},${p.y}`).join(" ")} fill="rgba(99,102,241,.15)" stroke={activeId === s.id ? "#a5b4fc" : "#22d3ee"} strokeWidth={2} vectorEffect="non-scaling-stroke" /> :
            <rect x={s.x} y={s.y} width={s.width} height={s.height} fill="rgba(99,102,241,.12)" stroke={activeId === s.id ? "#a5b4fc" : "#22d3ee"} strokeWidth={2} vectorEffect="non-scaling-stroke" />}
          <text x={s.x + radius} y={s.y + radius * 3} fontSize={radius * 2.5} fill="white" stroke="black" strokeWidth={1} paintOrder="stroke" pointerEvents="none">{index + 1}</text>
        </g>)}
        {tool === "select" && handles.map(([handle, x, y]) => <g key={handle} role="button" tabIndex={busy ? -1 : 0} aria-label={`Selector ${handle} handle`}
          onPointerDown={e => beginHandle(e, active!, handle)} onKeyDown={event => {
            if (busy || !active || !["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(event.key)) return;
            event.preventDefault(); const step = event.shiftKey ? 10 : 1;
            remember(selectors.map(s => s.id === active.id ? transformSelector(s, handle,
              event.key === "ArrowLeft" ? -step : event.key === "ArrowRight" ? step : 0,
              event.key === "ArrowUp" ? -step : event.key === "ArrowDown" ? step : 0, editingBounds) : s));
          }} style={{ cursor: handle === "center" ? "move" : `${handle}-resize`, touchAction: "none" }}>
          <rect x={x - radius * 1.7} y={y - radius * 1.7} width={radius * 3.4} height={radius * 3.4} fill="transparent" />
          {handle.length === 2 ? <><circle cx={x} cy={y} r={radius} fill="white" stroke="#6366f1" strokeWidth={2} vectorEffect="non-scaling-stroke" /><circle cx={x} cy={y} r={radius / 3} fill="#6366f1" /></> :
            <rect x={x - radius} y={y - radius / 1.3} width={radius * 2} height={radius * 1.54} rx={radius / 3} fill={handle === "center" ? "#22d3ee" : "white"} stroke="#6366f1" vectorEffect="non-scaling-stroke" />}
        </g>)}
        {tool === "select" && active?.points?.map((p, index) => <circle key={index} cx={p.x} cy={p.y} r={radius * .75} fill="#22d3ee" stroke="white"
          aria-label={`Polygon vertex ${index + 1}`} onPointerDown={e => beginHandle(e, active, "center", index)} className="cursor-move" />)}
        {points.length > 0 && <polyline points={points.map(p => `${p.x},${p.y}`).join(" ")} fill="rgba(34,211,238,.12)" stroke="#22d3ee" strokeWidth={2} vectorEffect="non-scaling-stroke" pointerEvents="none" />}
      </svg>;
  };
  const surface = (kind: "page" | "panel") => {
    const bounds = kind === "page" ? pageBounds : panelViewport, available = surfaceSizes[kind];
    const scale = zoom === "width" ? available.width / bounds.width : zoom === "fit"
      ? Math.min(available.width / bounds.width, available.height / bounds.height) : Math.max(.1, Number(zoom) / 100);
    return <div ref={kind === "page" ? pageScroll : panelScroll} role="region" aria-label={kind === "page" ? "Current source page" : "Current panel crop"}
      tabIndex={0} data-page-id={kind === "page" ? page.id : undefined} className="pf-setup-surface">
      <div className="pf-setup-surface-inner" style={{ width: bounds.width * scale, height: bounds.height * scale }}>{renderSurface(kind)}</div>
    </div>;
  };
  const renderPage = () => surface("page");
  const renderPanel = () => surface("panel");
  return <div className="contents" onKeyDown={event => {
    const action = historyShortcut(event);
    if (!action) return;
    // The focused draft owns the shortcut even at its history boundary.
    event.preventDefault(); event.stopPropagation(); restoreDraft(action);
  }}>
    <div className="pf-setup-editing-body">
    <fieldset disabled={busy} aria-label="Setup tools" className="pf-setup-tools">
      {([["select", "Select", Icons.Layout], ["rect", "Rectangle", Icons.Maximize], ["polygon", "Polygon", Icons.Sparkles], ["pen", "Pen", Icons.Scissors]] as const).map(([value, label, Icon]) =>
        <button type="button" key={value} aria-pressed={tool === value} onClick={() => { setTool(value); setPoints([]); setMessage(""); }}
          className={`${control} inline-flex items-center gap-1 ${tool === value ? "bg-indigo-600/30 border-indigo-400 text-indigo-200" : "text-zinc-300"}`}><Icon className="w-3.5 h-3.5" />{label}</button>)}
      {(tool === "polygon" || tool === "pen") && <><button className={control} type="button" onClick={finishPolygon} disabled={points.length < 3}>Finish shape</button>
        <button className={control} type="button" onClick={() => setPoints([])}>Clear shape</button></>}
      <button className={control} type="button" disabled={!history.getState().canUndo} onClick={() => restoreDraft("undo")}>Undo</button>
      <button className={control} type="button" disabled={!history.getState().canRedo} onClick={() => restoreDraft("redo")}>Redo</button>
    </fieldset>
    <div id="setup-view-content" role="tabpanel" aria-labelledby={`setup-tab-${view}`} className="flex flex-1 min-w-0 min-h-0 overflow-hidden" ref={splitHost}>
      {view === "pages" ? renderPage() : view === "panels" ? renderPanel() : <>
        <div className="flex min-w-0 min-h-0" style={{ width: `${splitRatio}%` }}>{renderPage()}</div>
        <div role="separator" aria-label="Resize page and panel views" aria-orientation="vertical" aria-valuemin={25} aria-valuemax={75} aria-valuenow={Math.round(splitRatio)} tabIndex={busy ? -1 : 0}
          className="w-2 shrink-0 cursor-col-resize bg-zinc-800 hover:bg-indigo-500 focus:bg-indigo-500 outline-none" style={{ touchAction: "none" }}
          onDoubleClick={() => onSplitRatioChange(50)} onPointerDown={event => { if (!busy && event.button === 0) { splitPointer.current = event.pointerId; event.currentTarget.setPointerCapture?.(event.pointerId); event.preventDefault(); } }}
          onPointerMove={event => {
            if (splitPointer.current !== event.pointerId || !splitHost.current) return;
            const rect = splitHost.current.getBoundingClientRect();
            if (rect.width > 0) onSplitRatioChange(clamp((event.clientX - rect.left) / rect.width * 100, 25, 75));
          }} onPointerUp={event => { splitPointer.current = null; if (event.currentTarget.hasPointerCapture?.(event.pointerId)) event.currentTarget.releasePointerCapture(event.pointerId); }}
          onPointerCancel={() => { splitPointer.current = null; }} onKeyDown={event => {
            if (busy || !["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
            event.preventDefault(); onSplitRatioChange(event.key === "Home" ? 25 : event.key === "End" ? 75 : clamp(splitRatio + (event.key === "ArrowLeft" ? -5 : 5), 25, 75));
          }} />
        {renderPanel()}
      </>}
    </div>
    </div>
    <div className="pf-setup-actions">
      <fieldset disabled={busy} className="flex flex-wrap gap-2 items-center">
        <label className="text-xs">Selector <select aria-label="Active selector" value={activeId} onChange={e => setActiveId(e.target.value)} className="bg-zinc-900 border border-zinc-700 rounded p-1">
          {selectors.map((s, i) => <option key={s.id} value={s.id}>{i + 1} · {s.kind}</option>)}
        </select></label>
        <label className="text-xs">Parts <input aria-label="Split parts" type="number" min={2} max={12} value={parts} onChange={e => setParts(Number(e.target.value))} className="w-12 bg-zinc-900 border border-zinc-700 rounded p-1" /></label>
        {(["vertical", "horizontal"] as const).map(direction => <button key={direction} className={control} type="button" disabled={!active || active.kind !== "rect"} onClick={() => {
          // IMMEDIATE undo snapshot before live selector mutation (split changes selectors locally)
          onPreMutation?.();
          try { const split = splitSelector(active!, direction, parts); remember(selectors.flatMap(s => s.id === activeId ? split : [s])); setActiveId(split[0].id); }
          catch (error) { setMessage((error as Error).message); }
        }}>Split {direction === "vertical" ? "vertically" : "horizontally"}</button>)}
        <button className={control} type="button" disabled={!active || selectors.length <= 1} onClick={() => {
          // IMMEDIATE undo snapshot before live selector deletion
          onPreMutation?.();
          const next = selectors.filter(s => s.id !== activeId); remember(next); setActiveId(next[0].id); 
        }}>Delete selector</button>
        <button className={control} type="button" disabled={isNew} onClick={() => setConfirmDelete(true)}>Delete panel</button>
        <span className="pf-setup-status" aria-live="polite">{dirty ? "Unsaved" : ""}</span>
        <button className={`${control} pf-setup-save`} type="button" onClick={() => void save()} disabled={!dirty || !!points.length}>{busy ? "Saving…" : "Save selectors"}</button>
        <button className={control} type="button" disabled={isNew || dirty || !!points.length} onClick={() => onAddPanel(page, panel)}>Add panel to timeline</button>
      </fieldset>
      {confirmDelete && <div role="alert" className="text-xs flex flex-wrap items-center gap-2">Delete this detected panel? Existing video scenes keep their saved composition.
        <button className={control} disabled={busy} onClick={() => void deletePanel()}>Confirm delete panel</button><button className={control} disabled={busy} onClick={() => setConfirmDelete(false)}>Cancel</button>
      </div>}
      <p className="pf-setup-hint" hidden={tool === "select"}>{tool === "polygon" ? "Click vertices, then Finish shape." : tool === "pen" ? "Draw an outline, then Finish shape." : "Drag to add a rectangle selector."}</p>
      {message && <p role="status" className="text-xs text-amber-200">{message}</p>}
    </div>
  </div>;
}
