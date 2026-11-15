import type { Job, PipelineStage, Project } from "@panelflow/shared-types";
import type { OriginalSeries } from "@panelflow/api-client";
import type { InboxKind } from "@panelflow/ui-v2";
import { isChronoFlowProject, paths, type Stage } from "../../app/routes";
import { firstErrorLine, jobLabel } from "../jobs/jobsView";

export type InboxAction = { type: "open"; to: string } | { type: "retry-job"; jobId: string };

export interface InboxItem {
  id: string;
  kind: InboxKind;
  title: string;
  subtitle: string;
  actionLabel: string;
  action: InboxAction;
  projectId?: string;
  /** ISO time used to order items of the same kind, newest first. */
  at: string;
}

const WEEK_MS = 7 * 86_400_000;
const RANK: Record<InboxKind, number> = { failed: 0, blocked: 1, review: 2, publish: 3 };

const REVIEW: Partial<Record<PipelineStage, [Stage, string]>> = {
  ACQUIRED: ["pages", "pages"],
  PANELS_DETECTED: ["panels", "panels"],
  OCR_COMPLETE: ["ocr", "OCR"],
  STORY_ANALYZED: ["story", "story"],
  SCRIPT_GENERATED: ["script", "script"],
  VOICE_GENERATED: ["audio", "audio"],
  SHOT_PLAN_GENERATED: ["motion", "motion"],
  RENDERED: ["render", "render"],
};

/** The screen where a stage that is waiting for approval is approved, or null when nothing waits. */
export function reviewStageFor(stage: PipelineStage): Stage | null {
  return REVIEW[stage]?.[0] ?? null;
}

const open = (to: string): InboxAction => ({ type: "open", to });
const time = (iso: string | null | undefined) => (iso ? Date.parse(iso) : 0);

/** The newest job of each type per project, when it failed recently and nothing newer replaced it. */
function failedItem(project: Project, jobs: Job[], now: number): InboxItem | undefined {
  const newestByType = new Map<string, Job>();
  for (const job of jobs) {
    if (job.project_id !== project.id) continue;
    const current = newestByType.get(job.job_type);
    if (!current || time(job.created_at) > time(current.created_at)) newestByType.set(job.job_type, job);
  }
  const failed = [...newestByType.values()]
    .filter((job) => job.status === "FAILED" && now - time(job.finished_at ?? job.created_at) <= WEEK_MS)
    .sort((a, b) => time(b.finished_at ?? b.created_at) - time(a.finished_at ?? a.created_at))[0];
  if (!failed) return undefined;
  return {
    id: `failed-${failed.job_id}`,
    kind: "failed",
    title: `${jobLabel(failed.job_type)} failed, ${project.title}`,
    subtitle: firstErrorLine(failed).slice(0, 90),
    actionLabel: "Retry",
    action: { type: "retry-job", jobId: failed.job_id },
    projectId: project.id,
    at: failed.finished_at ?? failed.created_at ?? project.updated_at,
  };
}

/** One item per project: failed job, then rights decision, then a review, then ready to upload. */
function projectItem(project: Project, jobs: Job[], now: number): InboxItem | undefined {
  if (isChronoFlowProject(project)) return undefined;
  const failed = failedItem(project, jobs, now);
  if (failed) return failed;
  if (project.rights_status === "UNKNOWN") {
    return {
      id: `rights-${project.id}`, kind: "blocked", title: `Rights decision, ${project.title}`,
      subtitle: "Source rights are unknown, so rendering is held", actionLabel: "Decide",
      action: open(paths.stage(project.id, "acquire")), projectId: project.id, at: project.updated_at,
    };
  }
  const review = REVIEW[project.current_stage];
  if (review) {
    return {
      id: `review-${project.id}`, kind: "review", title: `Review ${review[1]}, ${project.title}`,
      subtitle: "Waiting for your approval", actionLabel: "Review",
      action: open(paths.stage(project.id, review[0])), projectId: project.id, at: project.updated_at,
    };
  }
  if (project.current_stage === "QA_APPROVED") {
    return {
      id: `publish-${project.id}`, kind: "publish", title: `Package and upload, ${project.title}`,
      subtitle: "Rendered and approved", actionLabel: "Open",
      action: open(paths.stage(project.id, "publish")), projectId: project.id, at: project.updated_at,
    };
  }
  return undefined;
}

function episodeItems(series: OriginalSeries[]): InboxItem[] {
  return series.flatMap((s) =>
    s.episodes.flatMap((episode): InboxItem[] => {
      if (episode.status !== "done" || episode.youtube_url) return [];
      const base = { id: `episode-${s.id}-${episode.number}`, actionLabel: "Open", action: open(paths.create("stories")), at: episode.publish_at ?? "1970-01-01T00:00:00Z" };
      if (episode.upload_status === "failed") {
        return [{ ...base, kind: "failed", title: `Upload failed, episode ${episode.number}, ${s.name}`, subtitle: episode.upload_error || "The upload did not finish" }];
      }
      if (episode.upload_status === "") {
        return [{ ...base, kind: "publish", title: `Upload episode ${episode.number}, ${s.name}`, subtitle: "Rendered, not on YouTube yet" }];
      }
      return [];
    }),
  );
}

export function buildInbox(input: { projects: Project[]; jobs: Job[]; series: OriginalSeries[]; now?: number }): InboxItem[] {
  const now = input.now ?? Date.now();
  const items = [
    ...input.projects.map((project) => projectItem(project, input.jobs, now)).filter((item): item is InboxItem => Boolean(item)),
    ...episodeItems(input.series),
  ];
  return items.sort((a, b) => RANK[a.kind] - RANK[b.kind] || time(b.at) - time(a.at));
}

export function pickFocusProject(projects: Project[], items: InboxItem[]): Project | undefined {
  const focusId = items.find((item) => item.projectId)?.projectId;
  const named = focusId ? projects.find((project) => project.id === focusId) : undefined;
  return named ?? [...projects].sort((a, b) => time(b.updated_at) - time(a.updated_at))[0];
}
