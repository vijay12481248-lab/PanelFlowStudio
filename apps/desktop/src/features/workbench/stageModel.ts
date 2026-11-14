import type { PipelineStage, Project } from "@panelflow/shared-types";
import type { Step } from "@panelflow/ui-v2";
import { STAGES, paths, type Stage } from "../../app/routes";

export const STAGE_LABEL: Record<Stage, string> = {
  acquire: "Source", pages: "Pages", panels: "Panels", ocr: "OCR", story: "Story", script: "Script",
  audio: "Audio", motion: "Motion", render: "Render", publish: "Publish",
};

const ORDER: PipelineStage[] = [
  "NEW", "RIGHTS_APPROVED", "ACQUIRED", "NORMALIZED", "PANELS_DETECTED", "OCR_COMPLETE", "OCR_APPROVED", "STORY_ANALYZED", "STORY_APPROVED",
  "SCRIPT_GENERATED", "SCRIPT_APPROVED", "VOICE_GENERATED", "AUDIO_APPROVED", "SHOT_PLAN_GENERATED", "MOTION_APPROVED", "RENDERED", "QA_APPROVED", "EXPORTED",
];

/** The pipeline stages during which each workbench stage is the one in progress (inclusive). */
const RANGE: Record<Stage, [PipelineStage, PipelineStage]> = {
  acquire: ["NEW", "RIGHTS_APPROVED"],
  pages: ["ACQUIRED", "ACQUIRED"],
  panels: ["NORMALIZED", "PANELS_DETECTED"],
  ocr: ["OCR_COMPLETE", "OCR_APPROVED"],
  story: ["STORY_ANALYZED", "STORY_APPROVED"],
  script: ["SCRIPT_GENERATED", "SCRIPT_APPROVED"],
  audio: ["VOICE_GENERATED", "AUDIO_APPROVED"],
  motion: ["SHOT_PLAN_GENERATED", "MOTION_APPROVED"],
  render: ["RENDERED", "RENDERED"],
  publish: ["QA_APPROVED", "QA_APPROVED"],
};

type StepStatus = Step["status"];
type ProjectState = Pick<Project, "id" | "current_stage" | "rights_status" | "stale_stages">;

/**
 * Where a project stands in each stage. Precedence: stale (a stage that must be redone), then blocked
 * (unknown rights hold Render and Publish), then in progress, then done, else not started.
 */
export function stageSteps(project: ProjectState): Step[] {
  const at = ORDER.indexOf(project.current_stage);
  const stale = new Set(project.stale_stages ?? []);

  const statusOf = (stage: Stage): StepStatus => {
    const [from, to] = RANGE[stage];
    const past = at > ORDER.indexOf(to);
    const within = at >= ORDER.indexOf(from) && at <= ORDER.indexOf(to);
    if (stale.has(stage)) return "stale";
    if (project.rights_status === ("UNKNOWN" as Project["rights_status"]) && (stage === "render" || stage === "publish") && !past) return "blocked";
    if (within) return "active";
    return past ? "done" : "upcoming";
  };

  const statuses = STAGES.map(statusOf);
  // The next stage is reachable even though it has not started; steps further on are not.
  const reach = statuses.reduce((last, status, i) => (status === "done" || status === "active" || status === "stale" ? i : last), -1);

  return STAGES.map((stage, i) => ({
    id: stage,
    label: STAGE_LABEL[stage],
    status: statuses[i],
    ...(statuses[i] !== "upcoming" || i === reach + 1 ? { href: paths.stage(project.id, stage) } : {}),
  }));
}
