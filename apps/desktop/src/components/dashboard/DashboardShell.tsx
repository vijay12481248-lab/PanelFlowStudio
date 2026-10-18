import React, { useState, useEffect, useCallback } from "react";
import { SidebarClose, SidebarOpen } from "lucide-react";
import { api } from "@panelflow/api-client";
import type { Project, Job, SystemResourcesResponse } from "@panelflow/shared-types";
import type { NavTabId, DashboardShellProps } from "./types";
import { DashboardHeader } from "./DashboardHeader";
import { AppNavigationRail } from "./AppNavigationRail";
import { JobQueueSidebar } from "./JobQueueSidebar";
import { SystemOverviewCards } from "./SystemOverviewCards";
import { ProjectsWorkspace } from "./ProjectsWorkspace";
import { QuickActionsPanel } from "./QuickActionsPanel";
import { RecentActivityPanel } from "./RecentActivityPanel";
import { DashboardPromoCard } from "./DashboardPromoCard";

export const DashboardShell: React.FC<DashboardShellProps> = ({
  engineConnected,
  engineVersion,
  onRetryEngine,
  retryingEngine,
  onOpenToolsModels,
  onNewProject,
  onOpenAcquisition,
  onOpenReview,
  onOpenPanels,
  onOpenOCR,
  onOpenStoryEditor,
  onOpenLibrary,
}) => {
  // Navigation & view states
  const [activeNavTab, setActiveNavTab] = useState<NavTabId>("home");
  const [rightSidebarOpen, setRightSidebarOpen] = useState(true);

  // Data states
  const [projects, setProjects] = useState<Project[]>([]);
  const [projectCovers, setProjectCovers] = useState<Record<string, string>>({});
  const [jobs, setJobs] = useState<Job[]>([]);
  const [resources, setResources] = useState<SystemResourcesResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Favorites state persisted to localStorage
  const [favorites, setFavorites] = useState<Record<string, boolean>>(() => {
    try {
      const stored = localStorage.getItem("panelflow_project_favorites");
      return stored ? JSON.parse(stored) : {};
    } catch {
      return {};
    }
  });

  const handleToggleFavorite = (projectId: string) => {
    setFavorites((prev) => {
      const updated = { ...prev, [projectId]: !prev[projectId] };
      try {
        localStorage.setItem("panelflow_project_favorites", JSON.stringify(updated));
      } catch (err) {
        console.warn("Could not persist favorites:", err);
      }
      return updated;
    });
  };

  // Fetch projects, covers, jobs, and system telemetry
  const loadData = useCallback(async () => {
    try {
      const [projData, jobsData, sysResources] = await Promise.all([
        api.listProjects().catch((err) => {
          console.warn("Projects load warning:", err.message);
          return [] as Project[];
        }),
        api.listAllJobs(undefined, undefined, 40).catch((err) => {
          console.warn("Jobs load warning:", err.message);
          return [] as Job[];
        }),
        api.getSystemResources().catch(() => null),
      ]);

      setProjects(projData);
      setJobs(jobsData);
      if (sysResources) {
        setResources(sysResources);
      }
      setError(null);

      // Asynchronously fetch cover page for each project
      const coverMap: Record<string, string> = {};
      await Promise.all(
        projData.map(async (p) => {
          try {
            const pages = await api.listPages(p.id);
            if (pages && pages.length > 0) {
              const firstPage = pages.find((pg) => pg.sequence === 1) || pages[0];
              coverMap[p.id] = api.getPageImageUrl(p.id, firstPage.id);
            }
          } catch {
            // ignore
          }
        })
      );
      setProjectCovers(coverMap);
    } catch (err: any) {
      setError(err.message || "Failed to connect to PanelFlow local engine.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadData();

    // Check interval based on whether jobs are currently in flight
    const hasRunningOrQueued = jobs.some(
      (j) => j.status === "RUNNING" || j.status === "QUEUED"
    );
    const intervalMs = hasRunningOrQueued ? 3000 : 8000;

    const timer = setInterval(() => {
      loadData();
    }, intervalMs);

    return () => clearInterval(timer);
  }, [loadData, jobs.some((j) => j.status === "RUNNING" || j.status === "QUEUED")]);

  // Project action handlers
  const handleOpenFolder = async (projectId: string) => {
    try {
      await api.openProjectFolder(projectId);
    } catch (err: any) {
      alert(`Could not open folder: ${err.message}`);
    }
  };

  const handleDeleteProject = async (projectId: string) => {
    if (!window.confirm("Are you sure you want to delete this project and its workspace?")) {
      return;
    }
    try {
      await api.deleteProject(projectId);
      setProjects((prev) => prev.filter((p) => p.id !== projectId));
    } catch (err: any) {
      alert(`Delete failed: ${err.message}`);
    }
  };

  const handleRetryJob = async (jobId: string) => {
    try {
      await api.retryJob(jobId);
      await loadData();
    } catch (err: any) {
      alert(`Retry failed: ${err.message}`);
    }
  };

  const handleCancelJob = async (jobId: string) => {
    try {
      await api.cancelJob(jobId);
      await loadData();
    } catch (err: any) {
      alert(`Cancel failed: ${err.message}`);
    }
  };

  // Counts for summary telemetry
  const runningCount = jobs.filter((j) => j.status === "RUNNING").length;
  const queuedCount = jobs.filter((j) => j.status === "QUEUED").length;
  const completedCount = jobs.filter((j) => j.status === "SUCCEEDED").length;

  return (
    <div className="h-screen w-screen flex flex-col bg-[#090b10] text-zinc-100 overflow-hidden font-sans select-none">
      {/* 1. TOP HEADER */}
      <DashboardHeader
        engineConnected={engineConnected}
        engineVersion={engineVersion}
        onOpenToolsModels={onOpenToolsModels}
        onRetryEngine={onRetryEngine}
        retryingEngine={retryingEngine}
      />

      {/* 2. MAIN HORIZONTAL MULTI-COLUMN WORKSPACE */}
      <div className="flex-1 flex min-h-0 overflow-hidden">
        {/* Far-Left Navigation Rail (68px) */}
        <AppNavigationRail
          activeTab={activeNavTab}
          onSelectTab={setActiveNavTab}
          onOpenSettings={onOpenToolsModels}
          onOpenLibrary={onOpenLibrary}
        />

        {/* Left Job Queue Sidebar (~310px) */}
        <JobQueueSidebar
          jobs={jobs}
          projects={projects}
          coversMap={projectCovers}
          onRetryJob={handleRetryJob}
          onCancelJob={handleCancelJob}
          onNavigateProject={onOpenStoryEditor}
        />

        {/* Central Workspace (Flex-1) */}
        <main className="flex-1 min-w-0 flex flex-col overflow-y-auto p-3.5 sm:p-5 space-y-4 sm:space-y-5 bg-[#090b10] scrollbar-thin scrollbar-thumb-zinc-800">
          {/* Top 4 System Telemetry Cards */}
          <SystemOverviewCards
            resources={resources}
            engineConnected={engineConnected}
            engineVersion={engineVersion}
            runningCount={runningCount}
            queuedCount={queuedCount}
            completedCount={completedCount}
            onOpenToolsModels={onOpenToolsModels}
            onFocusJobs={() => setActiveNavTab("jobs")}
          />

          {/* Main Your Projects Section */}
          <ProjectsWorkspace
            projects={projects}
            favorites={favorites}
            coversMap={projectCovers}
            onToggleFavorite={handleToggleFavorite}
            onNewProject={onNewProject}
            onOpenStoryEditor={onOpenStoryEditor}
            onOpenOCR={onOpenOCR}
            onOpenPanels={onOpenPanels}
            onOpenFolder={handleOpenFolder}
            onDeleteProject={handleDeleteProject}
          />
        </main>

        {/* Right Sidebar (~280px) */}
        {rightSidebarOpen ? (
          <aside className="w-[280px] min-w-[260px] max-w-[310px] bg-[#0c0e17]/95 border-l border-[#181c2b] flex flex-col flex-shrink-0 h-full overflow-hidden select-none transition-all">
            <div className="flex items-center justify-end px-3 pt-2 lg:hidden">
              <button
                onClick={() => setRightSidebarOpen(false)}
                className="p-1 rounded text-zinc-500 hover:text-zinc-300"
                title="Collapse sidebar"
              >
                <SidebarClose className="w-4 h-4" />
              </button>
            </div>
            <div className="flex-1 overflow-y-auto p-4 space-y-5 scrollbar-thin scrollbar-thumb-zinc-800">
              {/* Quick Actions */}
              <QuickActionsPanel
                onNewProject={onNewProject}
                onImportPages={onNewProject}
                onOpenLibrary={onOpenLibrary}
                onModelSettings={onOpenToolsModels}
                onEngineSettings={onOpenToolsModels}
              />

              {/* Recent Activity Feed */}
              <RecentActivityPanel
                jobs={jobs}
                projects={projects}
                onNavigateProject={onOpenStoryEditor}
                onViewAll={() => setActiveNavTab("jobs")}
              />

              {/* Contextual Promo Card */}
              <DashboardPromoCard onAction={onNewProject} />
            </div>
          </aside>
        ) : (
          <div className="p-2 border-l border-[#181c2b] bg-[#0c0e17] flex flex-col items-center">
            <button
              onClick={() => setRightSidebarOpen(true)}
              className="p-1.5 rounded-lg bg-[#151928] border border-[#242c44] text-zinc-400 hover:text-zinc-200 transition-colors"
              title="Open right panel"
            >
              <SidebarOpen className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>
    </div>
  );
};
