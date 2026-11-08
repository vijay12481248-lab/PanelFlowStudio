import React from "react";
import { useQueryClient } from "@tanstack/react-query";
import { api } from "@panelflow/api-client";
import type { Project, RenderJob } from "@panelflow/shared-types";
import { Button, Chip, ErrorState, GlassPanel, Progress, Skeleton, useToast } from "@panelflow/ui-v2";
import { useError } from "../../../context/ErrorContext";
import { StageToolbar } from "../kit/StageToolbar";
import { refusal } from "../kit/engineReason";
import { latestRender } from "../../workbench/publishModel";
import { workbenchKeys } from "../../workbench/queries";
import { useStageNav } from "../kit/useStageNav";
import { RenderHistory } from "./RenderHistory";
import { RenderResult } from "./RenderResult";
import { RenderSettingsPanel } from "./RenderSettingsPanel";
import { useQuickDestinations, useRenderList, useRenderProfiles } from "./renderData";
import { DEFAULT_SETTINGS, activeRender, isRunning, profileChoices, renderStatus, startOptions, type RenderSettings } from "./renderModel";

export interface RenderStageProps {
  project: Project;
  /** Called with the reloaded project after a render finishes. */
  onRenderComplete: (updated: Project) => void;
}

const RENDER_ADVICE = "Check the engine log in Diagnostics for the details, then try again.";

