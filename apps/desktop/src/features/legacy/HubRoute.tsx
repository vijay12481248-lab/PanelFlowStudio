import React from "react";
import { useNavigate } from "react-router";
import { DashboardShell } from "../../components/dashboard";
import { useEngine } from "../../app/providers";
import { isChronoFlowProject, paths, stageForProject } from "../../app/routes";

/** The existing dashboard, mounted inside the new shell until the M3 Home, Projects and Jobs screens replace it. */
export const HubRoute: React.FC = () => {
  const navigate = useNavigate();
  const engine = useEngine();
  return (
    <DashboardShell
      embedded
      engineConnected={engine.connected}
      engineVersion={engine.version}
      onRetryEngine={() => void engine.retry()}
      retryingEngine={engine.retrying}
      onRestartEngine={() => void engine.restart()}
      restartingEngine={engine.restarting}
      onOpenToolsModels={() => navigate(paths.settings("engine"), { state: { open: true } })}
      onOpenProviderManagement={() => navigate(paths.settings("providers"))}
      onNewProject={() => navigate(paths.create("new"))}
      onOpenAnimeReview={() => navigate(paths.create("anime"))}
      onOpenOriginalStories={() => navigate(paths.create("stories"))}
      onOpenChronoFlow={(project) => navigate(paths.chronoflow({ projectId: project?.id }))}
      onOpenChronoFlowJob={(jobId) => navigate(paths.chronoflow({ jobId }))}
      onOpenAcquisition={(project) => navigate(paths.stage(project.id, "acquire"))}
      onOpenReview={(project) => navigate(paths.stage(project.id, "pages"))}
      onOpenPanels={(project) => navigate(paths.stage(project.id, "panels"))}
      onOpenOCR={(project) => navigate(paths.stage(project.id, "ocr"))}
      onOpenStoryEditor={(project) => navigate(paths.editor(project.id))}
      onOpenProject={(project) => navigate(isChronoFlowProject(project) ? paths.chronoflow({ projectId: project.id }) : paths.stage(project.id, stageForProject(project)))}
      onOpenLibrary={() => navigate(paths.settings("engine"), { state: { open: true } })}
    />
  );
};
