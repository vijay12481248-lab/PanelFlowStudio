import React from "react";
import type { Project } from "@panelflow/shared-types";
import { ErrorState, Skeleton } from "@panelflow/ui-v2";
import { LatestRender } from "./LatestRender";
import { PackagingPanel } from "./PackagingPanel";
import { PublishChecks } from "./PublishChecks";
import { useRenders, useRenderValidation } from "./queries";
import { canHandOff, latestRender, publishChecks } from "./publishModel";

export interface PublishStageProps {
  project: Project;
  /** Injected in tests. */
  copy?: (text: string) => Promise<void>;
}

/**
 * Publish: check the finished video and hand over everything needed to upload it by hand.
 * It never uploads, publishes or schedules, and it never asks for packaging until a button is pressed.
 */
export const PublishStage: React.FC<PublishStageProps> = ({ project, copy = (text) => navigator.clipboard.writeText(text) }) => {
  const renders = useRenders(project.id);
  const finished = latestRender(renders.data ?? []);
  const needsReport = Boolean(finished) && !finished?.validation_report;
  const fetched = useRenderValidation(project.id, finished?.render_id, needsReport);

  const report = finished?.validation_report ?? fetched.data ?? undefined;
  const checks = publishChecks({ project, renders: renders.data ?? [], validation: report });

  if (renders.isError) {
    return <ErrorState title="Couldn't load the renders" description="Check that the engine is running, then try again." onRetry={() => void renders.refetch()} />;
  }
  if (!renders.data) return <div className="grid grid-cols-1 gap-4"><Skeleton className="h-48" /><Skeleton className="h-64" /></div>;

  return (
    <div className="grid grid-cols-1 gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <div className="grid min-w-0 grid-cols-1 content-start gap-5">
        <PublishChecks checks={checks} />
        <LatestRender projectId={project.id} render={finished} report={report} />
      </div>
      <div className="min-w-0">
        <PackagingPanel projectId={project.id} canCopy={canHandOff(checks)} copy={copy} />
      </div>
    </div>
  );
};
