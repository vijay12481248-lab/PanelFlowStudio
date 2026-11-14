import React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { ChevronLeft, ChevronRight, RotateCw, Trash2 } from "lucide-react";
import { api } from "@panelflow/api-client";
import type { AcquisitionManifest, Page, Project } from "@panelflow/shared-types";
import { Button, EmptyState, ErrorState, GlassPanel, IconButton, Skeleton } from "@panelflow/ui-v2";
import { useError } from "../../../context/ErrorContext";
import { ConfirmDialog } from "../kit/ConfirmDialog";
import { JobProgress } from "../kit/JobProgress";
import { PageThumb } from "../kit/PageThumb";
import { StageToolbar } from "../kit/StageToolbar";
import { refusal } from "../kit/engineReason";
import { isActiveJob, stageKeys, useJob, usePages } from "../kit/stageData";
import { ManifestDialog } from "./ManifestDialog";
import { PageInspector } from "./PageInspector";
import { canConfirm, moveItem } from "./pagesModel";

export interface PagesStageProps {
  project: Project;
  /** Called with the updated project after the acquisition is confirmed. */
  onConfirmed: (updated: Project) => void;
  /** Move on without confirming (the old "Detect Panels" button). */
  onContinue: (project: Project) => void;
}

/** Pages: put the scans in order, rotate or remove the wrong ones, then confirm the acquisition. */
export const PagesStage: React.FC<PagesStageProps> = ({ project, onConfirmed, onContinue }) => {
  const queryClient = useQueryClient();
  const { reportError } = useError();
  const query = usePages(project.id);
  const pages = React.useMemo(() => [...(query.data ?? [])].sort((a, b) => a.sequence - b.sequence), [query.data]);
  const failed = pages.filter((p) => p.status === "FAILED").length;
  const gate = canConfirm(pages);
  const ready = pages.filter((p) => p.status === "READY").length;

  const [error, setError] = React.useState<string | null>(null);
  const [bust, setBust] = React.useState(() => Date.now()); // changes after a rotation so the browser reloads the image
  const [toDelete, setToDelete] = React.useState<Page | null>(null);
  const [inspectId, setInspectId] = React.useState<string | null>(null);
  const [manifest, setManifest] = React.useState<AcquisitionManifest | null>(null);
  const [dragFrom, setDragFrom] = React.useState<number | null>(null);
  const [dragOver, setDragOver] = React.useState<number | null>(null);
  const [confirming, setConfirming] = React.useState(false);
  const [retryJobId, setRetryJobId] = React.useState<string | undefined>();

  const reordering = React.useRef(false);
  const rotating = React.useRef(new Set<string>());
  const deleting = React.useRef(false);
  const confirmBusy = React.useRef(false);
  const retryBusy = React.useRef(false);

  const setPages = (next: Page[]) => queryClient.setQueryData(stageKeys.pages(project.id), next);
  const reload = () => queryClient.invalidateQueries({ queryKey: stageKeys.pages(project.id) });

  const move = async (from: number, to: number) => {
    if (reordering.current || from === to) return;
    const next = moveItem(pages, from, to);
    if (next.every((p, i) => p.id === pages[i].id)) return;
    reordering.current = true;
    setError(null);
    const previous = pages;
    setPages(next.map((p, i) => ({ ...p, sequence: i + 1 }))); // show the new order at once (the grid sorts by sequence); restore it if the engine refuses
    try {
      setPages(await api.reorderPages(project.id, next.map((p) => p.id)));
    } catch (err: any) {
      setPages(previous);
      setError("Couldn't save the new order. The pages are back in their old order.");
      reportError({ title: "Page Reorder Failed", message: "Failed to save reordered pages.", severity: "warning", source: "pipeline", projectId: project.id, rawDetails: err });
    } finally { reordering.current = false; }
  };

  const rotate = async (page: Page) => {
    if (rotating.current.has(page.id)) return;
    rotating.current.add(page.id);
    setError(null);
    try {
      const updated = await api.rotatePage(project.id, page.id, 90);
      setPages(pages.map((p) => (p.id === page.id ? updated : p)));
      setBust(Date.now());
    } catch (err: any) {
      setError(`Couldn't rotate page ${page.sequence}. Try again.`);
      reportError({ title: "Page Rotation Failed", message: `Failed to rotate page ${page.sequence}.`, severity: "warning", source: "pipeline", projectId: project.id, rawDetails: { pageId: page.id, error: err } });
    } finally { rotating.current.delete(page.id); }
  };

  const remove = async () => {
    const page = toDelete;
    if (!page || deleting.current) return;
    deleting.current = true;
    setToDelete(null);
    setError(null);
    try {
      await api.deletePage(project.id, page.id);
      if (inspectId === page.id) setInspectId(null);
      await reload();
    } catch (err: any) {
      setError("Couldn't delete the page. Nothing was removed.");
      reportError({ title: "Page Delete Failed", message: `Failed to delete page ${page.sequence}.`, severity: "warning", source: "pipeline", projectId: project.id, rawDetails: err });
    } finally { deleting.current = false; }
  };

  const confirm = async () => {
    if (confirmBusy.current || !gate.ok) return;
    confirmBusy.current = true;
    setConfirming(true);
    setError(null);
    try {
      onConfirmed(await api.confirmAcquisition(project.id));
    } catch (err: any) {
      setError(refusal("Couldn't confirm the pages.", err));
      reportError({ title: "Acquisition Confirmation Failed", message: "Could not confirm page acquisition.", severity: "error", source: "pipeline", projectId: project.id, rawDetails: err });
    } finally { confirmBusy.current = false; setConfirming(false); }
  };

  const retry = async () => {
    if (retryBusy.current) return;
    retryBusy.current = true;
    setError(null);
    try { setRetryJobId((await api.retryFailedPages(project.id)).job_id); }
    catch (err: any) {
      setError("Couldn't retry the failed pages. Check that the engine is running, then try again.");
      reportError({ title: "Page Download Retry Failed", message: "Failed to retry downloading failed pages.", severity: "error", source: "pipeline", projectId: project.id, jobType: "ACQUISITION", rawDetails: err });
    } finally { retryBusy.current = false; }
  };

  // While a retry job runs, show it; when it ends, reload the pages.
  const retryJob = useJob(retryJobId);
  React.useEffect(() => {
    if (retryJobId && retryJob.data && !isActiveJob(retryJob.data)) {
      setRetryJobId(undefined);
      setBust(Date.now());
      void reload();
    }
  }, [retryJobId, retryJob.data?.status]); // eslint-disable-line react-hooks/exhaustive-deps

  const viewManifest = async () => {
    try { setManifest(await api.getManifest(project.id)); }
    catch (err: any) {
      setError("Couldn't load the manifest. Check that the engine is running, then try again.");
      reportError({ title: "Could Not Fetch Manifest", message: "Failed to load acquisition manifest.", severity: "warning", source: "pipeline", projectId: project.id, rawDetails: err });
    }
  };

  const imageUrl = (page: Page) => `${api.getPageImageUrl(project.id, page.id)}?t=${bust}`;

  if (query.isError) {
    return <ErrorState title="Couldn't load the pages" description="Check that the engine is running, then try again." onRetry={() => void query.refetch()} />;
  }

  return (
    <div className="grid grid-cols-1 gap-5">
      <StageToolbar
        title="Review pages"
        description="Confirm the order, rotate scans that are sideways, and remove blank or wrong pages."
        actions={
          <>
            {failed > 0 && <Button variant="secondary" size="sm" loading={Boolean(retryJobId)} onClick={() => void retry()}>{`Retry failed pages (${failed})`}</Button>}
            <Button variant="secondary" size="sm" onClick={() => void viewManifest()}>View manifest</Button>
            <Button variant="secondary" size="sm" disabled={!gate.ok} onClick={() => onContinue(project)}>Continue to panels</Button>
            <Button variant="primary" size="sm" loading={confirming} disabled={!gate.ok} onClick={() => void confirm()}>{`Confirm acquisition (${ready} pages)`}</Button>
          </>
        }
      />
      {!gate.ok && pages.length > 0 && <p className="text-sm text-warn">{gate.reason}</p>}
      {error && <p role="alert" className="text-sm text-bad">{error}</p>}
      {retryJobId && <GlassPanel blur={false} className="p-4"><JobProgress job={retryJob.data} idleLabel="Retrying the failed pages." /></GlassPanel>}

      {!query.data ? (
        <Skeleton className="h-64" />
      ) : pages.length === 0 ? (
        <GlassPanel blur={false}>
          <EmptyState title="No pages yet" description="Go back to Acquire and start the download. Pages appear here when they are ready." />
          {!gate.ok && <p className="pb-4 text-center text-sm text-warn">{gate.reason}</p>}
        </GlassPanel>
      ) : (
        <div className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-4">
          {pages.map((p, index) => {
            const isFailed = p.status === "FAILED";
            return (
              <div
                key={p.id}
                data-page-id={p.id}
                draggable
                onDragStart={(event) => { event.dataTransfer?.setData("text/plain", p.id); setDragFrom(index); }}
                onDragOver={(event) => { event.preventDefault(); setDragOver(index); }}
                onDragLeave={() => setDragOver((current) => (current === index ? null : current))}
                onDrop={(event) => { event.preventDefault(); setDragOver(null); const from = dragFrom; setDragFrom(null); if (from !== null) void move(from, index); }}
                onDragEnd={() => { setDragFrom(null); setDragOver(null); }}
                className={`grid gap-2 rounded-card p-1 ${dragOver === index && dragFrom !== index ? "ring-2 ring-accent" : ""}`}
              >
                <PageThumb
                  src={imageUrl(p)}
                  label={`Page ${p.sequence}`}
                  failed={isFailed}
                  reason={isFailed ? p.error_message : null}
                  onOpen={isFailed ? undefined : () => setInspectId(p.id)}
                />
                <div className="flex items-center justify-between gap-1">
                  <p className="text-xs text-fg-faint">{`#${p.sequence}${p.width > 0 ? ` · ${p.width}×${p.height}` : ""}`}</p>
                  <div className="flex items-center gap-1">
                    <IconButton label={`Move page ${p.sequence} earlier`} className="size-7" disabled={index === 0} onClick={() => void move(index, index - 1)}><ChevronLeft size={14} /></IconButton>
                    <IconButton label={`Move page ${p.sequence} later`} className="size-7" disabled={index === pages.length - 1} onClick={() => void move(index, index + 1)}><ChevronRight size={14} /></IconButton>
                    {!isFailed && <IconButton label={`Rotate page ${p.sequence}`} className="size-7" onClick={() => void rotate(p)}><RotateCw size={14} /></IconButton>}
                    <IconButton label={`Delete page ${p.sequence}`} className="size-7" onClick={() => setToDelete(p)}><Trash2 size={14} /></IconButton>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <PageInspector pages={pages.filter((p) => p.status !== "FAILED")} openId={inspectId} imageUrl={imageUrl} onOpen={setInspectId} onClose={() => setInspectId(null)} onRotate={(page) => void rotate(page)} />
      <ManifestDialog manifest={manifest} onClose={() => setManifest(null)} />
      <ConfirmDialog
        open={toDelete !== null}
        title={toDelete ? `Delete page ${toDelete.sequence}?` : "Delete page?"}
        description="The remaining pages are renumbered. This can't be undone."
        confirmLabel="Delete page"
        danger
        onConfirm={() => void remove()}
        onCancel={() => setToDelete(null)}
      />
    </div>
  );
};
