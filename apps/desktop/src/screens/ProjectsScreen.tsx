import React from "react";
import type { Project } from "@panelflow/shared-types";
import { DashboardShell } from "../components/dashboard";

interface ProjectsScreenProps {
  onNewProject: () => void;
  onOpenAcquisition: (project: Project) => void;
  onOpenReview: (project: Project) => void;
  onOpenPanels: (project: Project) => void;
  onOpenOCR?: (project: Project) => void;
  onOpenStory?: (project: Project) => void;
  onOpenScript?: (project: Project) => void;
  onOpenAudio?: (project: Project) => void;
  onOpenMotion?: (project: Project) => void;
  onOpenRender?: (project: Project) => void;
  onOpenStoryEditor?: (project: Project) => void;
  onOpenLibrary?: () => void;
  engineConnected?: boolean;
  engineVersion?: string;
  onRetryEngine?: () => void;
  retryingEngine?: boolean;
  onOpenToolsModels?: () => void;
}

export const ProjectsScreen: React.FC<ProjectsScreenProps> = ({
  onNewProject,
  onOpenAcquisition,
  onOpenReview,
  onOpenPanels,
  onOpenOCR,
  onOpenStoryEditor,
  onOpenLibrary,
  engineConnected = true,
  engineVersion = "1.0.0-beta.2",
  onRetryEngine = () => {},
  retryingEngine = false,
  onOpenToolsModels = () => {},
}) => {
  return (
    <DashboardShell
      engineConnected={engineConnected}
      engineVersion={engineVersion}
      onRetryEngine={onRetryEngine}
      retryingEngine={retryingEngine}
      onOpenToolsModels={onOpenToolsModels}
      onNewProject={onNewProject}
      onOpenAcquisition={onOpenAcquisition}
      onOpenReview={onOpenReview}
      onOpenPanels={onOpenPanels}
      onOpenOCR={onOpenOCR || onOpenPanels}
      onOpenStoryEditor={onOpenStoryEditor || onOpenPanels}
      onOpenLibrary={onOpenLibrary}
    />
  );
};
