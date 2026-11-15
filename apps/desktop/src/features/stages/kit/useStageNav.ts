import { useNavigate } from "react-router";
import { useQueryClient } from "@tanstack/react-query";
import type { Project } from "@panelflow/shared-types";
import { nextStage, paths, prevStage, type Stage } from "../../../app/routes";

/** Navigation for one stage screen: the callbacks every old screen took (`onBack`, `onApproved(updated)`, `onProceed`). */
export function useStageNav(project: Pick<Project, "id">, stage: Stage) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const goTo = (to: Stage) => navigate(paths.stage(project.id, to));
  const back = () => { const previous = prevStage(stage); navigate(previous ? paths.stage(project.id, previous) : paths.projects()); };
  const store = (updated: Project) => queryClient.setQueryData(["project", project.id], updated);
  /** Store the updated project, then move to the next stage. */
  const advance = (updated: Project) => { store(updated); const next = nextStage(stage); if (next) goTo(next); };
  return { goTo, back, store, advance };
}
