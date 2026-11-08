import React from "react";
import { useNavigate } from "react-router";
import { Button, ErrorState, GlassPanel, PageHeader, Skeleton, Tile } from "@panelflow/ui-v2";
import type { Project } from "@panelflow/shared-types";
import { isChronoFlowProject, paths, stageForProject } from "../../app/routes";
import { useJobs, useOriginalSeries, useProjectCovers, useProjects, useRetryJob } from "../data/queries";
import { projectInitials, stageLabel } from "../projects/projectsView";
import { buildInbox, pickFocusProject, type InboxItem } from "./inbox";
import { NeedsYou } from "./NeedsYou";
import { ProjectHero } from "./ProjectHero";
import { RunningNow } from "./RunningNow";

const RECENT = 4;

export const HomePage: React.FC = () => {
  const navigate = useNavigate();
  const projects = useProjects();
  const jobs = useJobs();
  const series = useOriginalSeries();
  const retry = useRetryJob();
  const inFlight = React.useRef(new Set<string>()); // synchronous guard against a fast double click

  const all = projects.data ?? [];
  const items = React.useMemo(() => buildInbox({ projects: all, jobs: jobs.data ?? [], series: series.data ?? [] }), [all, jobs.data, series.data]);
  const focus = pickFocusProject(all, items);
  const recent = React.useMemo(() => [...all].sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at)).slice(0, RECENT), [all]);
  const covers = useProjectCovers(focus ? [focus, ...recent.filter((p) => p.id !== focus.id)] : recent);
  const titles = React.useMemo(() => new Map(all.map((p) => [p.id, p.title])), [all]);

  const open = (project: Project) =>
    navigate(isChronoFlowProject(project) ? paths.chronoflow({ projectId: project.id }) : paths.stage(project.id, stageForProject(project)));

  const act = async (item: InboxItem) => {
    if (item.action.type === "open") return navigate(item.action.to);
    const { jobId } = item.action;
    if (inFlight.current.has(jobId)) return;
    inFlight.current.add(jobId);
    try { await retry.mutateAsync(jobId); } finally { inFlight.current.delete(jobId); }
  };

  if (projects.isError) {
    return <ErrorState title="Couldn't load your projects" description="Check that the engine is running, then try again." onRetry={() => void projects.refetch()} />;
  }
  if (projects.isLoading || !projects.data) {
    return <div className="mx-auto grid max-w-6xl gap-4 p-8 grid-cols-1"><Skeleton className="h-10 w-48" /><Skeleton className="h-64" /></div>;
  }

  const focusItem = focus ? items.find((item) => item.projectId === focus.id) : undefined;
  return (
    <div className="mx-auto grid w-full max-w-6xl gap-6 p-6 md:p-8 grid-cols-1">
      <PageHeader title="Home" meta={<span>{items.length === 0 ? "All clear" : `${items.length} ${items.length === 1 ? "thing needs" : "things need"} you`}</span>} />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1.25fr)_minmax(0,1fr)]">
        <div className="grid content-start gap-6 grid-cols-1">
          {focus && <ProjectHero project={focus} coverUrl={covers[focus.id]} note={focusItem?.title} onContinue={() => (focusItem?.action.type === "open" ? navigate(focusItem.action.to) : open(focus))} />}
          {recent.length > 0 && (
            <section aria-label="Recent projects" className="grid gap-3 grid-cols-1">
              <div className="flex items-center justify-between">
                <h2 className="font-display text-sm font-semibold text-fg">Recent projects</h2>
                <Button variant="ghost" size="sm" onClick={() => navigate(paths.projects())}>All projects</Button>
              </div>
              <div className="grid grid-cols-2 gap-4 md:grid-cols-4">
                {recent.map((project) => (
                  <Tile key={project.id} title={project.title} subtitle={stageLabel(project.current_stage)} fallbackText={projectInitials(project.title)} imageUrl={covers[project.id]} onOpen={() => open(project)} />
                ))}
              </div>
            </section>
          )}
        </div>
        <div className="grid content-start gap-6 grid-cols-1">
          <GlassPanel className="grid gap-3 p-4 grid-cols-1">
            <h2 className="font-display text-sm font-semibold text-fg">Needs you</h2>
            <NeedsYou items={items} onAction={(item) => void act(item)} onCreate={() => navigate(paths.create("new"))} onOpenStories={() => navigate(paths.create("stories"))} />
          </GlassPanel>
          <RunningNow jobs={jobs.data ?? []} projectTitles={titles} />
        </div>
      </div>
    </div>
  );
};
