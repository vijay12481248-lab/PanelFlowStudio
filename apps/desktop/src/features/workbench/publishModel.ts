import type { Project, RenderJob, RenderValidationReport, YouTubeChapter, YouTubePackagingData } from "@panelflow/shared-types";

export type CheckState = "pass" | "fail" | "pending";

export interface PublishCheck {
  id: "rights" | "approved" | "render" | "fresh" | "valid";
  label: string;
  state: CheckState;
  detail: string;
}

const RUNNING = new Set(["QUEUED", "PREPARING", "COMPOSING", "ENCODING", "MUXING", "VALIDATING"]);
const time = (iso: string | undefined) => (iso ? Date.parse(iso) : 0);
const newestFirst = (a: RenderJob, b: RenderJob) => time(b.created_at) - time(a.created_at);

/** The newest finished render: the one to preview and to check. */
export function latestRender(renders: RenderJob[]): RenderJob | undefined {
  return [...renders].filter((r) => r.status === "COMPLETE").sort(newestFirst)[0];
}

type PublishProject = Pick<Project, "current_stage" | "rights_status" | "stale_stages">;

export function publishChecks(input: { project: PublishProject; renders: RenderJob[]; validation?: RenderValidationReport }): PublishCheck[] {
  const { project, renders } = input;
  const decisive = [...renders].filter((r) => r.status === "COMPLETE" || r.status === "FAILED" || RUNNING.has(r.status)).sort(newestFirst)[0];
  const finished = latestRender(renders);
  const report = input.validation ?? finished?.validation_report ?? undefined;

  const rightsKnown = project.rights_status !== ("UNKNOWN" as Project["rights_status"]);
  const approved = project.current_stage === "QA_APPROVED" || project.current_stage === "EXPORTED";

  let render: Pick<PublishCheck, "state" | "detail">;
  if (!decisive) render = { state: "pending", detail: "Render the video first" };
  else if (decisive.status === "FAILED") render = { state: "fail", detail: `The latest render failed. ${decisive.error_message ?? "Check the render stage for the reason."}` };
  else if (decisive.status === "COMPLETE") render = { state: "pass", detail: "The latest render finished" };
  else render = { state: "pending", detail: "A render is running" };

  let valid: Pick<PublishCheck, "state" | "detail">;
  if (!report) valid = { state: "pending", detail: "No render checks yet" };
  else if (!report.is_valid) valid = { state: "fail", detail: report.warnings[0] ?? "The render did not pass its checks" };
  else {
    const n = report.warnings.length;
    valid = { state: "pass", detail: `Passed with ${n === 0 ? "no warnings" : `${n} ${n === 1 ? "warning" : "warnings"}`}` };
  }

  const stale = (project.stale_stages ?? []).includes("render");
  const fresh: Pick<PublishCheck, "state" | "detail"> = !finished
    ? { state: "pending", detail: "Waiting for a finished render" }
    : stale
      ? { state: "fail", detail: "Audio or motion changed after this render. Render again." }
      : { state: "pass", detail: "The render matches the current audio and motion" };

  return [
    { id: "rights", label: "Rights", state: rightsKnown ? "pass" : "fail", detail: rightsKnown ? "Rights are declared" : "Rights are unknown, so publishing is held" },
    { id: "approved", label: "Approved", state: approved ? "pass" : "pending", detail: approved ? "The render is approved" : "Approve the render first" },
    { id: "render", label: "Render", ...render },
    { id: "fresh", label: "Up to date", ...fresh },
    { id: "valid", label: "Render checks", ...valid },
  ];
}

/** Copying the details is allowed unless something has failed; pending checks are shown but do not hold it. */
export function canHandOff(checks: PublishCheck[]): boolean {
  return !checks.some((c) => c.state === "fail");
}

export function chaptersText(chapters: YouTubeChapter[]): string {
  return chapters.map((c) => `${c.timestamp} ${c.title}`).join("\n");
}

export function packagingBundle(data: YouTubePackagingData, title: string): string {
  const tags = [data.tags_string, data.hashtags_string].filter(Boolean).join("\n");
  return [title, data.description, chaptersText(data.chapters), tags].filter(Boolean).join("\n\n");
}

export function durationLabel(seconds: number): string {
  const total = Math.max(0, Math.round(seconds));
  if (total < 60) return `${total} s`;
  if (total < 3600) return `${Math.floor(total / 60)} min ${total % 60} s`;
  return `${Math.floor(total / 3600)} h ${Math.floor((total % 3600) / 60)} min`;
}
