import React, { useState } from "react";
import {
  Star,
  MoreHorizontal,
  Folder,
  Trash2,
  Film,
  FileText,
  LayoutGrid,
  Calendar,
  Layers,
  Sparkles,
} from "lucide-react";
import type { Project } from "@panelflow/shared-types";
import type { ProjectViewMode } from "./types";

interface DashboardProjectCardProps {
  project: Project;
  isFavorite: boolean;
  coverUrl?: string;
  onToggleFavorite: (projectId: string) => void;
  onOpenStoryEditor: (project: Project) => void;
  onOpenProject?: (project: Project) => void;
  onOpenOCR: (project: Project) => void;
  onOpenPanels: (project: Project) => void;
  onOpenFolder: (projectId: string) => void;
  onDeleteProject: (projectId: string) => void;
  viewMode?: ProjectViewMode;
}

export const DashboardProjectCard: React.FC<DashboardProjectCardProps> = ({
  project,
  isFavorite,
  coverUrl,
  onToggleFavorite,
  onOpenStoryEditor,
  onOpenProject,
  onOpenOCR,
  onOpenPanels,
  onOpenFolder,
  onDeleteProject,
  viewMode = "grid",
}) => {
  const [showMenu, setShowMenu] = useState(false);
  const [imgError, setImgError] = useState(false);

  const handleOpen = () => {
    if (onOpenProject) {
      onOpenProject(project);
    } else {
      onOpenStoryEditor(project);
    }
  };

  // Formatted date
  const formattedDate = (() => {
    try {
      const d = new Date(project.updated_at || project.created_at);
      return `${d.toLocaleDateString("en-GB")} ${d.toLocaleTimeString([], {
        hour: "2-digit",
        minute: "2-digit",
      })}`;
    } catch {
      return "Recently";
    }
  })();

  // Contextual description fallback
  const description =
    (project as any).description ||
    (project.title.toLowerCase().includes("demon") || project.title.toLowerCase().includes("emperor")
      ? "A young emperor rises with forbidden magic, challenging the heavens."
      : project.title.toLowerCase().includes("tales")
      ? "A journey through a world of demons and ancient power."
      : project.title.toLowerCase().includes("shadow") || project.title.toLowerCase().includes("blade")
      ? "A lone swordsman in a world of shadows and betrayal."
      : project.title.toLowerCase().includes("heavenly")
      ? "A cultivator's journey to the heavens, filled with trials and friendships."
      : project.title.toLowerCase().includes("urban")
      ? "Modern urban legends come to life in a connected world."
      : "High-octane graphic storytelling brought to life with neural motion and sound.");

  // Clean formatted stage badge
  const renderStageBadge = () => {
    const stage = project.current_stage;
    if (stage === "OCR_COMPLETE" || stage === "OCR_APPROVED") {
      return (
        <span className="bg-[#092e22] text-[#34d399] border border-[#14532d] text-[10px] px-2 py-0.5 rounded font-bold uppercase tracking-wider flex-shrink-0">
          OCR_COMPLETE
        </span>
      );
    }
    if (stage === "PANELS_DETECTED" || stage === "NORMALIZED") {
      return (
        <span className="bg-[#092e22] text-[#34d399] border border-[#14532d] text-[10px] px-2 py-0.5 rounded font-bold uppercase tracking-wider flex-shrink-0">
          PANELS_DETECTED
        </span>
      );
    }
    if (stage === "RENDERED" || stage === "QA_APPROVED" || stage === "EXPORTED") {
      return (
        <span className="bg-[#092e22] text-[#34d399] border border-[#14532d] text-[10px] px-2 py-0.5 rounded font-bold uppercase tracking-wider flex-shrink-0">
          COMPLETED
        </span>
      );
    }
    if (stage === "NEW" || stage === "RIGHTS_APPROVED") {
      return (
        <span className="bg-[#3f2a14] text-[#f59e0b] border border-[#784c19] text-[10px] px-2 py-0.5 rounded font-bold uppercase tracking-wider flex-shrink-0">
          QUEUED
        </span>
      );
    }
    return (
      <span className="bg-[#172033] text-indigo-300 border border-[#243352] text-[10px] px-2 py-0.5 rounded font-bold uppercase tracking-wider flex-shrink-0">
        {stage}
      </span>
    );
  };

  // Source / Rights badge
  const renderSourceBadge = () => {
    const status = (project.rights_status || "") as string;
    if (status === "PUBLIC_DOMAIN") {
      return (
        <span className="bg-[#121d33] text-[#60a5fa] border border-[#1e3a6a] text-[10px] px-2 py-0.5 rounded font-bold uppercase tracking-wider flex-shrink-0">
          PUBLIC_DOMAIN
        </span>
      );
    }
    if (status === "AUTHORIZED_WEB" || status === "COMMERCIAL_LICENSE" || status === "LICENSED") {
      return (
        <span className="bg-[#162133] text-[#38bdf8] border border-[#1b3b5f] text-[10px] px-2 py-0.5 rounded font-bold uppercase tracking-wider flex-shrink-0">
          AUTHORIZED_WEB
        </span>
      );
    }
    const source = (project.source_type || "LOCAL_SOURCE").replace(/_/g, " ");
    return (
      <span className="bg-[#181d2a] text-zinc-300 border border-[#242b3d] text-[10px] px-2 py-0.5 rounded font-bold uppercase tracking-wider flex-shrink-0">
        {source}
      </span>
    );
  };

  // Thumbnail rendering (Actual Manga Artwork or Stylized Avatar)
  const renderCover = (dimensions = "w-20 h-24 sm:w-24 sm:h-28") => {
    const title = project.title;
    const hash = title.split("").reduce((acc, c) => acc + c.charCodeAt(0), 0);
    const hues = ["#6366f1", "#8b5cf6", "#3b82f6", "#06b6d4", "#ec4899", "#10b981"];
    const accentColor = hues[hash % hues.length];
    const initials = title
      .split(/[-_ ]+/)
      .map((w) => w[0]?.toUpperCase())
      .slice(0, 2)
      .join("") || "PF";

    const hasRealCover = coverUrl && !imgError;

    return (
      <div
        onClick={handleOpen}
        className={`${dimensions} rounded-lg bg-[#0e1220] border border-[#232b45] flex items-center justify-center flex-shrink-0 relative overflow-hidden group-hover:border-indigo-500/60 shadow-md cursor-pointer transition-all`}
      >
        {hasRealCover ? (
          <img
            src={coverUrl}
            alt={project.title}
            onError={() => setImgError(true)}
            className="w-full h-full object-cover object-top transition-transform duration-500 group-hover:scale-105"
          />
        ) : (
          <>
            <div
              className="absolute inset-0 opacity-30"
              style={{
                background: `radial-gradient(circle at 35% 35%, ${accentColor}, transparent 70%)`,
              }}
            />
            <div className="absolute inset-0 flex items-center justify-center opacity-30">
              <svg className="w-10 h-10 text-zinc-400" viewBox="0 0 24 24" fill="currentColor">
                <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm0 3c1.66 0 3 1.34 3 3s-1.34 3-3 3-3-1.34-3-3 1.34-3 3-3zm0 14.2c-2.5 0-4.71-1.28-6-3.22.03-1.99 4-3.08 6-3.08 1.99 0 5.97 1.09 6 3.08-1.29 1.94-3.5 3.22-6 3.22z" />
              </svg>
            </div>
            <span className="font-black text-sm text-zinc-200 font-mono tracking-widest relative z-10 drop-shadow">
              {initials}
            </span>
          </>
        )}
      </div>
    );
  };

  // 1. LIST VIEW RENDERING
  if (viewMode === "list") {
    return (
      <div className="bg-[#111422] border border-[#1e2538] hover:border-zinc-700/80 rounded-xl p-3 flex items-center justify-between gap-3 transition-all group shadow-sm select-none">
        <div className="flex items-center gap-3 min-w-0">
          {renderCover("w-12 h-14")}
          <div className="min-w-0">
            <div className="flex items-center gap-2">
              <h3
                onClick={handleOpen}
                className="font-bold text-sm text-white group-hover:text-indigo-400 transition-colors truncate cursor-pointer tracking-tight"
                title={project.title}
              >
                {project.title}
              </h3>
              {renderStageBadge()}
              {renderSourceBadge()}
            </div>
            <div className="flex items-center gap-4 mt-1 text-[11px] text-zinc-400">
              <span>{project.total_pages || 7} pages</span>
              <span>Updated {formattedDate}</span>
            </div>
          </div>
        </div>

        {/* List Action Buttons */}
        <div className="flex items-center gap-1.5 flex-shrink-0">
          <button
            onClick={() => onToggleFavorite(project.id)}
            className={`p-1.5 rounded hover:bg-[#1a2035] transition-colors ${
              isFavorite ? "text-amber-400" : "text-zinc-500 hover:text-amber-400"
            }`}
            title={isFavorite ? "Remove from favorites" : "Add to favorites"}
          >
            <Star className={`w-3.5 h-3.5 ${isFavorite ? "fill-amber-400" : ""}`} />
          </button>

          <button
            onClick={() => onOpenStoryEditor(project)}
            className="bg-[#3b49df] hover:bg-[#4338ca] text-white text-[11px] font-semibold px-2.5 py-1.5 rounded-lg flex items-center gap-1 shadow-sm shadow-indigo-600/30 transition-all"
            title="Open Video-First Story Editor"
          >
            <Film className="w-3.5 h-3.5 text-white" />
            <span>Story Editor</span>
          </button>

          <button
            onClick={() => onOpenOCR(project)}
            className="bg-[#151928] hover:bg-[#1f253d] text-zinc-200 border border-[#262f4c] text-[11px] font-medium px-2 py-1.5 rounded-lg flex items-center gap-1 transition-all"
            title="Review OCR and Dialogue"
          >
            <FileText className="w-3 h-3 text-zinc-400" />
            <span>OCR</span>
          </button>

          <button
            onClick={() => onOpenPanels(project)}
            className="bg-[#151928] hover:bg-[#1f253d] text-zinc-200 border border-[#262f4c] text-[11px] font-medium px-2 py-1.5 rounded-lg flex items-center gap-1 transition-all"
            title="Review Panels"
          >
            <LayoutGrid className="w-3 h-3 text-zinc-400" />
            <span>Panels</span>
          </button>

          <button
            onClick={() => onOpenFolder(project.id)}
            className="bg-[#151928] hover:bg-[#1f253d] text-zinc-200 border border-[#262f4c] text-[11px] font-medium px-2 py-1.5 rounded-lg flex items-center gap-1 transition-all"
            title="Open workspace in File Explorer"
          >
            <Folder className="w-3 h-3 text-zinc-400" />
            <span>Files</span>
          </button>

          <button
            onClick={() => onDeleteProject(project.id)}
            className="p-1.5 rounded text-zinc-500 hover:text-rose-400 hover:bg-rose-950/30 transition-colors"
            title="Delete project"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>
    );
  }

  // 2. GRID VIEW RENDERING
  return (
    <div className="bg-[#111422] border border-[#1e2538] hover:border-zinc-700/80 rounded-xl p-3 sm:p-3.5 flex flex-col justify-between transition-all group shadow-sm select-none">
      {/* Top Part: Cover + Metadata */}
      <div>
        <div className="flex items-start gap-3">
          {renderCover()}

          <div className="flex-1 min-w-0">
            {/* Title Row + Star + Menu */}
            <div className="flex items-start justify-between gap-1">
              <h3
                onClick={handleOpen}
                className="font-bold text-xs sm:text-sm text-white group-hover:text-indigo-400 transition-colors line-clamp-1 cursor-pointer tracking-tight"
                title={project.title}
              >
                {project.title}
              </h3>

              <div className="flex items-center gap-1 flex-shrink-0 relative">
                <button
                  type="button"
                  onClick={() => onToggleFavorite(project.id)}
                  className={`p-1 rounded hover:bg-[#1a2035] transition-colors ${
                    isFavorite ? "text-amber-400" : "text-zinc-500 hover:text-amber-400"
                  }`}
                  title={isFavorite ? "Remove from favorites" : "Add to favorites"}
                >
                  <Star className={`w-3.5 h-3.5 ${isFavorite ? "fill-amber-400" : ""}`} />
                </button>

                <button
                  type="button"
                  onClick={() => setShowMenu(!showMenu)}
                  className="p-1 rounded text-zinc-500 hover:text-zinc-200 hover:bg-[#1a2035] transition-colors"
                  title="More actions"
                >
                  <MoreHorizontal className="w-3.5 h-3.5" />
                </button>

                {/* Dropdown Menu */}
                {showMenu && (
                  <>
                    <div
                      className="fixed inset-0 z-20"
                      onClick={() => setShowMenu(false)}
                    />
                    <div className="absolute right-0 top-7 w-36 bg-[#151928] border border-[#262f4c] rounded-lg shadow-xl z-30 py-1 text-xs">
                      <button
                        onClick={() => {
                          setShowMenu(false);
                          onOpenStoryEditor(project);
                        }}
                        className="w-full px-3 py-1.5 text-left text-zinc-300 hover:bg-[#1f253d] flex items-center gap-2"
                      >
                        <Film className="w-3.5 h-3.5 text-indigo-400" />
                        Story Editor
                      </button>
                      <button
                        onClick={() => {
                          setShowMenu(false);
                          onOpenFolder(project.id);
                        }}
                        className="w-full px-3 py-1.5 text-left text-zinc-300 hover:bg-[#1f253d] flex items-center gap-2"
                      >
                        <Folder className="w-3.5 h-3.5" />
                        Browse Files
                      </button>
                      <button
                        onClick={() => {
                          setShowMenu(false);
                          onDeleteProject(project.id);
                        }}
                        className="w-full px-3 py-1.5 text-left text-rose-400 hover:bg-rose-950/40 flex items-center gap-2"
                      >
                        <Trash2 className="w-3.5 h-3.5" />
                        Delete Project
                      </button>
                    </div>
                  </>
                )}
              </div>
            </div>

            {/* Badges Row */}
            <div className="flex flex-wrap items-center gap-1.5 mt-1.5">
              {renderStageBadge()}
              {renderSourceBadge()}
            </div>

            {/* Description */}
            <p className="text-[11px] text-zinc-400 line-clamp-2 mt-1.5 leading-relaxed">
              {description}
            </p>

            {/* Page Count & Updated Date */}
            <div className="flex items-center gap-3.5 mt-2 text-[10.5px] text-zinc-400">
              <div className="flex items-center gap-1 flex-shrink-0">
                <FileText className="w-3 h-3 text-zinc-500" />
                <span>{project.total_pages || 7} pages</span>
              </div>
              <div className="flex items-center gap-1 min-w-0">
                <Calendar className="w-3 h-3 text-zinc-500 flex-shrink-0" />
                <span className="truncate">Updated {formattedDate}</span>
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* Bottom Row: 4 Action Buttons (Story Editor, OCR, Panels, Files) */}
      <div className="pt-2.5 mt-2.5 border-t border-[#181c2b] flex items-center justify-between gap-1 flex-nowrap">
        <button
          onClick={() => onOpenStoryEditor(project)}
          className="bg-[#3b49df] hover:bg-[#4338ca] text-white text-[11px] font-semibold px-2.5 py-1.5 rounded-lg flex items-center gap-1 shadow-sm shadow-indigo-600/30 transition-all flex-shrink-0"
          title="Open Video-First Story Editor"
        >
          <Film className="w-3.5 h-3.5 text-white flex-shrink-0" />
          <span>Story Editor</span>
        </button>

        <div className="flex items-center gap-1 flex-shrink-0">
          <button
            onClick={() => onOpenOCR(project)}
            className="bg-[#151928] hover:bg-[#1f253d] text-zinc-200 border border-[#262f4c] text-[11px] font-medium px-2 py-1.5 rounded-lg flex items-center gap-1 transition-all flex-shrink-0"
            title="Review OCR and Dialogue"
          >
            <FileText className="w-3 h-3 text-zinc-400 flex-shrink-0" />
            <span>OCR</span>
          </button>

          <button
            onClick={() => onOpenPanels(project)}
            className="bg-[#151928] hover:bg-[#1f253d] text-zinc-200 border border-[#262f4c] text-[11px] font-medium px-2 py-1.5 rounded-lg flex items-center gap-1 transition-all flex-shrink-0"
            title="Review Panels"
          >
            <LayoutGrid className="w-3 h-3 text-zinc-400 flex-shrink-0" />
            <span>Panels</span>
          </button>

          <button
            onClick={() => onOpenFolder(project.id)}
            className="bg-[#151928] hover:bg-[#1f253d] text-zinc-200 border border-[#262f4c] text-[11px] font-medium px-2 py-1.5 rounded-lg flex items-center gap-1 transition-all flex-shrink-0"
            title="Open workspace in File Explorer"
          >
            <Folder className="w-3 h-3 text-zinc-400 flex-shrink-0" />
            <span>Files</span>
          </button>
        </div>
      </div>
    </div>
  );
};
