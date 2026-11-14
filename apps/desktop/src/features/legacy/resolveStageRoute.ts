import type { Project } from "@panelflow/shared-types";
import { STAGES, isChronoFlowProject, paths, stageForProject, type Stage } from "../../app/routes";

export type StageDecision =
  | { kind: "loading" }
  | { kind: "not-found" }
  | { kind: "redirect"; to: string }
  | { kind: "render"; stage: Stage };

/** What `/projects/:id/:stage` should show for the project data loaded so far. */
export function resolveStageRoute(input: { id: string; stage: string; project: Project | undefined; failed: boolean }): StageDecision {
  const { id, stage, project, failed } = input;
  if (failed) return { kind: "not-found" };
  if (!project) return { kind: "loading" };
  if (isChronoFlowProject(project)) return { kind: "redirect", to: paths.chronoflow({ projectId: id }) };
  if (!(STAGES as readonly string[]).includes(stage)) return { kind: "redirect", to: paths.stage(id, stageForProject(project)) };
  return { kind: "render", stage: stage as Stage };
}
