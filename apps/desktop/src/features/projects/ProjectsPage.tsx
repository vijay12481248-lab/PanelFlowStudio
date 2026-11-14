import React from "react";
import { useNavigate } from "react-router";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { api } from "@panelflow/api-client";
import type { Project } from "@panelflow/shared-types";
import { Button, Dialog, EmptyState, ErrorState, GlassPanel, Input, PageHeader, Skeleton, Tabs, useToast } from "@panelflow/ui-v2";
import { useError } from "../../context/ErrorContext";
import { isChronoFlowProject, paths, stageForProject } from "../../app/routes";
import { queryKeys, useJobs, useProjectCovers, useProjects } from "../data/queries";
import { buildInbox } from "../home/inbox";
import { CreationsSection } from "./CreationsSection";
import { loadFavorites, saveFavorites, toggleFavorite } from "./favorites";
import { ProjectTile } from "./ProjectTile";
import { filterProjects, groupBySeries, type ProjectFilter } from "./projectsView";

export const ProjectsPage: React.FC = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const toast = useToast();
  const { reportError } = useError();
  const projects = useProjects();
  const jobs = useJobs();
  const all = projects.data ?? [];
  const covers = useProjectCovers(all);

  const [query, setQuery] = React.useState("");
  const [filter, setFilter] = React.useState<ProjectFilter>("all");
  const [favorites, setFavorites] = React.useState(() => loadFavorites(window.localStorage));
  const [toDelete, setToDelete] = React.useState<Project | null>(null);
  const deleting = React.useRef(false); // set synchronously: state alone lets a very fast double click submit twice

  const needsYou = React.useMemo(
    () => new Set(buildInbox({ projects: all, jobs: jobs.data ?? [], series: [] }).flatMap((item) => (item.projectId ? [item.projectId] : []))),
    [all, jobs.data],
  );
  const visible = React.useMemo(() => filterProjects(all, { query, filter, favorites, needsYou }), [all, query, filter, favorites, needsYou]);
  const { groups, singles } = React.useMemo(() => groupBySeries(visible), [visible]);

  const remove = useMutation({
    mutationFn: (project: Project) => api.deleteProject(project.id),
    onSuccess: (_, project) => {
      queryClient.setQueryData<Project[]>(queryKeys.projects, (old) => old?.filter((p) => p.id !== project.id));
      toast.show("Project deleted", "ok");
    },
    onError: (error: Error, project) =>
      reportError({ title: "Couldn't delete the project", message: error.message || "The engine did not delete it. Try again.", severity: "error", source: "engine", projectId: project.id }),
  });

  const open = (project: Project) =>
    navigate(isChronoFlowProject(project) ? paths.chronoflow({ projectId: project.id }) : paths.stage(project.id, stageForProject(project)));

  const tile = (project: Project) => (
    <ProjectTile
      key={project.id}
      project={project}
      coverUrl={covers[project.id]}
      favorite={Boolean(favorites[project.id])}
      needsYou={needsYou.has(project.id)}
      onOpen={() => open(project)}
      onToggleFavorite={() => setFavorites((current) => { const next = toggleFavorite(current, project.id); saveFavorites(window.localStorage, next); return next; })}
      onOpenEditor={() => navigate(paths.editor(project.id))}
      onOpenFolder={() => void api.openProjectFolder(project.id).catch(() => reportError({ title: "Couldn't open the folder", message: "The project folder could not be opened. Check that it still exists.", severity: "warning", source: "ui", projectId: project.id }))}
      onDelete={() => setToDelete(project)}
    />
  );
  const grid = (items: Project[]) => <div className="grid grid-cols-2 gap-5 md:grid-cols-3 xl:grid-cols-4">{items.map(tile)}</div>;

  let body: React.ReactNode;
  if (projects.isError) {
    body = <ErrorState title="Couldn't load projects" description="Check that the engine is running, then try again." onRetry={() => void projects.refetch()} />;
  } else if (projects.isLoading || !projects.data) {
    body = <div className="grid grid-cols-4 gap-5">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="aspect-square" />)}</div>;
  } else if (all.length === 0) {
    body = <EmptyState title="No projects yet" description="Import manga pages to start your first project." action={<Button variant="primary" onClick={() => navigate(paths.create("new"))}>Create a project</Button>} />;
  } else if (visible.length === 0) {
    body = <EmptyState title="No projects match" description="Try a different search or filter." />;
  } else {
    body = (
      <div className="grid gap-8 grid-cols-1">
        {groups.map((group) => (
          <section key={group.series} className="grid gap-3 grid-cols-1">
            <h2 className="font-display text-base font-semibold text-fg">{group.series}</h2>
            {grid(group.projects)}
          </section>
        ))}
        {singles.length > 0 && (
          <section className="grid gap-3 grid-cols-1">
            {groups.length > 0 && <h2 className="font-display text-base font-semibold text-fg">Other projects</h2>}
            {grid(singles)}
          </section>
        )}
      </div>
    );
  }

  return (
    <div className="mx-auto grid w-full max-w-6xl gap-6 p-6 md:p-8 grid-cols-1">
      <PageHeader
        title="Projects"
        meta={<span>{`${all.length} ${all.length === 1 ? "project" : "projects"}`}</span>}
        actions={<Button variant="primary" onClick={() => navigate(paths.create("new"))}>Create a project</Button>}
      />
      <GlassPanel className="grid gap-4 p-4 grid-cols-1">
        <Input type="search" placeholder="Search projects" aria-label="Search projects" value={query} onChange={(event) => setQuery(event.target.value)} />
        <Tabs
          value={filter}
          onValueChange={(value) => setFilter(value as ProjectFilter)}
          tabs={[{ value: "all", label: "All" }, { value: "needs-you", label: `Needs you ${needsYou.size}` }, { value: "favorites", label: "Favorites" }]}
        >
          {body}
        </Tabs>
      </GlassPanel>
      <CreationsSection />
      <Dialog
        open={toDelete !== null}
        onOpenChange={(isOpen) => { if (!isOpen) setToDelete(null); }}
        title={toDelete ? `Delete ${toDelete.title}?` : "Delete project?"}
        description="This removes the project and its workspace. You cannot undo this."
        footer={
          <>
            <Button variant="ghost" onClick={() => setToDelete(null)}>Cancel</Button>
            <Button variant="danger" loading={remove.isPending} onClick={() => {
              if (!toDelete || deleting.current) return;
              deleting.current = true;
              remove.mutate(toDelete, { onSettled: () => { deleting.current = false; } });
              setToDelete(null);
            }}>Delete project</Button>
          </>
        }
      >
        Its pages, panels, scripts and renders are deleted from this PC.
      </Dialog>
    </div>
  );
};
