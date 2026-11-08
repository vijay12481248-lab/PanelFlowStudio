import React from "react";
import type { Project } from "@panelflow/shared-types";
import { Button, Chip } from "@panelflow/ui-v2";
import { stageLabel } from "../projects/projectsView";

export interface ProjectHeroProps {
  project: Project;
  coverUrl?: string;
  /** Why this project is in focus, from the inbox; falls back to the page count. */
  note?: string;
  onContinue: () => void;
}

export const ProjectHero: React.FC<ProjectHeroProps> = ({ project, coverUrl, note, onContinue }) => {
  const [coverFailed, setCoverFailed] = React.useState(false);
  return (
    <div data-hero className="relative min-h-64 overflow-hidden rounded-card border border-edge bg-flat">
      {coverUrl && !coverFailed && (
        <img src={coverUrl} alt="" onError={() => setCoverFailed(true)} className="absolute inset-y-0 right-0 h-full w-3/5 object-cover" />
      )}
      <div className="absolute inset-0 bg-gradient-to-r from-flat via-flat/90 to-transparent" />
      <div className="relative grid max-w-[62%] gap-3 p-6 grid-cols-1">
        <Chip tone="accent" className="w-fit">{stageLabel(project.current_stage)}</Chip>
        <h2 className="font-display text-3xl font-bold leading-tight tracking-tight text-fg">{project.title}</h2>
        <p className="text-sm text-fg-dim">{note ?? `${project.ready_pages} of ${project.total_pages} pages ready`}</p>
        <div><Button variant="primary" onClick={onContinue}>Continue</Button></div>
      </div>
    </div>
  );
};
