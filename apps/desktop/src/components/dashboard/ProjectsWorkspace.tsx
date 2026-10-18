import React, { useState, useMemo } from "react";
import {
  Folder,
  Search,
  LayoutGrid,
  List,
  Plus,
} from "lucide-react";
import type { Project } from "@panelflow/shared-types";
import type { ProjectViewMode, ProjectFilterTab } from "./types";
import { DashboardProjectCard } from "./DashboardProjectCard";

interface ProjectsWorkspaceProps {
  projects: Project[];
  favorites: Record<string, boolean>;
  coversMap?: Record<string, string>;
  onToggleFavorite: (projectId: string) => void;
  onNewProject: () => void;
  onOpenStoryEditor: (project: Project) => void;
  onOpenOCR: (project: Project) => void;
  onOpenPanels: (project: Project) => void;
  onOpenFolder: (projectId: string) => void;
  onDeleteProject: (projectId: string) => void;
}

export const ProjectsWorkspace: React.FC<ProjectsWorkspaceProps> = ({
  projects,
  favorites,
  coversMap,
  onToggleFavorite,
  onNewProject,
  onOpenStoryEditor,
  onOpenOCR,
  onOpenPanels,
  onOpenFolder,
  onDeleteProject,
}) => {
  const [searchQuery, setSearchQuery] = useState("");
  const [viewMode, setViewMode] = useState<ProjectViewMode>("grid");
  const [activeFilter, setActiveFilter] = useState<ProjectFilterTab>("all");

  // Filtering logic
  const favoriteProjects = useMemo(() => {
    return projects.filter((p) => !!favorites[p.id]);
  }, [projects, favorites]);

  const recentlyUpdatedProjects = useMemo(() => {
    return [...projects].sort((a, b) => {
      const dateA = new Date(a.updated_at || a.created_at).getTime();
      const dateB = new Date(b.updated_at || b.created_at).getTime();
      return dateB - dateA;
    });
  }, [projects]);

  const filteredProjects = useMemo(() => {
    let list = projects;
    if (activeFilter === "favorites") {
      list = favoriteProjects;
    } else if (activeFilter === "recent") {
      list = recentlyUpdatedProjects;
    }

    if (!searchQuery.trim()) return list;

    const query = searchQuery.toLowerCase().trim();
    return list.filter((p) => {
      return (
        p.title.toLowerCase().includes(query) ||
        p.current_stage.toLowerCase().includes(query) ||
        (p.rights_status && p.rights_status.toLowerCase().includes(query))
      );
    });
  }, [projects, favoriteProjects, recentlyUpdatedProjects, activeFilter, searchQuery]);

  return (
    <div className="space-y-4 select-none">
      {/* Workspace Header Toolbar (Single Clean Row) */}
      <div className="flex items-center justify-between gap-3">
        {/* Left: Icon + Title + Subtitle */}
        <div className="flex items-center gap-2.5 min-w-0">
          <div className="w-8 h-8 sm:w-9 sm:h-9 rounded-xl bg-[#3b49df]/20 border border-[#3b49df]/40 flex items-center justify-center text-[#6366f1] shadow-inner flex-shrink-0">
            <Folder className="w-4 h-4 sm:w-5 sm:h-5" />
          </div>
          <div className="min-w-0">
            <h2 className="text-lg sm:text-xl font-bold text-white tracking-tight leading-none">Your Projects</h2>
            <p className="text-[11px] sm:text-xs text-zinc-400 mt-1 truncate">
              Manage your manga projects, process pages, and create motion comics.
            </p>
          </div>
        </div>

        {/* Right: Search, View Mode, New Project Button (Never Wraps) */}
        <div className="flex items-center gap-2 flex-shrink-0">
          {/* Search Box */}
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-zinc-500 absolute left-2.5 top-1/2 -translate-y-1/2 pointer-events-none" />
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search projects..."
              className="bg-[#111422] border border-[#1e2538] focus:border-indigo-500 rounded-lg pl-7 pr-2.5 py-1.5 text-xs text-zinc-200 placeholder-zinc-500 focus:outline-none w-28 sm:w-36 lg:w-44 transition-colors font-sans"
            />
          </div>

          {/* Grid / List View Toggle */}
          <div className="flex items-center bg-[#111422] border border-[#1e2538] rounded-lg p-0.5">
            <button
              onClick={() => setViewMode("grid")}
              className={`p-1.5 rounded transition-colors ${
                viewMode === "grid"
                  ? "bg-[#21283d] text-indigo-300 shadow-sm"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
              title="Grid view"
            >
              <LayoutGrid className="w-3.5 h-3.5" />
            </button>
            <button
              onClick={() => setViewMode("list")}
              className={`p-1.5 rounded transition-colors ${
                viewMode === "list"
                  ? "bg-[#21283d] text-indigo-300 shadow-sm"
                  : "text-zinc-500 hover:text-zinc-300"
              }`}
              title="List view"
            >
              <List className="w-3.5 h-3.5" />
            </button>
          </div>

          {/* New Project Button */}
          <button
            onClick={onNewProject}
            className="bg-[#4338ca] hover:bg-[#4f46e5] text-white text-xs font-semibold px-3 py-1.5 rounded-lg flex items-center gap-1.5 shadow-md shadow-indigo-600/30 transition-all flex-shrink-0"
          >
            <Plus className="w-4 h-4 text-white" />
            <span>New Project</span>
          </button>
        </div>
      </div>

      {/* Filter Tabs */}
      <div className="flex items-center gap-2 border-b border-[#181c2b] pb-2">
        <button
          onClick={() => setActiveFilter("all")}
          className={`px-3 py-1 rounded-lg text-xs font-medium transition-all ${
            activeFilter === "all"
              ? "bg-[#20253b] text-indigo-300 border border-[#2b3352]"
              : "text-zinc-400 hover:text-zinc-200 hover:bg-[#141826]"
          }`}
        >
          All Projects ({projects.length})
        </button>

        <button
          onClick={() => setActiveFilter("recent")}
          className={`px-3 py-1 rounded-lg text-xs font-medium transition-all ${
            activeFilter === "recent"
              ? "bg-[#20253b] text-indigo-300 border border-[#2b3352]"
              : "text-zinc-400 hover:text-zinc-200 hover:bg-[#141826]"
          }`}
        >
          Recently Updated ({recentlyUpdatedProjects.length})
        </button>

        <button
          onClick={() => setActiveFilter("favorites")}
          className={`px-3 py-1 rounded-lg text-xs font-medium transition-all ${
            activeFilter === "favorites"
              ? "bg-[#20253b] text-indigo-300 border border-[#2b3352]"
              : "text-zinc-400 hover:text-zinc-200 hover:bg-[#141826]"
          }`}
        >
          Favorites ({favoriteProjects.length})
        </button>
      </div>

      {/* Projects Grid / List */}
      {filteredProjects.length === 0 ? (
        <div className="bg-[#111422] border border-dashed border-[#1e2538] rounded-xl p-10 text-center space-y-3">
          <div className="w-12 h-12 rounded-2xl bg-[#14192a] border border-[#232b45] flex items-center justify-center text-zinc-400 mx-auto">
            <Folder className="w-6 h-6" />
          </div>
          <h3 className="text-sm font-semibold text-zinc-200">
            {searchQuery ? "No matching projects found" : "No projects in this category"}
          </h3>
          <p className="text-xs text-zinc-500 max-w-sm mx-auto">
            {searchQuery
              ? `No projects matched "${searchQuery}". Try a different keyword.`
              : "Create your first project from a local image folder, ZIP archive, or web source."}
          </p>
          {!searchQuery && (
            <button
              onClick={onNewProject}
              className="mt-2 bg-[#4338ca] hover:bg-[#4f46e5] text-white text-xs font-semibold px-4 py-2 rounded-lg inline-flex items-center gap-1.5 shadow-md shadow-indigo-600/30 transition-all"
            >
              <Plus className="w-4 h-4" />
              Create Project
            </button>
          )}
        </div>
      ) : (
        <div
          className={
            viewMode === "grid"
              ? "grid grid-cols-1 xl:grid-cols-2 gap-3.5 sm:gap-4"
              : "flex flex-col space-y-2.5"
          }
        >
          {filteredProjects.map((proj) => (
            <DashboardProjectCard
              key={proj.id}
              project={proj}
              coverUrl={coversMap?.[proj.id]}
              isFavorite={!!favorites[proj.id]}
              onToggleFavorite={onToggleFavorite}
              onOpenStoryEditor={onOpenStoryEditor}
              onOpenOCR={onOpenOCR}
              onOpenPanels={onOpenPanels}
              onOpenFolder={onOpenFolder}
              onDeleteProject={onDeleteProject}
              viewMode={viewMode}
            />
          ))}
        </div>
      )}
    </div>
  );
};
