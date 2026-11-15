import type { PipelineStage, Project } from "@panelflow/shared-types";

export type ProjectFilter = "all" | "needs-you" | "favorites";

const CHAPTER_RE = /^(.*?)\s*[-–:]\s*(?:chapter|ch\.?|episode|ep\.?)\s*(\d+(?:\.\d+)?)/i;

/** Titles look like "<Series> - Chapter N - ..."; two or more chapters of a series form a group, ordered by chapter. */
export function groupBySeries(projects: Project[]) {
  const bySeries = new Map<string, { project: Project; chapter: number }[]>();
  const singles: Project[] = [];
  const parsed = projects.map((project) => {
    const m = CHAPTER_RE.exec(project.title);
    return { project, series: m?.[1].trim() || "", chapter: m ? parseFloat(m[2]) : 0 };
  });
  for (const { project, series, chapter } of parsed) {
    if (!series) continue;
    const key = series.toLowerCase();
    bySeries.set(key, [...(bySeries.get(key) ?? []), { project, chapter }]);
  }
  const groups: { series: string; projects: Project[] }[] = [];
  for (const { project, series } of parsed) {
    const rows = series ? bySeries.get(series.toLowerCase()) : undefined;
    if (!rows || rows.length < 2) singles.push(project);
    else if (!groups.some((g) => g.series.toLowerCase() === series.toLowerCase()))
      groups.push({ series, projects: [...rows].sort((a, b) => a.chapter - b.chapter).map((r) => r.project) });
  }
  return { groups, singles };
}

export interface FilterOptions {
  query: string;
  filter: ProjectFilter;
  favorites: Record<string, boolean>;
  needsYou: ReadonlySet<string>;
}

export function filterProjects(projects: Project[], { query, filter, favorites, needsYou }: FilterOptions): Project[] {
  const needle = query.trim().toLowerCase();
  return projects
    .filter((project) => !needle || project.title.toLowerCase().includes(needle))
    .filter((project) => (filter === "favorites" ? favorites[project.id] : filter === "needs-you" ? needsYou.has(project.id) : true))
    .sort((a, b) => Date.parse(b.updated_at) - Date.parse(a.updated_at));
}

export function projectInitials(title: string): string {
  const words = title.trim().split(/\s+/).filter(Boolean);
  if (words.length === 0) return "?";
  return (words.length === 1 ? words[0].slice(0, 2) : words[0][0] + words[1][0]).toUpperCase();
}

const STAGE_LABEL: Record<PipelineStage, string> = {
  NEW: "Not started",
  RIGHTS_APPROVED: "Rights approved",
  ACQUIRED: "Pages imported",
  NORMALIZED: "Pages prepared",
  PANELS_DETECTED: "Panels ready for review",
  OCR_COMPLETE: "OCR ready for review",
  OCR_APPROVED: "OCR approved",
  STORY_ANALYZED: "Story ready for review",
  STORY_APPROVED: "Story approved",
  SCRIPT_GENERATED: "Script ready for review",
  SCRIPT_APPROVED: "Script approved",
  VOICE_GENERATED: "Audio ready for review",
  AUDIO_APPROVED: "Audio approved",
  SHOT_PLAN_GENERATED: "Motion ready for review",
  MOTION_APPROVED: "Motion approved",
  RENDERED: "Render ready for review",
  QA_APPROVED: "Ready to upload",
  EXPORTED: "Exported",
};

export function stageLabel(stage: PipelineStage): string {
  return STAGE_LABEL[stage] ?? stage;
}