/** Render: choose the output settings, make the video, follow it, and keep the history. */
export const RenderStage: React.FC<RenderStageProps> = ({ project, onRenderComplete }) => {
  const queryClient = useQueryClient();
  const toast = useToast();
  const { reportError } = useError();

  const nav = useStageNav(project, "render");
  const [viewedId, setViewedId] = React.useState<string | null>(null);
  const rendersQuery = useRenderList(project.id);
  const renders = rendersQuery.data ?? [];
  const active = activeRender(renders);
  const profilesQuery = useRenderProfiles();
  const choices = React.useMemo(() => profileChoices(profilesQuery.data?.profiles), [profilesQuery.data]);
  const destinations = useQuickDestinations(project.id);

  const [settings, setSettings] = React.useState<RenderSettings>(DEFAULT_SETTINGS);
  const profileId = settings.profile && choices.options.some((o) => o.id === settings.profile) ? settings.profile : choices.defaultId ?? "";
  const [error, setError] = React.useState<string | null>(null);
  const [notice, setNotice] = React.useState<string | null>(null);
  const [pickerError, setPickerError] = React.useState<string | null>(null);
  const [starting, setStarting] = React.useState(false);
  const [cancelling, setCancelling] = React.useState(false);
  const busy = React.useRef(false);
  const cancelBusy = React.useRef(false);

  // Like the old screen, a new render saves to the engine's default folder unless the person chooses another.
  const prefilled = React.useRef(false);
  React.useEffect(() => {
    const dir = destinations.data?.default_directory;
    if (!prefilled.current && dir) { prefilled.current = true; setSettings((s) => (s.saveLocation ? s : { ...s, saveLocation: dir })); }
  }, [destinations.data]);

  const change = (patch: Partial<RenderSettings>) => setSettings((s) => ({ ...s, ...patch }));
  const refresh = () => queryClient.invalidateQueries({ queryKey: workbenchKeys.renders(project.id) });

  // Follow a render to its end: the one running when the stage opened, or one started here.
  const tracked = React.useRef<string | null>(null);
  const handled = React.useRef(new Set<string>());
  React.useEffect(() => {
    if (!rendersQuery.data) return;
    if (active) { tracked.current = active.render_id; return; }
    const id = tracked.current;
    if (!id || handled.current.has(id)) return;
    const done = rendersQuery.data.find((r) => r.render_id === id);
    if (!done || isRunning(done)) return;
    handled.current.add(id);
    tracked.current = null;
    if (done.status === "COMPLETE") {
      void api.getProject(project.id).then((updated) => { onRenderComplete(updated); toast.show("Render finished."); }).catch(() => setError("The render finished, but the project could not be reloaded. Reload the page."));
    } else if (done.status === "CANCELLED") {
      setNotice("Render cancelled.");
    } else if (done.status === "FAILED") {
      setError(refusal("Render failed.", new Error(done.error_message ?? ""), RENDER_ADVICE));
      reportError({ title: "Render Job Failed", message: done.error_message || done.error_code || "Video encoding failed.", severity: "error", source: "pipeline", projectId: project.id, jobId: done.render_id, jobType: "VIDEO_RENDER", rawDetails: done });
    }
  }, [rendersQuery.data, active?.render_id]); // eslint-disable-line react-hooks/exhaustive-deps

  const start = async () => {
    if (busy.current || active || !profileId) return;
    busy.current = true;
    setStarting(true);
    setError(null);
    setNotice(null);
    try {
      await api.startRender(project.id, startOptions({ ...settings, profile: profileId }));
      await refresh();
    } catch (err: any) {
      setError("Couldn't start the render. Check that the engine is running, then try again.");
      reportError({ title: "Render Failed to Start", message: "An error occurred starting the render job.", severity: "error", source: "pipeline", projectId: project.id, jobType: "VIDEO_RENDER", rawDetails: err });
    } finally { busy.current = false; setStarting(false); }
  };

  const cancel = async () => {
    if (!active || cancelBusy.current) return;
    cancelBusy.current = true;
    setCancelling(true);
    try {
      await api.cancelRender(project.id, active.render_id);
      await refresh();
    } catch (err: any) {
      setError("Couldn't cancel the render. Try again in a moment.");
      reportError({ title: "Render Cancellation Failed", message: "Failed to cancel the active render job.", severity: "warning", source: "pipeline", projectId: project.id, jobId: active.render_id, jobType: "VIDEO_RENDER", rawDetails: err });
    } finally { cancelBusy.current = false; setCancelling(false); }
  };

  const browse = async (kind: "folder" | "file") => {
    setPickerError(null);
    try {
      const res = kind === "folder"
        ? await api.pickDirectoryNative(settings.saveLocation || undefined, "Select the video folder")
        : await api.pickSaveFileNative(settings.saveLocation || undefined, `${project.title.replace(/\s+/g, "_").toLowerCase()}_${profileId || "video"}.mp4`, "Save the video as");
      if (res?.selected && res.path) change({ saveLocation: res.path });
    } catch {
      setPickerError(kind === "folder" ? "Couldn't open the folder picker. Paste the folder path instead." : "Couldn't open the file picker. Paste the file path instead.");
    }
  };

  const opening = React.useRef(false); // one open at a time: a double click must not open two windows
  const openFile = async (path: string) => {
    if (opening.current) return;
    opening.current = true;
    try { await api.openPath(path, true); }
    catch { setError("Couldn't open that file. It may have been moved."); }
    finally { opening.current = false; }
  };

  const viewed: RenderJob | undefined = active ?? latestRender(renders) ?? renders[0];
  const shown: RenderJob | undefined = renders.find((r) => r.render_id === viewedId) ?? latestRender(renders);
  const statusChip = viewed ? <Chip tone={renderStatus(viewed.status).tone}>{renderStatus(viewed.status).word}</Chip> : <Chip>Not rendered</Chip>;
  const noProfiles = !choices.fromEngine && !profilesQuery.isLoading;

  if (rendersQuery.isError) return <ErrorState title="Couldn't load the renders" description="Check that the engine is running, then try again." onRetry={() => void rendersQuery.refetch()} />;

  return (
    <div className="grid grid-cols-1 gap-5">
      <StageToolbar
        title="Render the video"
        description="Choose how the video is made, start the render, and check the result."
        status={statusChip}
        actions={active
          ? <Button variant="danger" size="sm" loading={cancelling} onClick={() => void cancel()}>Cancel render</Button>
          : <Button variant="primary" size="sm" loading={starting} disabled={!profileId} onClick={() => void start()}>Start render</Button>}
      />

      {noProfiles && <p role="alert" className="text-sm text-warn">Couldn't load the render profiles. Check that the engine is running.</p>}
      {error && <p role="alert" className="text-sm text-bad">{error}</p>}
      {notice && <p role="status" className="text-sm text-fg-dim">{notice}</p>}

      {active && (
        <GlassPanel blur={false} className="grid grid-cols-1 gap-3 p-4" role="status">
          <div className="flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2"><Chip tone="accent">{renderStatus(active.status).word}</Chip><h3 className="font-display text-sm font-semibold text-fg">Rendering the video</h3></div>
            <span className="font-data text-sm text-fg-dim">{`${active.frames_done.toLocaleString("en-US")} / ${active.frames_total.toLocaleString("en-US")} frames`}</span>
          </div>
          <Progress value={Math.round((active.progress <= 1 ? active.progress * 100 : active.progress))} label="Render progress" />
          <p className="text-xs text-fg-dim">{`Profile ${active.output_profile}${active.elapsed_sec ? ` · ${active.elapsed_sec.toFixed(1)}s elapsed` : ""}`}</p>
        </GlassPanel>
      )}

      {!active && (profilesQuery.isLoading
        ? <Skeleton className="h-64" />
        : <RenderSettingsPanel settings={{ ...settings, profile: profileId }} onChange={change} profiles={choices.options} destinations={destinations.data?.destinations ?? []} onBrowseFolder={() => void browse("folder")} onBrowseFile={() => void browse("file")} pickerError={pickerError} />)}

      {!active && shown && shown.status === "COMPLETE" && <RenderResult key={shown.render_id} projectId={project.id} render={shown} onPublish={() => nav.goTo("publish")} />}

      <section className="grid grid-cols-1 gap-3" aria-label="Renders">
        <h3 className="font-display text-sm font-semibold text-fg">Render history</h3>
        {rendersQuery.isLoading ? <Skeleton className="h-24" /> : <RenderHistory renders={renders} onView={(r) => setViewedId(r.render_id)} onOpenFile={(path) => void openFile(path)} />}
      </section>
    </div>
  );
};
