import type { Project } from "@panelflow/shared-types";

export type Stage = "acquire" | "pages" | "panels" | "ocr" | "story" | "script" | "audio" | "motion" | "render" | "publish";

export const STAGES: readonly Stage[] = ["acquire", "pages", "panels", "ocr", "story", "script", "audio", "motion", "render", "publish"];

export function isChronoFlowProject(project: Pick<Project, "source_type" | "settings">): boolean {
  return project.source_type === ("CHRONOFLOW_AI" as Project["source_type"]) || project.settings?.workflow_type === "chronoflow";
}

/**
 * Where a project opens: the screen the old App.tsx handleOpenProject chose for its pipeline stage.
 * NORMALIZED and PANELS_DETECTED skip the panels stage, exactly as the old code did; see docs/UI_V2_UNCOVERED.md.
 */
export function stageForProject(project: Pick<Project, "current_stage" | "settings">): Stage {
  switch (project.current_stage) {
    case "NEW":
    case "RIGHTS_APPROVED":
      return "acquire";
    case "ACQUIRED":
      return "pages";
    case "NORMALIZED":
    case "PANELS_DETECTED":
      return project.settings?.visual_storytelling ? "story" : "ocr";
    case "OCR_COMPLETE":
    case "OCR_APPROVED":
      return "story";
    case "STORY_ANALYZED":
    case "STORY_APPROVED":
      return "script";
    case "SCRIPT_GENERATED":
    case "SCRIPT_APPROVED":
      return "audio";
    case "VOICE_GENERATED":
    case "AUDIO_APPROVED":
    case "SHOT_PLAN_GENERATED":
      return "motion";
    default:
      return "render";
  }
}

export function nextStage(stage: Stage): Stage | null {
  return STAGES[STAGES.indexOf(stage) + 1] ?? null;
}

export function prevStage(stage: Stage): Stage | null {
  return STAGES[STAGES.indexOf(stage) - 1] ?? null;
}

export type CreateKind = "new" | "stories" | "anime" | "chronoflow" | "image";
export type SettingsSection = "engine" | "models" | "providers" | "youtube" | "diagnostics";

const id = encodeURIComponent;

export const paths = {
  home: () => "/home",
  projects: () => "/projects",
  project: (projectId: string) => `/projects/${id(projectId)}`,
  stage: (projectId: string, stage: Stage) => `/projects/${id(projectId)}/${stage}`,
  editor: (projectId: string) => `/editor/${id(projectId)}`,
  create: (kind?: CreateKind) => (kind ? `/create/${kind}` : "/create"),
  chronoflow: ({ projectId, jobId }: { projectId?: string; jobId?: string }) =>
    jobId ? `/create/chronoflow/job/${id(jobId)}` : projectId ? `/create/chronoflow/${id(projectId)}` : "/create/chronoflow",
  jobs: () => "/jobs",
  library: (kind?: "audio" | "media" | "voices" | "images") => (kind ? `/library/${kind}` : "/library"),
  settings: (section: SettingsSection = "engine") => `/settings/${section}`,
};
