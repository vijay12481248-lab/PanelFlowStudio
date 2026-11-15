import React from "react";
import { Link } from "react-router";
import { Film, Zap } from "lucide-react";
import type { Project } from "@panelflow/shared-types";
import { Button, Chip, GlassPanel, PageHeader, Stepper } from "@panelflow/ui-v2";
import { paths, type Stage } from "../../app/routes";
import { stageLabel } from "../projects/projectsView";
import { rightsLabel } from "./rightsLabel";
import { stageSteps } from "./stageModel";

export interface WorkbenchFrameProps {
  project: Project;
  /** The stage whose screen is open. */
  stage: Stage;
  onAutoPilot: () => void;
  children: React.ReactNode;
}

const LINK_BUTTON = "inline-flex h-8 items-center gap-2 rounded-full border border-edge bg-glass-hi px-3 text-[13px] font-semibold text-fg transition-colors hover:bg-glass focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-info";

/** The one frame every pipeline stage sits in: project header, real pipeline stepper, then the stage itself. */
export const WorkbenchFrame: React.FC<WorkbenchFrameProps> = ({ project, stage, onAutoPilot, children }) => {
  const steps = stageSteps(project).map((step) => ({ ...step, viewed: step.id === stage }));
  const rights = rightsLabel(project.rights_status);
  const stale = (project.stale_stages ?? []).length > 0;
  return (
    <div className="mx-auto grid w-full max-w-7xl grid-cols-1 gap-5 p-6 md:p-8">
      <div className="grid grid-cols-1 gap-3">
        <Link to={paths.projects()} className="w-fit text-xs text-fg-dim underline-offset-2 hover:text-fg hover:underline">Projects</Link>
        <PageHeader
          title={project.title}
          meta={
            <>
              <Chip tone="accent">{stageLabel(project.current_stage)}</Chip>
              <Chip tone={rights.tone === "warn" ? "warn" : rights.tone === "ok" ? "ok" : "neutral"}>{rights.word}</Chip>
              {stale && <Chip tone="warn">Needs a rerun</Chip>}
            </>
          }
          actions={
            <>
              <Button variant="secondary" size="sm" icon={<Zap size={14} />} onClick={onAutoPilot}>Auto-Pilot</Button>
              <Link to={paths.editor(project.id)} className={LINK_BUTTON}><Film size={14} aria-hidden="true" />Open story editor</Link>
            </>
          }
        />
      </div>
      <GlassPanel blur={false} className="p-2.5">
        <Stepper steps={steps} renderLink={(step, children) => <Link to={step.href!}>{children}</Link>} />
      </GlassPanel>
      <div data-stage-body>{children}</div>
    </div>
  );
};
