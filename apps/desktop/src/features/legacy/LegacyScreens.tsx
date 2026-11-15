import React from "react";
import { Navigate, useNavigate, useParams, useSearchParams } from "react-router";
import { useQuery } from "@tanstack/react-query";
import { api } from "@panelflow/api-client";
import { ErrorState, Skeleton } from "@panelflow/ui-v2";
import type { Project } from "@panelflow/shared-types";
import { NewProjectScreen } from "../../screens/NewProjectScreen";
import { OriginalStoriesScreen } from "../../screens/OriginalStoriesScreen";
import { AnimeReviewScreen } from "../../screens/AnimeReviewScreen";
import { ChronoFlowScreen } from "../../screens/ChronoFlowScreen";
import { StoryEditorScreen } from "../../screens/StoryEditorScreen";
import { useEngine } from "../../app/providers";
import { isChronoFlowProject, paths, stageForProject } from "../../app/routes";

function useProject(id: string | undefined) {
  return useQuery({ queryKey: ["project", id], queryFn: () => api.getProject(id as string), enabled: Boolean(id), retry: false });
}

const Loading: React.FC = () => <div className="mx-auto grid max-w-5xl gap-4 p-8 grid-cols-1"><Skeleton className="h-10 w-72" /><Skeleton className="h-64 w-full" /></div>;

const ProjectMissing: React.FC = () => {
  const navigate = useNavigate();
  return <ErrorState title="This project no longer exists" description="It may have been deleted. Go back to your projects." onBack={() => navigate(paths.projects())} />;
};

export const NewProjectRoute: React.FC = () => {
  const navigate = useNavigate();
  return (
    <div className="mx-auto w-full max-w-7xl p-6 md:p-8">
      <NewProjectScreen
        onBack={() => navigate(paths.create())}
        onProjectCreated={(project: Project) => navigate(isChronoFlowProject(project) ? paths.chronoflow({ projectId: project.id }) : paths.stage(project.id, "acquire"))}
      />
    </div>
  );
};

export const StoriesRoute: React.FC = () => {
  const navigate = useNavigate();
  return <OriginalStoriesScreen onBack={() => navigate(paths.projects())} />;
};

export const AnimeRoute: React.FC = () => {
  const navigate = useNavigate();
  return <AnimeReviewScreen onBack={() => navigate(paths.projects())} />;
};

export const ChronoFlowRoute: React.FC = () => {
  const { projectId, jobId } = useParams();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const project = useProject(projectId);
  const tab = params.get("tab");
  const story = params.get("story");
  if (projectId && project.isError) return <ProjectMissing />;
  if (projectId && !project.data) return <Loading />;
  return <ChronoFlowScreen project={project.data ?? null} jobId={jobId ?? null} tab={tab} story={story} onBack={() => navigate(paths.home())} />;
};

/** Same screen as ChronoFlow's Image Studio "Generate New Image" (one art path: ArtEngine). */
export const ImageRoute: React.FC = () => {
  const navigate = useNavigate();
  return <ChronoFlowScreen project={null} jobId={null} tab="image-generate" story={null} onBack={() => navigate(paths.create())} />;
};

export const EditorRoute: React.FC = () => {
  const { id } = useParams();
  const navigate = useNavigate();
  const engine = useEngine();
  const project = useProject(id);
  if (project.isError) return <ProjectMissing />;
  if (!project.data) return <Loading />;
  return <StoryEditorScreen project={project.data} engineConnected={engine.connected} onBack={() => navigate(paths.projects())} onExport={() => { /* handled by the built-in export dialog */ }} />;
};

/** `/projects/:id` opens the project at the stage it has reached. */
export const ProjectRedirect: React.FC = () => {
  const { id } = useParams();
  const project = useProject(id);
  if (project.isError) return <ProjectMissing />;
  if (!project.data) return <Loading />;
  return <Navigate to={isChronoFlowProject(project.data) ? paths.chronoflow({ projectId: project.data.id }) : paths.stage(project.data.id, stageForProject(project.data))} replace />;
};
