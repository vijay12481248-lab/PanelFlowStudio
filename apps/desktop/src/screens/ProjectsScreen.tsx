import React, { useEffect, useState } from "react";
import { api } from "@panelflow/api-client";
import type { Project } from "@panelflow/shared-types";
import { Button, Card, Badge, Icons } from "@panelflow/ui";
import { MultiProjectQueueDashboard } from "../components/MultiProjectQueueDashboard";

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
}

export const ProjectsScreen: React.FC<ProjectsScreenProps> = ({
  onNewProject,
  onOpenAcquisition,
  onOpenReview,
  onOpenPanels,
  onOpenOCR,
  onOpenStory,
  onOpenScript,
  onOpenAudio,
  onOpenMotion,
  onOpenRender,
  onOpenStoryEditor,
}) => {
  const [projects, setProjects] = useState<Project[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const loadProjects = async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await api.listProjects();
      setProjects(data);
    } catch (err: any) {
      setError(err.message || "Failed to connect to PanelFlow local engine.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadProjects();
  }, []);

  const handleDelete = async (e: React.MouseEvent, projectId: string) => {
    e.stopPropagation();
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

  const handleOpenFolder = async (e: React.MouseEvent, projectId: string) => {
    e.stopPropagation();
    try {
      await api.openProjectFolder(projectId);
    } catch (err: any) {
      alert(`Could not open folder: ${err.message}`);
    }
  };

  const getRightsBadgeVariant = (rights: string) => {
    switch (rights) {
      case "PUBLIC_DOMAIN":
      case "CREATIVE_COMMONS":
      case "USER_OWNED":
        return "success";
      case "LICENSED":
      case "EXPLICIT_PERMISSION":
        return "accent";
      default:
        return "danger";
    }
  };

  const getStageBadgeVariant = (stage: string) => {
    switch (stage) {
      case "RENDERED":
      case "MOTION_APPROVED":
      case "AUDIO_APPROVED":
      case "SCRIPT_APPROVED":
      case "STORY_APPROVED":
      case "OCR_APPROVED":
      case "OCR_COMPLETE":
      case "PANELS_DETECTED":
      case "ACQUIRED":
        return "success";
      case "NORMALIZED":
      case "RIGHTS_APPROVED":
      case "VOICE_GENERATED":
      case "SHOT_PLAN_GENERATED":
        return "accent";
      default:
        return "neutral";
    }
  };

  const handleCardClick = (proj: Project) => {
    if (onOpenStoryEditor && proj.current_stage !== "NEW" && proj.current_stage !== "RIGHTS_APPROVED") {
      onOpenStoryEditor(proj);
      return;
    }
    if (proj.current_stage === "RENDERED" || proj.current_stage === "QA_APPROVED" || proj.current_stage === "EXPORTED") {
      if (onOpenRender) onOpenRender(proj);
      else if (onOpenMotion) onOpenMotion(proj);
    } else if (proj.current_stage === "SHOT_PLAN_GENERATED" || proj.current_stage === "MOTION_APPROVED") {
      if (onOpenMotion) onOpenMotion(proj);
      else if (onOpenAudio) onOpenAudio(proj);
    } else if (proj.current_stage === "VOICE_GENERATED" || proj.current_stage === "AUDIO_APPROVED") {
      if (onOpenAudio) onOpenAudio(proj);
      else if (onOpenScript) onOpenScript(proj);
    } else if (proj.current_stage === "SCRIPT_GENERATED" || proj.current_stage === "SCRIPT_APPROVED") {
      if (onOpenScript) onOpenScript(proj);
      else if (onOpenStory) onOpenStory(proj);
    } else if (proj.current_stage === "STORY_ANALYZED" || proj.current_stage === "STORY_APPROVED") {
      if (onOpenStory) onOpenStory(proj);
      else if (onOpenOCR) onOpenOCR(proj);
    } else if (proj.current_stage === "OCR_COMPLETE" || proj.current_stage === "OCR_APPROVED") {
      if (onOpenOCR) onOpenOCR(proj);
      else onOpenPanels(proj);
    } else if (proj.current_stage === "PANELS_DETECTED") {
      onOpenPanels(proj);
    } else if (proj.current_stage === "ACQUIRED" || proj.current_stage === "NORMALIZED") {
      onOpenReview(proj);
    } else {
      onOpenAcquisition(proj);
    }
  };

  return (
    <div className="space-y-6">
      {/* Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-6 border-b border-zinc-800">
        <div>
          <h2 className="text-2xl font-bold tracking-tight text-zinc-100">Projects</h2>
          <p className="text-sm text-zinc-400 mt-1">
            Manage your imported graphic stories, acquisition pipelines, and motion assets.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <Button variant="secondary" size="md" onClick={loadProjects} title="Refresh projects list">
            <Icons.Refresh className="w-4 h-4" />
            Refresh
          </Button>
          <Button variant="primary" size="md" onClick={onNewProject}>
            <Icons.Plus className="w-4 h-4" />
            New Project
          </Button>
        </div>
      </div>

      {/* Multi-Project Queue Scheduler Dashboard */}
      <MultiProjectQueueDashboard
        projects={projects}
        onNavigateProject={handleCardClick}
      />

      {/* Error state */}
      {error && (
        <div className="p-4 bg-rose-950/50 border border-rose-800 rounded-xl flex items-center justify-between">
          <div className="flex items-center gap-3">
            <Icons.XCircle className="w-5 h-5 flex-shrink-0" />
            <p className="text-sm text-rose-200">{error}</p>
          </div>
          <Button variant="outline" size="sm" onClick={loadProjects}>
            Retry Connection
          </Button>
        </div>
      )}

      {/* Loading state */}
      {loading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {[1, 2, 3].map((i) => (
            <Card key={i} className="animate-pulse h-48 bg-zinc-900/50 border-zinc-800">
              <div className="h-4 bg-zinc-800 rounded w-3/4 mb-4" />
              <div className="h-3 bg-zinc-800 rounded w-1/2 mb-2" />
              <div className="h-3 bg-zinc-800 rounded w-1/3" />
            </Card>
          ))}
        </div>
      ) : projects.length === 0 ? (
        /* Empty State */
        <Card className="text-center py-16 px-4 border-dashed border-zinc-800">
          <div className="w-16 h-16 bg-zinc-800 text-zinc-400 rounded-2xl flex items-center justify-center mx-auto mb-4">
            <Icons.Folder className="w-8 h-8" />
          </div>
          <h3 className="text-lg font-semibold text-zinc-200 mb-1">No Projects Found</h3>
          <p className="text-sm text-zinc-400 max-w-md mx-auto mb-6">
            Get started by creating a new project from a local image sequence folder, a ZIP archive, or an authorized web source.
          </p>
          <Button variant="primary" size="lg" onClick={onNewProject}>
            <Icons.Plus className="w-5 h-5" />
            Create First Project
          </Button>
        </Card>
      ) : (
        /* Projects Grid */
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-5">
          {projects.map((proj) => (
            <Card
              key={proj.id}
              className="group hover:border-zinc-700 transition-all cursor-pointer flex flex-col justify-between"
            >
              <div onClick={() => handleCardClick(proj)}>
                <div className="flex items-start justify-between gap-2 mb-3">
                  <h3 className="font-semibold text-zinc-100 text-base group-hover:text-indigo-400 transition-colors line-clamp-1">
                    {proj.title}
                  </h3>
                  <Badge variant={getStageBadgeVariant(proj.current_stage)}>
                    {proj.current_stage}
                  </Badge>
                </div>

                <div className="flex flex-wrap gap-2 mb-4">
                  <Badge variant={getRightsBadgeVariant(proj.rights_status)}>
                    {proj.rights_status}
                  </Badge>
                  <Badge variant="neutral">
                    {proj.source_type}
                  </Badge>
                </div>

                <div className="space-y-1.5 text-xs text-zinc-400">
                  <div className="flex justify-between">
                    <span>Pages:</span>
                    <span className="font-medium text-zinc-200">
                      {proj.ready_pages} ready / {proj.total_pages} total
                    </span>
                  </div>
                  {proj.failed_pages > 0 && (
                    <div className="flex justify-between text-rose-400">
                      <span>Failed:</span>
                      <span className="font-semibold">{proj.failed_pages} pages</span>
                    </div>
                  )}
                  <div className="flex justify-between">
                    <span>Updated:</span>
                    <span className="text-zinc-500">
                      {new Date(proj.updated_at).toLocaleDateString()} {new Date(proj.updated_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>
                </div>
              </div>

              {/* Card Footer Actions */}
              <div className="pt-4 mt-4 border-t border-zinc-800/80 flex items-center justify-between">
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={(e) => handleOpenFolder(e, proj.id)}
                  title="Open source workspace folder in file manager"
                >
                  <Icons.Folder className="w-3.5 h-3.5" />
                  Files
                </Button>

                <div className="flex items-center gap-2">
                  <Button
                    variant="ghost"
                    size="sm"
                    className="text-rose-400 hover:text-rose-300 hover:bg-rose-950/30"
                    onClick={(e) => handleDelete(e, proj.id)}
                    title="Delete project"
                  >
                    <Icons.Trash className="w-3.5 h-3.5" />
                  </Button>

                  {onOpenStoryEditor && proj.current_stage !== "NEW" && proj.current_stage !== "RIGHTS_APPROVED" && (
                    <Button
                      variant="primary"
                      size="sm"
                      onClick={() => onOpenStoryEditor(proj)}
                      className="bg-indigo-600 hover:bg-indigo-500 text-white font-medium shadow-md shadow-indigo-600/20"
                    >
                      <Icons.Film className="w-3.5 h-3.5 mr-1" />
                      Story Editor
                    </Button>
                  )}

                  {proj.current_stage === "SCRIPT_GENERATED" || proj.current_stage === "SCRIPT_APPROVED" ? (
                    <div className="flex items-center gap-1.5">
                      <Button variant="secondary" size="sm" onClick={() => onOpenScript && onOpenScript(proj)}>
                        Script
                      </Button>
                    </div>
                  ) : proj.current_stage === "STORY_ANALYZED" || proj.current_stage === "STORY_APPROVED" ? (
                    <div className="flex items-center gap-1.5">
                      <Button variant="secondary" size="sm" onClick={() => onOpenStory && onOpenStory(proj)}>
                        Story
                      </Button>
                    </div>
                  ) : proj.current_stage === "OCR_APPROVED" || proj.current_stage === "OCR_COMPLETE" ? (
                    <div className="flex items-center gap-1.5">
                      <Button variant="secondary" size="sm" onClick={() => (onOpenOCR ? onOpenOCR(proj) : onOpenPanels(proj))}>
                        OCR
                      </Button>
                    </div>
                  ) : proj.current_stage === "PANELS_DETECTED" ? (
                    <div className="flex items-center gap-1.5">
                      <Button variant="secondary" size="sm" onClick={() => onOpenPanels(proj)}>
                        Panels
                      </Button>
                    </div>
                  ) : proj.current_stage === "ACQUIRED" || proj.current_stage === "NORMALIZED" ? (
                    <div className="flex items-center gap-1.5">
                      <Button variant="secondary" size="sm" onClick={() => onOpenReview(proj)}>
                        Pages
                      </Button>
                    </div>
                  ) : (
                    <Button variant="primary" size="sm" onClick={() => onOpenAcquisition(proj)}>
                      Acquire
                    </Button>
                  )}
                </div>
              </div>
            </Card>
          ))}
        </div>
      )}
    </div>
  );
};
