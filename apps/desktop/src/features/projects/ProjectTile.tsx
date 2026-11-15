import React from "react";
import { Star } from "lucide-react";
import { MoreHorizontal } from "lucide-react";
import type { Project } from "@panelflow/shared-types";
import { Chip, IconButton, Menu, Tile } from "@panelflow/ui-v2";
import { projectInitials, stageLabel } from "./projectsView";

export interface ProjectTileProps {
  project: Project;
  coverUrl?: string;
  favorite: boolean;
  needsYou: boolean;
  onOpen: () => void;
  onToggleFavorite: () => void;
  onOpenEditor: () => void;
  onOpenFolder: () => void;
  onDelete: () => void;
}

export const ProjectTile: React.FC<ProjectTileProps> = ({ project, coverUrl, favorite, needsYou, onOpen, onToggleFavorite, onOpenEditor, onOpenFolder, onDelete }) => {
  // A cover that 404s must not leave a broken-image icon: fall back to the initials tile.
  const [coverFailed, setCoverFailed] = React.useState(false);
  return (
    <div data-project-tile={project.title} className="relative">
      <Tile
        title={project.title}
        subtitle={stageLabel(project.current_stage)}
        fallbackText={projectInitials(project.title)}
        imageUrl={coverFailed ? undefined : coverUrl}
        onImageError={() => setCoverFailed(true)}
        onOpen={onOpen}
      />
      {needsYou && <Chip tone="warn" className="absolute left-3 top-3">Needs you</Chip>}
      <div className="absolute right-2 top-2 flex gap-1">
        <IconButton label={favorite ? "Remove from favorites" : "Add to favorites"} aria-pressed={favorite} onClick={onToggleFavorite}>
          <Star size={15} className={favorite ? "fill-warn text-warn" : undefined} />
        </IconButton>
        <Menu
          trigger={<IconButton label="More actions"><MoreHorizontal size={15} /></IconButton>}
          items={[
            { label: "Open story editor", onSelect: onOpenEditor },
            { label: "Open folder", onSelect: onOpenFolder },
            { label: "Delete project", onSelect: onDelete, danger: true },
          ]}
        />
      </div>
    </div>
  );
};
