import type { Project, Job, SystemResourcesResponse } from "@panelflow/shared-types";

export type NavTabId = "home" | "projects" | "jobs" | "library" | "settings";
export type ProjectViewMode = "grid" | "list";
export type ProjectFilterTab = "all" | "recent" | "favorites";

export interface DashboardActivityItem {
  id: string;
  title: string;
  projectName: string;
  projectId?: string;
  timestamp: string;
  relativeTime: string;
  type: "check" | "play" | "queue" | "doc" | "error";
}

export interface DashboardShellProps {
  engineConnected: boolean;
  engineVersion: string;
  onRetryEngine: () => void;
  retryingEngine: boolean;
  onOpenToolsModels: () => void;
  onNewProject: () => void;
  onOpenAcquisition: (project: Project) => void;
  onOpenReview: (project: Project) => void;
  onOpenPanels: (project: Project) => void;
  onOpenOCR: (project: Project) => void;
  onOpenStoryEditor: (project: Project) => void;
  onOpenProject?: (project: Project) => void;
  onOpenLibrary?: () => void;
}
